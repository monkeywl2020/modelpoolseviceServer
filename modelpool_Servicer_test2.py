import time
import requests
import json
import os
from concurrent import futures
from threading import Lock
from collections import defaultdict
from datetime import datetime  # 新增：用于格式化时间
from loguru import logger
import grpc

import modelpool_pb2
import modelpool_pb2_grpc

#-----------------------------------------------------------------
#      配置日志处理，设置为 20M每个文件，一共5个。循环覆盖
#-----------------------------------------------------------------
if 0:
    # 动态构造相对路径
    log_dir = os.path.join("./", "log")
    log_path = os.path.join(log_dir, "modelpoolserver_log.log")

    # 移除默认控制台输出
    logger.remove()

    # 配置日志文件
    logger.add(log_path, rotation="20 MB", retention=5)
#-----------------------------------------------------------------
# 定义模型类
class Model:
    def __init__(self, name, model_type, model, base_url):
        self.name = name
        self.model_type = model_type
        self.model = model
        self.base_url = base_url
        self.status = "unknown"
        self.load = 0
        self.usage_count = 0  # 新增：记录使用该模型的客户端数量

# 模型池服务器，主要负责提供模型列表和健康检查，给agent提供可用的模型列表
class ModelPoolServiceServicer(modelpool_pb2_grpc.ModelPoolServiceServicer):
    def __init__(self, config_file="modelserver.json"): # 默认配置在本目录下
        self.config = self._load_config(config_file) # 加载配置
        self.models = self.config.get("models", [])
        logger.info(f"加载了 {len(self.models)} 个模型配置， models: {self.models}")
        self.health_check_interval = self.config.get("health_check_interval", 10)  # 默认 60 秒
        #---------------------------------------------------------
        # 1：跟踪 client_id 到多个 (base_url, model) 的映射
        # agent的 client 用了哪些模型
        #---------------------------------------------------------
        self.client_usage = defaultdict(set) # {client_id1: set([(base_url, model), client_id2: set([(base_url, model)，(base_url, model)...])}
        
        #---------------------------------------------------------
        # 2：反向映射，记录每个模型被哪些 client_id 使用 ，模型对应的有多少client
        #---------------------------------------------------------
        self.model_clients = defaultdict(set)  # {(base_url, model): set([client_id1, client_id2,...])}
        
        #---------------------------------------------------------
        # 3：记录每个 client_id 的最后活跃时间
        #---------------------------------------------------------
        self.client_last_active = {}  # {client_id: timestamp}

        self.usage_lock = Lock()  # 保护并发更新
        #---------------------------------------------------------
        # 4：启动健康检查
        #---------------------------------------------------------
        self._start_health_check() 

    def _load_config(self, config_file):
        """从 JSON 文件加载配置"""
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            # 检查必要字段
            if "models" not in config:
                raise ValueError("配置文件中缺少 'models' 字段")
            if not isinstance(config["models"], list):
                raise ValueError("'models' 必须是数组")
            if "health_check_interval" in config and not isinstance(config["health_check_interval"], int):
                raise ValueError("'health_check_interval' 必须是整数")

            models = []
            for item in config["models"]:
                if not all(key in item for key in ["name", "model_type", "model", "base_url"]):
                    raise ValueError(f"模型配置项缺失必要字段: {item}")
                models.append(Model(
                    name=item["name"],
                    model_type=item["model_type"],
                    model=item["model"],
                    base_url=item["base_url"]
                ))
            logger.info(f"从 {config_file} 加载了 {len(models)} 个模型配置，健康检查间隔: {config.get('health_check_interval', 10)} 秒")
            return {"models": models, "health_check_interval": config.get("health_check_interval", 10)}
        except FileNotFoundError:
            logger.info(f"配置文件 {config_file} 不存在")
            return {"models": [], "health_check_interval": 10}
        except json.JSONDecodeError:
            logger.info(f"配置文件 {config_file} 格式错误")
            return {"models": [], "health_check_interval": 10}
        except Exception as e:
            logger.info(f"加载配置失败: {e}")
            return {"models": [], "health_check_interval": 10}

    # 进行健康检查，采用openAI格式的http请求
    def _check_health(self, model):
        """使用 base_url + '/models' 检查模型服务状态"""
        try:
            # 调用 vLLM 的 /models 接口作为心跳请求
            response = requests.get(f"{model.base_url}/models", timeout=5)
            logger.info(f"====_check_health: {model.base_url}，rsp: {response.status_code} text: {response.text}")
            if response.status_code == 200:
                data = response.json()

                # 提取实际模型名称（根据实际响应结构）
                if data.get("object") == "list" and data.get("data"):
                    # 从第一个模型的 id 中提取名称（格式示例：'/models/Qwen2.5-72B-Instruct-AWQ'）
                    actual_model_name = data["data"][0]["id"].rstrip("/")  # 去除结尾斜杠
                else:
                    # 处理非列表格式的响应（根据实际情况调整）
                    actual_model_name = data.get("id", "").rstrip("/")  # 去除结尾斜杠

                # 获取预期路径并去除结尾斜杠（防止用户配置带斜杠）
                expected_model_path = model.model.rstrip("/")

                # 检查模型名称是否匹配
                if actual_model_name == expected_model_path:
                    model.status = "available"
                    model.load = 0
                else:
                    logger.error(f"模型名称不匹配！预期: {expected_model_path}, 实际: {actual_model_name}")
                    model.status = "unavailable"
                    model.load = 0
            else:
                model.status = "unavailable"
                model.load = 0
        except requests.RequestException:
            # 请求超时或连接失败，认为服务不可用
            model.status = "unavailable"
            model.load = 0

    def _cleanup_inactive_clients(self):
        """清理超过 3 个探测周期未活跃的客户端"""
        with self.usage_lock:
            current_time = time.time()
            timeout = 3 * self.health_check_interval  # 3 个周期
            inactive_clients = [
                client_id for client_id, last_active in self.client_last_active.items()
                if current_time - last_active > timeout
            ]

            for client_id in inactive_clients:
                if client_id in self.client_usage:
                    models_used = self.client_usage[client_id]
                    for model_key in models_used:
                        if client_id in self.model_clients[model_key]:
                            self.model_clients[model_key].remove(client_id)
                            # 更新对应模型的 usage_count
                            for m in self.models:
                                if (m.base_url, m.model) == model_key:
                                    m.usage_count = len(self.model_clients[model_key])
                                    logger.info(f"Client {client_id} has timed out and has been removed from model {model_key[0]},{model_key[1]} . usage_count has been updated to:  {m.usage_count}")
                                    break
                    del self.client_usage[client_id]
                    del self.client_last_active[client_id]
                    logger.info(f"Cleaned up timed-out client {client_id}")

    def _start_health_check(self):
        def run():
            while True:
                # 逐个对每个模型进行健康检查
                for model in self.models:
                    self._check_health(model)# 进行健康检查
                self._cleanup_inactive_clients()  # 在健康检查时清理超时客户端
                time.sleep(self.health_check_interval)  # 使用配置的间隔

                # 新增：打印 client_usage、model_clients 和 client_last_active
                with self.usage_lock:
                    logger.info("\n\n==>##current client and model usage info:")
                    logger.info(f"client_usage: {dict(self.client_usage)}")  # 转为 dict 以便日志可读
                    logger.info(f"model_clients: {dict(self.model_clients)}")
                    # 格式化时间戳为日期时间
                    active_times = {
                        client_id: datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                        for client_id, ts in self.client_last_active.items()
                    }
                    logger.info(f"client_last_active: {active_times}")

                # 改为逐行打印模型状态
                logger.info("==>##cur model status:")
                for m in self.models:
                    logger.info(f" model [{m.name}] status: {{'status': '{m.status}','usage_count':{m.usage_count},'model_type': '{m.model_type}', 'model': '{m.model}','base_url': '{m.base_url}','load': {m.load}}}")
                logger.info("\n")

        import threading
        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()
    
    def _update_usage_count(self, client_id, model_usages):
        """更新模型的 usage_count，支持一个 client_id 使用多个模型"""
        # 加锁以确保并发安全
        with self.usage_lock:
            # 更新最后活跃时间
            self.client_last_active[client_id] = time.time()
           
            if not model_usages:
                logger.info(f"Client {client_id} sent an empty model_usages list, skipping update.")
                return

            # 初始化 client_id 的模型集合
            client_models = self.client_usage[client_id] # 获取这个agent 下面使用了模型的集合

            # 遍历请求中的所有 model_usages
            for usage in model_usages:
                base_url = usage.base_url
                model_path = usage.model
                model_key = (base_url, model_path) # base_url 和 model_path组成一个key，通过这个key可以找到 客户端的client_id
                
                # 如果该 client_id 尚未使用这个模型
                if model_key not in client_models:
                    client_models.add(model_key)

                    # 更新 model_clients 映射
                    # model_clients 的内容 {(base_url, model): set([client_id1, ...]), (base_url, model): set([client_id2,...]),....}
                    self.model_clients[model_key].add(client_id)

                    for m in self.models:
                        if m.base_url == base_url and m.model == model_path:
                            m.usage_count = len(self.model_clients[model_key])
                            logger.info(f"===>agent client_id: {client_id} add new model: {base_url}{model_path}")
                            logger.info(f"===>model: {base_url}{model_path} usage_count update to: {m.usage_count}")
                            break
                    else:
                        # 如果循环未找到匹配的模型，记录警告
                        logger.warning(f"Client {client_id} is using an unregistered model: base_url={base_url}, model={model_path}")

    def GetModelList(self, request, context):
        # 更新 usage_count
        if request.client_id and request.model_usages:
            self._update_usage_count(request.client_id, request.model_usages)

        models = [modelpool_pb2.Model(
            name=m.name, model_type=m.model_type, model=m.model, base_url=m.base_url,
            status=m.status, load=m.load, usage_count=m.usage_count
        ) for m in self.models]
        return modelpool_pb2.ModelListResponse(models=models)

    def GetAvailableModels(self, request, context):
        # 更新 usage_count
        if request.client_id and request.model_usages:
            self._update_usage_count(request.client_id, request.model_usages)

        available = [m for m in self.models if m.status == "available"]
        available.sort(key=lambda x: x.load)
        models = [modelpool_pb2.Model(
            name=m.name, model_type=m.model_type, model=m.model, base_url=m.base_url,
            status=m.status, load=m.load, usage_count=m.usage_count
        ) for m in available]
        return modelpool_pb2.ModelListResponse(models=models)

def serve(port="50052"):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    modelpool_pb2_grpc.add_ModelPoolServiceServicer_to_server(ModelPoolServiceServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info(f"<<<<<<<<<<<<<<ModelPoolServiceServicer load from localhost:{port} success!!!>>>>>>>>>>>>>>>")
    server.wait_for_termination()

if __name__ == "__main__":
    serve()