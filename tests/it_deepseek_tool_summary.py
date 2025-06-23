# tests/it_deepseek_tool_summary.py
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest, logging, json, time, httpx
from agno.models.message import Message
from agno.models.deepseek import DeepSeek
from core.context_managed_agent import ContextManagedAgent
from agno.agent import Agent
from agno.tools import tool

logging.basicConfig(level=logging.DEBUG)   # 打开 Agno 全局 DEBUG

# ---------- 1. 定义一个超简单的工具 ----------
@tool
def dummy_tool() -> str:   # 纯占位，文本越长越涨 token
    repeat = 600
    return "A" * repeat

# ---------- 2. 构造调试用 DeepSeek 客户端 ----------
def build_debug_client(timeout=60):
    def _dbg(name):
        def _hook(e):
            print(f"[SUMMARY-HTTPX] {name}: {e!r}", file=sys.stderr)
        return _hook
    return httpx.Client(
        timeout=timeout,
        http2=False,
        limits=httpx.Limits(max_keepalive_connections=0),
        event_hooks={"request": [_dbg("request")], "response": [_dbg("response")]},
    )

# ---------- 3. 创建主 Agent ----------
def build_agent():
    model = DeepSeek(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        id="deepseek-chat",
        timeout=60,
        max_retries=2,
    )
    ag = ContextManagedAgent(
        model=model,
        tools=[dummy_tool],
        max_context_tokens=2000,
        truncate_threshold=0.8,
        debug_mode=True,          # 打开 Agno + Agent 自己的 DEBUG
        show_tool_calls=True,
    )

    # 给总结模型注入专用 debug httpx.Client
    def _patched_get_or_create(self):
        # 若已缓存直接返回
        if hasattr(self, "_summary_model") and self._summary_model:
            return self._summary_model
        from agno.models.deepseek.deepseek import DeepSeek
        self._summary_model = DeepSeek(
            api_key=self.model.api_key,
            id=self.model.id,
            base_url=self.model.base_url,
            timeout=60,
            max_retries=2,
            http_client=build_debug_client(60),
        )
        return self._summary_model

    # Monkey-patch
    ContextManagedAgent._get_or_create_summary_model = _patched_get_or_create
    return ag

# ---------- 4. 生成 prompt：一次 run 触发 15 次工具调用 ----------
PROMPT = """
你有一个工具 dummy_tool()。
每次对话调用一次，工具回复后继续调用，一直这样下去，会有人在需要的时候叫停你的
"""

if __name__ == "__main__":
    agent = build_agent()
    try:
        # 单轮调用，stream=False 方便观察日志
        agent.print_response(PROMPT, stream=False)
    except Exception as e:
        # 打印完整异常链，便于分析
        import traceback
        traceback.print_exception(type(e), e, e.__traceback__)
        cause = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
        if cause:
            print("── inner cause ──", file=sys.stderr)
            traceback.print_exception(type(cause), cause, cause.__traceback__, file=sys.stderr)