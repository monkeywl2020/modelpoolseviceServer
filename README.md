**这个是用来检测大模型服务端业务是否正常的服务端，原理是使用模型服务端提供的查询模型接口**<br>
例如：vllm的服务端 http://172.21.30.230:8985/v1/models 获取模型的信息。<br>
如果模型正常的话，会响应200OK，并携带模型的信息。服务端接收响应，同时解析响应中模型的名称。<br>
<br>
而在访问本地vllm的大模型端点时候，通常会采用下面这种格式。<br>
'llmcfg': {<br>
    "model_type": "deepseek",<br>
    'model': '/models/DeepSeek-R1-Distill-Qwen-32B',<br>
    'base_url': 'http://172.21.30.230:8985/v1',  <br>
    'api_key': 'EMPTY',<br>
    'top_p': 0.8,<br>
    'temperature': 0.6,<br>
}<br>
而使用openAI的时候，通常是先初始化，然后在使用 客户端进行请求。<br>
        self.active_client = openai.AsyncOpenAI(<br>
            api_key=self.api_key,                # 需要 api_key<br>
            base_url=self.primary_base_url       # 需要 base_url<br>
        )<br>
<br>
然后，response = self.active_client.chat.completions.create(**openAIkwargs)<br>
        openAIkwargs = {<br>
            "model": model_name,                # 需要 model<br>
            "messages": messages,               # 用户的消息，标准openAI格式。<br>
            "stream": True,<br>
            "max_tokens": 2048,<br>
            "top_p": 0.8,<br>
            "temperature": 0.6<br>
        }<br>
所以，实际需要在用户每次使用客户端的时候，获取当前可用的客户端，这个可用客户端是根据探测到的模型端点信息来的。<br>
而这个就是模型服务探测的服务器。客户端是连接这个服务器获取探测结果的。用户侧使用这个Modelpool client的结果来决定<br>
使用哪个客户端。
