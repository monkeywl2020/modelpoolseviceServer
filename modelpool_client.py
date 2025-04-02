import grpc
import time
import uuid
import asyncio
from grpc.aio import insecure_channel
from typing import List
from loguru import logger

import modelpool_pb2
import modelpool_pb2_grpc

#--------------------------------------------------------------------------
# 模型服务池客户端
# 说明：ModelPoolClient 注意他不是每次都对所有的地址都建 stub和 channel，
# 只有初始化的时候干一次。后面的只要有正常的就不会对其他的进行重建。因为如果某个
# modelpool server 异常了，可能是很长时间都不能恢复。这种情况下反复探测这个地址
# 意义不大，而且反复建立通道和stub又反复释放（这里还不是显示的释放资源）反而可能
# 会出现问题。
#    所以，首次切换不会重建，如果全部失败过了，重建才会执行，而且这过程中未恢复的 
# 仍然会重建失败。实际重建只有当时正常的才能恢复，不正常的还是会失败，后续切换实际
# 重建失败的的channel实际没有啥作用。一旦正常的channel失败了，又会触发重建。只有在
# 重建的时候正常的，后续切换才能正常使用
#--------------------------------------------------------------------------
class ModelPoolClient:
    # 初始化，默认设置主备地址（是模型服务池管理器的地址，2个，以防1个挂掉了）
    def __init__(self, addresses: list[str] = ["localhost:50051", "localhost:50052"]):
        self.addresses = addresses # modelpool service server的地址池，可以配置多个 server确保不会单点故障
        self.models = [] # 存放所有的可用的模型的信息
        self.client_id = str(uuid.uuid4()) # 客户端的uuid，唯一标识，每个agent使用一个模型池客户端都有一个唯一的客户端

        #--------------------------------------------------------------------------
        # 这个里面是放着使用这个 ModelPoolClient 的agent,他们使用的模型服务器的信息
        #--------------------------------------------------------------------------
        self.used_model_usages = set()  # 使用 set 存储 (base_url, model) 元组，避免重复

        logger.info(f"=======>ModelPoolClient client_id:{self.client_id}")
        # 预创建所有通道和存根
        self.channels = {} # 都是以 primary 和 secondary的字符串为 key，值是 channel
        self.stubs = {}    # 都是以 primary 和 secondary的字符串为 key，值是 stub

        # 初始化通道和存根, 遍历主备建立通道和stub
        for addr in self.addresses:
            channel = insecure_channel(addr)
            stub = modelpool_pb2_grpc.ModelPoolServiceStub(channel)
            self.channels[addr] = channel
            self.stubs[addr] = stub
            logger.info(f"init channel: {addr}，delay verification until use!")

        self.current_address = self.addresses[0]  # 默认使用第一个地址        

    # 获取当前缓存下来的所有可用的模型的信息
    def get_all_available_models(self) -> List:
        return self.models

    # 测试用函数：设置当前可用模型信息，用于测试
    def set_all_available_models(self, new_models: List) -> None:
        """设置当前可用模型信息，用于测试"""
        self.models = new_models
        logger.info(f"Set available models: {self.models}")

    #--------------------------------------------------------------------------
    # 用于动态添加使用的模型信息，这个函数是给使用这个 ModelPoolClient 的agent调用的
    # agent将自己使用的模型服务器的信息上报给模型池客户端，模型池客户端将这些信息存储
    # 起来，同时在获取模型服务器端信息的时候，将这些信息上报给服务端，更新服务端的 模型的 usage_count
    #--------------------------------------------------------------------------
    def add_model_usage(self, base_url: str, model: str):
        """添加客户端使用的模型信息"""
        model_usage = (base_url, model)
        if model_usage not in self.used_model_usages:
            self.used_model_usages.add(model_usage)
            logger.info(f"Added model usage for client {self.client_id}: base_url={base_url}, model={model}")

    #----------------------------------------------------
    # 一次性重建所有通道,这个当两个都异常了才会重建
    #----------------------------------------------------
    async def _rebuild_all_channels(self):
        """一次性重建所有通道"""
        # 先关闭所有旧通道
        for addr, channel in self.channels.items():
            if channel is not None:
                try:
                    channel.close()
                    logger.info(f"Closed old channel: {addr}")
                except Exception as e:
                    logger.error(f"Failed to close old channel {addr} : {e}")

        # 重建所有通道
        rebuilt_stubs = {}
        for addr in self.addresses:
            try:
                channel = insecure_channel(addr)
                stub = modelpool_pb2_grpc.ModelPoolServiceStub(channel)
                await stub.GetAvailableModels(
                    modelpool_pb2.AvailableModelsRequest(client_id=self.client_id),
                    timeout=5
                )
                self.channels[addr] = channel
                rebuilt_stubs[addr] = stub
                logger.info(f"Successfully rebuilt channel: {addr}")
            except Exception as e:
                logger.error(f"Failed to rebuild channel {addr} : {e}")
                self.channels[addr] = None
                rebuilt_stubs[addr] = None

        # 更新 stubs 和 current_address
        self.stubs.update(rebuilt_stubs)
        for addr in self.addresses:
            if self.stubs[addr] is not None:
                self.current_address = addr
                return self.stubs[addr]
        logger.error("All channel rebuilds failed")
        return None

    #----------------------------------------------------
    # 获取模型池管理器的grpc stub，用于调用grpc服务
    #----------------------------------------------------
    async def _get_available_stub(self):
        """获取可用存根，优先复用现有通道"""
        # 优先尝试当前地址
        current_stub = self.stubs.get(self.current_address)
        if current_stub is not None:
            try:
                # 快速健康检查
                await current_stub.GetModelList(
                    modelpool_pb2.AvailableModelsRequest(client_id=self.client_id),
                    timeout=2
                )
                return current_stub
            except Exception:
                logger.warning(f"The current address {self.current_address} is unavailable, trying to switch")
        
        # 遍历所有地址寻找可用通道
        for addr in self.addresses:
            if addr == self.current_address:
                continue
            stub = self.stubs.get(addr)
            if stub is not None:
                try:
                    await stub.GetModelList(
                        modelpool_pb2.AvailableModelsRequest(client_id=self.client_id),
                        timeout=2
                    )
                    self.current_address = addr
                    logger.info(f"Switched to available address: {addr}")
                    return stub
                except grpc.RpcError as e:
                    logger.warning(f"Address {addr} is unavailable: {e.details()}")
        
        # 所有通道不可用，统一重建
        logger.error("All pre-created channels are unavailable, performing a unified rebuild")
        return await self._rebuild_all_channels()
    
    #--------------------------------------------------------------------------
    # 从modelpoolservice server获取当前可用模型列表，同时上报当前使用这个客户端
    # 的grpc链路上的agent，所有使用的模型信息
    #--------------------------------------------------------------------------
    async def get_available_models(self):
        """获取可用模型列表，复用通道"""
        stub = await self._get_available_stub()
        if stub is None:
            logger.error("Failed to get an available stub, returning an empty list")
            return []

        try:
            # 构造grpc请求，消息的内容是当前客户端使用 base_url 和 model ，id是客户端唯一标识用来给服务端区分客户端的
            # 这个是当前客户端的请求， client_id 是自己的id
            request = modelpool_pb2.AvailableModelsRequest(
                # 将使用这个modelpool 客户端的agent下使用的所有的模型服务器的信息上报给服务端
                model_usages=[
                    modelpool_pb2.ModelUsage(base_url=base_url, model=model)
                    for base_url, model in self.used_model_usages
                ],
                client_id=self.client_id
            )
            # 获取当前可用的模型列表
            response = await stub.GetAvailableModels(request, timeout=5)
            self.models = response.models
            return self.models
        except Exception as e:
            logger.error(f"Failed to get the model list: {e}")
            self.stub = None  # 标记 Stub 失效，下次重建
            raise

    async def start_polling(self, interval: int = 10) -> None:
        """启动后台轮询任务以更新模型状态"""
        self._polling_task = asyncio.create_task(
            self.poll_status(interval),
            name=f"ModelPoolClientPoll/{self.client_id}"
        )
        logger.info(f"Started model pool polling for client {self.client_id} (interval: {interval}s)")
    #----------------------------------------------------
    # 定时从 modelpool service 获取 所有模型服务器的状态
    #----------------------------------------------------
    async def poll_status(self, interval=10):
        while True:
            try:
                start_time = time.time()
                models = await self.get_available_models()# grpc远程调用
                logger.info(f"Retrieved {self.current_address} models from {len(models)} took {time.time() - start_time:.2f}s")

                # 优化打印模型列表
                if models:
                    model_lines = []
                    for m in models:
                        model_info = (
                            f"- name: \"{m.name}\",model_type: \"{m.model_type}\",model: \"{m.model}\",base_url: \"{m.base_url}\",status: \"{m.status}\",usage_count: {m.usage_count}\n\n"
                        )
                        model_lines.append(model_info)
                    logger.info("Received model list:\n" + "\n".join(model_lines))
                else:
                    logger.info("Received model list: []")

            except Exception as e:
                logger.error(f"Failed to query the model pool status: {e}")
            await asyncio.sleep(interval)

    #----------------------------------------------------
    # 关闭所有通道, 释放资源
    #----------------------------------------------------
    async def close(self):
        """关闭所有通道并停止轮询"""
        # 停止轮询
        if hasattr(self, '_polling_task') and self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        
        # 关闭所有通道
        for addr, channel in self.channels.items():
            if channel is not None:
                try:
                    channel.close()
                    logger.info(f"Closed channel: {addr}")
                except Exception as e:
                    logger.error(f"Failed to close channel {addr} : {e}")


# 测试代码
async def main():
    #my_addresses = ["172.21.30.231:50051","172.21.30.231:50052"]
    my_addresses = ["localhost:50051","172.21.30.231:50052"]
    client = ModelPoolClient(addresses = my_addresses)
    # 告知服务端自己所使用的 url 和 model
    client.add_model_usage("http://8.147.119.207:8985/v1", "/root/models/DeepSeek-R1-Distill-Qwen-32B")
    client.add_model_usage("http://172.21.30.231:8987/v1", "/models/DeepSeek-R1-Distill-Qwen-32B")
    client.add_model_usage("http://172.21.30.230:8985/v1", "/models/DeepSeek-R1-Distill-Qwen-32B")
    await client.start_polling()
    try:
        # 无限等待，直到收到退出信号（如 Ctrl+C）
        await asyncio.Future()  # 等待一个永不完成的 Future
    except KeyboardInterrupt:
        logger.info("Received shutdown signal, closing client...")
        await client.close()
 
if __name__ == "__main__":
    asyncio.run(main())