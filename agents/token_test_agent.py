"""
Token监控测试Agent
专门用于测试ContextManagedAgent的token监控功能
"""

from typing import Optional
from textwrap import dedent
from pathlib import Path
import os

from agno.agent import Agent
from agno.tools.shell import ShellTools
from agno.tools.file import FileTools

from core.context_managed_agent import ContextManagedAgent
from agno.models.deepseek import DeepSeek

# 硬编码工作空间路径
HARDCODED_WORKSPACE_PATH = Path("E:/vulnAgent8")

def get_token_test_agent(
    model_id: str = "deepseek-reasoner",
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    debug_mode: bool = True,
    max_context_tokens: int = 4000,  # 设置较低的token限制，更容易触发监控
) -> ContextManagedAgent:
    """创建用于测试token监控的简化代理"""
    
    shell_tools = ShellTools(base_dir=HARDCODED_WORKSPACE_PATH)
    file_tools = FileTools(base_dir=HARDCODED_WORKSPACE_PATH)
    
    test_tools = [
        shell_tools,
        file_tools
    ]
    
    additional_context = dedent(f"""\
        <context>
        目标项目位于: {str(HARDCODED_WORKSPACE_PATH)}。所有相对路径操作都相对于此路径。
        </context>

        **重要提醒**: 在工具调用时，只生成标准的JSON格式工具调用，不要添加任何额外的结束标记。
        
        ## 🧪 Token监控测试Agent
        
        你是一个专门用于测试token监控功能的测试代理。你的主要任务是：
        
        1. **生成不同长度的响应**来测试token使用率
        2. **执行各种操作**来观察token监控的行为
        3. **帮助验证**ContextManagedAgent的智能输出策略
        
        ### 测试场景：
        - 短响应（<50% token使用率）- 应该静默
        - 中等响应（50-70% token使用率）- 应该简单提醒
        - 长响应（70-80% token使用率）- 应该警告
        - 超长响应（>80% token使用率）- 应该关键警告
        
        ### 可用命令：
        - `test short` - 生成短响应
        - `test medium` - 生成中等长度响应
        - `test long` - 生成长响应
        - `test very-long` - 生成超长响应
        - `analyze files` - 分析文件结构（中等token消耗）
        - `deep analysis` - 深度分析（高token消耗）
        """)

    agent_description = dedent("""\
        ## 🧪 Token监控测试专家
        
        你是一个专门用于测试token监控功能的测试代理。
        
        **主要职责**：
        - 根据用户指令生成不同长度的响应
        - 测试ContextManagedAgent的token监控功能
        - 验证智能输出策略的有效性
        
        **响应策略**：
        - 当用户说"test short"时，给出简短回复（约100-200 tokens）
        - 当用户说"test medium"时，给出中等长度回复（约500-1000 tokens）
        - 当用户说"test long"时，给出长回复（约1500-2500 tokens）
        - 当用户说"test very-long"时，给出超长回复（约3000+ tokens）
        
        **测试重点**：
        - 观察不同token使用率下的监控输出
        - 验证智能输出策略是否按预期工作
        - 确认token监控不会干扰正常功能
        """)

    # 创建ContextManagedAgent
    agent = ContextManagedAgent(
        name="Token Test Agent",
        agent_id="token_test_agent_v1",
        model=DeepSeek(id=model_id, api_key=os.getenv("DEEPSEEK_API_KEY")),
        user_id=user_id or "token_test_user",
        session_id=session_id,
        tools=test_tools,
        instructions=[agent_description, additional_context],
        debug_mode=debug_mode,
        max_context_tokens=max_context_tokens,
        # 启用详细的debug输出
        show_tool_calls=True,
        markdown=True,
        add_datetime_to_instructions=True,
    )
    
    # 确保debug_mode属性被设置（用于token监控调试）
    agent.debug_mode = debug_mode
    
    return agent

# 测试函数
async def test_token_monitoring():
    """测试token监控功能"""
    print("🧪 开始测试Token监控功能...")
    
    agent = get_token_test_agent(
        user_id="test_user",
        model_id="deepseek-reasoner"
    )
    
    test_cases = [
        "test short",
        "test medium", 
        "test long",
        "test very-long"
    ]
    
    for test_case in test_cases:
        print(f"\n📝 测试案例: {test_case}")
        print("-" * 50)
        
        try:
            response = await agent.arun(test_case)
            print(f"✅ 响应长度: {len(response.content)} 字符")
            print(f"📊 响应内容预览: {response.content[:100]}...")
        except Exception as e:
            print(f"❌ 测试失败: {e}")
    
    print("\n🎯 Token监控测试完成！")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_token_monitoring()) 