from agno.models.ollama.chat import Ollama
from typing import Any, Dict, Iterator, List, Mapping, Optional, Type, Union
from pydantic import BaseModel
from agno.models.message import Message
import requests, json

class OllamaNoStream(Ollama):
    """强制把 stream 请求降级为一次性请求，兼容远程 Ollama 502 问题"""
    
    # 同步
    def invoke_stream(
        self,
        messages: List[Message],
        response_format: Optional[Union[Dict, Type[BaseModel]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    ) -> Iterator[Mapping[str, Any]]:
        # 直接 HTTP 调用，绕过 ollama.Client 的连接池问题
        url = f"{self.host.rstrip('/')}/api/chat"
        payload = {
            "model": self.id.strip(),
            "messages": [self._format_message(m) for m in messages],
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        resp = requests.post(
            url,
            headers=headers,
            data=json.dumps(payload),
            timeout=self.timeout or 120,
            proxies={"http": None, "https": None},  # 禁用环境代理
        )
        resp.raise_for_status()
        yield resp.json()

    # 异步
    async def ainvoke_stream(
        self,
        messages: List[Message],
        response_format: Optional[Union[Dict, Type[BaseModel]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    ):
        import asyncio, requests, json
        print(">>> no-stream ainvoke_stream called")
        url = f"{self.host.rstrip('/')}/api/chat"
        payload = {
            "model": self.id.strip(),
            "messages": [self._format_message(m) for m in messages],
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        resp = await asyncio.to_thread(
            requests.post,
            url,
            headers=headers,
            data=json.dumps(payload),
            timeout=self.timeout or 120,
            proxies={"http": None, "https": None},
        )
        resp.raise_for_status()
        yield resp.json()