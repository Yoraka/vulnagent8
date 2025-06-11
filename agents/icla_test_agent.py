from textwrap import dedent
from typing import Optional, Callable, Dict, Any
import json
from datetime import datetime
import os
from pathlib import Path

from agno.agent import Agent
from agno.models.openai import OpenAIChat, OpenAILike
from agno.storage.agent.postgres import PostgresAgentStorage
from agno.tools.shell import ShellTools
from agno.tools.file import FileTools
from agno.tools import tool
from agno.utils.pprint import pprint_run_response

from db.session import db_url

# 硬编码的工作空间路径
HARDCODED_WORKSPACE_PATH = Path("/data/one-api")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY is not set")

# ====== 新架构：状态透明工具 ======

@tool
def view_current_state(agent: Agent) -> str:
    """查看当前HCA状态和进度 - 完整状态信息（因为工具调用时看不到session_state）"""
    _ensure_state_structure(agent)
    
    runtime_state = agent.session_state["runtime_state"]
    working_memory = agent.session_state["working_memory"]
    current_hypothesis = runtime_state.get("current_hypothesis", {})
    current_challenge = runtime_state.get("current_challenge", {})
    current_adaptation = runtime_state.get("current_adaptation", {})
    
    # 获取下一步建议
    next_action = "分析代码，调用 start_new_hypothesis('具体假设内容')"
    if current_hypothesis:
        status = current_hypothesis.get('status', '')
        if status == 'pending_challenge':
            next_action = "调用 record_challenge('类型', '反驳证据内容')"
        elif status == 'challenged':
            next_action = "调用 complete_adaptation('调整内容', '推理过程')"
        elif status == 'adapted':
            next_action = "可以开始新假设或调用 validate_conclusion_readiness()"
    
    # 完整的状态输出（替代session_state自动注入）
    result = f"""📊 **完整ICLA状态视图**

🔬 **当前假设** (H-{runtime_state.get('hypothesis_count', 1):02d}):
- ID: {current_hypothesis.get('id', '尚未创建')}
- 状态: {current_hypothesis.get('status', 'N/A')}
- 创建时间: {current_hypothesis.get('created_at', 'N/A')}
- 内容: {current_hypothesis.get('content', '尚未设置')}

⚔️ **当前挑战**:
- 类型: {current_challenge.get('type', 'N/A')}
- 状态: {current_challenge.get('status', 'N/A')}
- 内容: {current_challenge.get('content', 'N/A')}
- 时间: {current_challenge.get('timestamp', 'N/A')}

🧠 **当前适应**:
- 状态: {current_adaptation.get('status', 'N/A')}
- 变化: {current_adaptation.get('changes', 'N/A')}
- 推理: {current_adaptation.get('reasoning', 'N/A')}

📈 **整体进度**:
- 当前阶段: {runtime_state.get('current_phase', 'hypothesis')}
- 假设计数: {runtime_state.get('hypothesis_count', 1)}
- 累积奖励: {agent.session_state.get('cumulative_reward', 0.0):.2f}
- 总步数: {agent.session_state.get('total_steps', 0)}
- 工作记忆大小: {len(agent.session_state.get('main_md_content', ''))} 字符

📚 **HCA历史**:
- 已完成循环数: {len(working_memory.get('hca_history', []))}

🎯 **当前状态判断**:
- 当前假设可用于结论: {'✅' if current_hypothesis.get('status') == 'adapted' else '❌'}
- 建议下一步行动: {next_action}

⚠️ **重要提醒**: 
- 只有状态为'adapted'的假设才能用于形成最终结论
- 必须完整经过 H→C→A 流程"""
    
    return result

@tool
def view_hca_history(agent: Agent) -> str:
    """查看HCA历史循环记录 - 完整历史信息（工具调用时无法访问session_state）"""
    _ensure_state_structure(agent)
    
    working_memory = agent.session_state["working_memory"]
    hca_history = working_memory.get("hca_history", [])
    
    if not hca_history:
        return "📚 **HCA历史**: 暂无完成的HCA循环记录\n\n⚠️ 这意味着还没有任何假设完成完整的H→C→A流程"
    
    result = f"📚 **完整HCA历史记录** (共{len(hca_history)}个循环):\n\n"
    
    # 显示所有循环的详细信息
    for i, cycle in enumerate(hca_history, 1):
        result += f"**循环 {cycle.get('cycle_id', f'#{i}')} - {cycle.get('completed_at', 'N/A')}**:\n"
        result += f"- 假设: {cycle.get('hypothesis', 'N/A')}\n"
        result += f"- 挑战类型: {cycle.get('challenge_type', 'N/A')}\n"
        result += f"- 挑战内容: {cycle.get('challenge_content', 'N/A')}\n"
        result += f"- 适应变化: {cycle.get('adaptation_changes', 'N/A')}\n"
        result += f"- 适应推理: {cycle.get('adaptation_reasoning', 'N/A')}\n"
        result += f"- 状态: {cycle.get('status', 'N/A')}\n"
        result += "---\n"
    
    # 添加学习洞察
    learning_insights = working_memory.get("learning_insights", [])
    if learning_insights:
        result += f"\n💡 **学习洞察** (共{len(learning_insights)}条):\n"
        for insight in learning_insights[-3:]:  # 显示最近3条
            result += f"- {insight}\n"
    
    result += f"\n🔢 **统计摘要**:\n"
    result += f"- 完成的假设数: {len(hca_history)}\n"
    result += f"- 学习洞察数: {len(learning_insights)}\n"
    result += f"- 可用于结论的假设: {len([h for h in hca_history if h.get('status') == 'completed'])}个"
    
    return result

# ====== 新架构：状态更新工具 ======

@tool
def start_new_hypothesis(agent: Agent, content: str) -> str:
    """开始新假设 - 代理自主决定何时使用"""
    _ensure_state_structure(agent)
    
    runtime_state = agent.session_state["runtime_state"]
    hypothesis_count = runtime_state["hypothesis_count"]
    
    # 创建新假设
    new_hypothesis = {
        "id": f"H-{hypothesis_count:02d}",
        "content": content,
        "created_at": datetime.now().isoformat(),
        "status": "pending_challenge"
    }
    
    runtime_state["current_hypothesis"] = new_hypothesis
    runtime_state["current_phase"] = "hypothesis"
    
    # 更新工作记忆
    agent.session_state["main_md_content"] = _update_main_md_with_hypothesis(agent, content)
    agent.session_state["total_steps"] = agent.session_state.get("total_steps", 0) + 1
    
    # 验证状态一致性
    is_valid, error_msg = _validate_state_consistency(agent)
    if not is_valid:
        return f"❌ **状态错误**: {error_msg}"
    
    return f"""🔬 **新假设已创建**: H-{hypothesis_count:02d}
    
📋 **假设内容**: {content}
⚠️ **状态**: pending_challenge (无法用于结论)
🎯 **下一步**: 必须进入挑战阶段才能用于结论形成

💡 **漏洞分析提醒**: 确保假设具体指向可能的安全漏洞点"""

@tool
def record_challenge(agent: Agent, challenge_type: str, content: str) -> str:
    """记录挑战内容 - 如果要形成结论，此步骤必须执行"""
    _ensure_state_structure(agent)
    
    runtime_state = agent.session_state["runtime_state"]
    current_hypothesis = runtime_state.get("current_hypothesis", {})
    
    if not current_hypothesis or current_hypothesis.get("status") != "pending_challenge":
        return "❌ **错误**: 当前没有待挑战的假设。请先调用 start_new_hypothesis()"
    
    # 验证challenge_type有效性
    valid_types = ["assumption", "evidence", "logic", "bias"]
    if challenge_type not in valid_types:
        return f"❌ **错误**: challenge_type必须是以下之一: {valid_types}"
    
    # 记录挑战
    challenge = {
        "type": challenge_type,
        "content": content,
        "status": "addressed",
        "timestamp": datetime.now().isoformat()
    }
    
    runtime_state["current_challenge"] = challenge
    runtime_state["current_hypothesis"]["status"] = "challenged"
    runtime_state["current_phase"] = "challenge"
    
    agent.session_state["total_steps"] = agent.session_state.get("total_steps", 0) + 1
    
    # 验证状态一致性
    is_valid, error_msg = _validate_state_consistency(agent)
    if not is_valid:
        return f"❌ **状态错误**: {error_msg}"
    
    return f"""⚔️ **挑战已记录**: {challenge_type}

📋 **挑战内容**: {content}
✅ **假设状态**: challenged (仍无法用于结论)
🎯 **下一步**: 必须完成适应阶段才能用于结论形成

🔍 **安全分析提醒**: 挑战应关注输入验证、权限检查、边界条件等安全防护"""

@tool
def complete_adaptation(agent: Agent, changes: str, reasoning: str) -> str:
    """完成适应 - 如果要形成结论，此步骤必须执行"""
    _ensure_state_structure(agent)
    
    runtime_state = agent.session_state["runtime_state"]
    current_hypothesis = runtime_state.get("current_hypothesis", {})
    
    if not current_hypothesis or current_hypothesis.get("status") != "challenged":
        return "❌ **错误**: 当前假设未经过挑战。请先调用 record_challenge()"
    
    # 记录适应
    adaptation = {
        "changes": changes,
        "reasoning": reasoning,
        "status": "completed",
        "timestamp": datetime.now().isoformat()
    }
    
    runtime_state["current_adaptation"] = adaptation
    runtime_state["current_hypothesis"]["status"] = "adapted"
    runtime_state["current_phase"] = "adapt"
    
    # 记录到历史
    _record_hca_cycle_to_history(agent)
    
    # 准备下一个假设
    runtime_state["hypothesis_count"] += 1
    runtime_state["current_phase"] = "hypothesis"
    
    agent.session_state["total_steps"] = agent.session_state.get("total_steps", 0) + 1
    
    # 验证状态一致性
    is_valid, error_msg = _validate_state_consistency(agent)
    if not is_valid:
        return f"❌ **状态错误**: {error_msg}"
    
    return f"""🧠 **适应已完成**

📋 **适应变化**: {changes}
🤔 **推理过程**: {reasoning}
✅ **假设状态**: adapted (可用于结论形成)

🔄 **流程状态**: 准备开始下一个假设 H-{runtime_state['hypothesis_count']:02d}
🎯 **漏洞发现**: 如果确认发现漏洞，调用 terminate_with_report()"""

@tool
def validate_conclusion_readiness(agent: Agent) -> str:
    """验证是否可以基于当前假设形成结论"""
    _ensure_state_structure(agent)
    
    runtime_state = agent.session_state["runtime_state"]
    working_memory = agent.session_state["working_memory"]
    
    # 检查当前假设
    current_hypothesis = runtime_state.get("current_hypothesis", {})
    current_ready = current_hypothesis.get("status") == "adapted"
    current_hypothesis_id = current_hypothesis.get("id", "N/A")
    
    # 检查历史假设
    hca_history = working_memory.get("hca_history", [])
    ready_hypotheses = [h for h in hca_history if h.get("status") == "completed"]
    
    # 计算总的可用假设数
    total_ready = len(ready_hypotheses) + (1 if current_ready else 0)
    
    status_message = f"""🎯 **结论就绪性验证**

✅ **可用于结论的假设** (总计: {total_ready}个):
- 当前假设: {current_hypothesis_id if current_ready else '无'}
- 历史完成假设: {len(ready_hypotheses)}个

📊 **当前假设状态**:
- ID: {current_hypothesis_id}
- 状态: {current_hypothesis.get('status', 'N/A')}
- {'✅ 可用于结论' if current_ready else '❌ 无法用于结论'}

🚨 **流程完整性**: 只有adapted状态的假设才能用于最终结论"""

    # 给出具体的下一步建议
    if current_ready or total_ready > 0:
        status_message += f"\n\n💡 **建议**: 当前有{total_ready}个假设可用于结论，可以调用 terminate_with_report()"
    else:
        status_message += f"\n\n⚠️ **建议**: 尚无可用假设，需要完成当前HCA循环或开始新假设"
    
    return status_message

# ====== 保留原有核心工具（适配新架构）======

@tool
def calculate_intrinsic_reward(agent: Agent, information_gain_score: float, reasoning: str) -> str:
    """计算并记录内在奖励 - ICLA 核心机制"""
    if not 0.0 <= information_gain_score <= 1.0:
        return "❌ 信息增益分数必须在 0.0 到 1.0 之间"
    
    current_reward = agent.session_state.get("cumulative_reward", 0.0)
    new_reward = current_reward + information_gain_score
    agent.session_state["cumulative_reward"] = new_reward
    
    if "reward_history" not in agent.session_state:
        agent.session_state["reward_history"] = []
    
    reward_entry = {
        "step": agent.session_state.get("total_steps", 0),
        "score": information_gain_score,
        "reasoning": reasoning,
        "timestamp": datetime.now().isoformat()
    }
    agent.session_state["reward_history"].append(reward_entry)
    
    return f"✅ 内在奖励已记录: +{information_gain_score:.2f} | 累积奖励: {new_reward:.2f}"

@tool
def terminate_with_report(agent: Agent, final_report: str) -> str:
    """终止任务并提交最终报告"""
    agent.session_state["task_completed"] = True
    agent.session_state["final_report"] = final_report
    agent.session_state["completion_time"] = datetime.now().isoformat()
    
    summary = {
        "total_steps": agent.session_state.get("total_steps", 0),
        "cumulative_reward": agent.session_state.get("cumulative_reward", 0.0),
        "final_report": final_report
    }
    
    return f"🏁 任务已完成！\n\n**最终报告:**\n{final_report}\n\n**统计:**\n```json\n{json.dumps(summary, indent=2, ensure_ascii=False)}\n```"

@tool
def create_archive_file(agent: Agent, filename: str, content: str) -> str:
    """创建归档文件 - 用于上下文管理"""
    if "archive_files" not in agent.session_state:
        agent.session_state["archive_files"] = {}
    
    agent.session_state["archive_files"][filename] = {
        "content": content,
        "created_at": datetime.now().isoformat(),
        "step": agent.session_state.get("total_steps", 0)
    }
    
    return f"📁 归档文件已创建: {filename} ({len(content)} 字符)"

@tool
def update_main_md(agent: Agent, new_content: str) -> str:
    """传统工作记忆更新 - 兼容旧接口，建议使用新架构工具"""
    agent.session_state["main_md_content"] = new_content
    agent.session_state["last_update_time"] = datetime.now().isoformat()
    agent.session_state["total_steps"] = agent.session_state.get("total_steps", 0) + 1
    
    # 简化的上下文提醒
    content_length = len(new_content)
    if content_length > 3000:
        pressure_info = f"⚠️ 上下文: {content_length} 字符 (考虑归档)"
    else:
        pressure_info = f"📊 上下文: {content_length} 字符"
    
    return f"""✅ 工作记忆已更新
{pressure_info}
📈 步数: {agent.session_state['total_steps']} | 累积奖励: {agent.session_state.get('cumulative_reward', 0.0):.2f}

💡 建议：使用新架构工具 view_current_state() 查看详细状态"""

# ====== 新架构支持函数 ======

def _validate_state_consistency(agent: Agent) -> tuple[bool, str]:
    """验证状态一致性，返回(是否有效, 错误信息)"""
    _ensure_state_structure(agent)
    
    runtime_state = agent.session_state["runtime_state"]
    current_hypothesis = runtime_state.get("current_hypothesis", {})
    current_challenge = runtime_state.get("current_challenge", {})
    current_adaptation = runtime_state.get("current_adaptation", {})
    current_phase = runtime_state.get("current_phase", "hypothesis")
    
    # 检查状态机的一致性
    if current_hypothesis:
        hypothesis_status = current_hypothesis.get("status", "")
        
        # 状态和阶段一致性检查
        if hypothesis_status == "pending_challenge":
            if current_phase != "hypothesis":
                return False, f"假设状态为pending_challenge，但当前阶段为{current_phase}，应该是hypothesis"
            if current_challenge:
                return False, "假设状态为pending_challenge，但已经存在挑战记录"
                
        elif hypothesis_status == "challenged":
            if current_phase != "challenge":
                return False, f"假设状态为challenged，但当前阶段为{current_phase}，应该是challenge"
            if not current_challenge:
                return False, "假设状态为challenged，但没有挑战记录"
                
        elif hypothesis_status == "adapted":
            if current_phase != "adapt":
                return False, f"假设状态为adapted，但当前阶段为{current_phase}，应该是adapt"
            if not current_challenge or not current_adaptation:
                return False, "假设状态为adapted，但缺少挑战或适应记录"
    
    return True, "状态一致"

def _ensure_state_structure(agent: Agent):
    """确保新架构状态结构存在"""
    if "runtime_state" not in agent.session_state:
        agent.session_state["runtime_state"] = {
            "current_phase": "hypothesis",
            "hypothesis_count": 1,
            "current_hypothesis": {},
            "current_challenge": {},
            "current_adaptation": {},
            "phase_guidance": {}
        }
    
    if "working_memory" not in agent.session_state:
        agent.session_state["working_memory"] = {
            "hca_history": [],
            "learning_insights": [],
            "challenge_patterns": {}
        }

def _update_main_md_with_hypothesis(agent: Agent, hypothesis_content: str) -> str:
    """使用假设内容更新主工作记忆"""
    runtime_state = agent.session_state["runtime_state"]
    hypothesis_id = runtime_state["current_hypothesis"]["id"]
    
    existing_content = agent.session_state.get("main_md_content", "")
    
    # 添加新假设段落
    new_section = f"""

## Active Hypothesis {hypothesis_id}
**假设陈述**: {hypothesis_content}
**创建时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**状态**: 待挑战 (pending_challenge)

### 预期发现
{hypothesis_content}

### 挑战记录
(待更新)

### 适应结果
(待更新)
"""
    
    return existing_content + new_section

def _record_hca_cycle_to_history(agent: Agent):
    """将完成的HCA循环记录到历史"""
    runtime_state = agent.session_state["runtime_state"]
    working_memory = agent.session_state["working_memory"]
    
    current_hypothesis = runtime_state.get("current_hypothesis", {})
    current_challenge = runtime_state.get("current_challenge", {})
    current_adaptation = runtime_state.get("current_adaptation", {})
    
    if current_hypothesis and current_challenge and current_adaptation:
        cycle_record = {
            "cycle_id": runtime_state.get("hypothesis_count", 1),
            "hypothesis": current_hypothesis.get("content", ""),
            "challenges": [current_challenge],
            "adaptations": [current_adaptation.get("changes", "")],
            "outcomes": current_adaptation.get("reasoning", ""),
            "status": "completed",
            "timestamp": datetime.now().isoformat()
        }
        
        working_memory["hca_history"].append(cycle_record)
        
        # 清理当前状态，为下一个HCA循环准备
        runtime_state["current_hypothesis"] = {}
        runtime_state["current_challenge"] = {}
        runtime_state["current_adaptation"] = {}

# ====== 新架构编排钩子 ======

def icla_orchestrator_hook(function_name: str, function_call: Callable, arguments: Dict[str, Any]) -> Any:
    """
    新架构ICLA协调器钩子 - 轻度编排，确保流程完整性
    """
    # 调用原始函数
    result = function_call(**arguments)
    
    # 获取agent实例
    agent = arguments.get("agent")
    if not agent:
        return result
    
    # 确保状态结构存在
    _ensure_state_structure(agent)
    
    runtime_state = agent.session_state["runtime_state"]
    current_phase = runtime_state.get("current_phase", "hypothesis")
    current_hypothesis = runtime_state.get("current_hypothesis", {})
    
    # 检查HCA流程完整性
    incomplete_hypotheses = []
    if current_hypothesis and current_hypothesis.get("status") in ["pending_challenge", "challenged"]:
        incomplete_hypotheses.append(current_hypothesis)
    
    # 检查是否有跳跃流程的倾向
    process_integrity_warning = False
    if function_name == "terminate_with_report":
        if incomplete_hypotheses:
            process_integrity_warning = True
    
    # 提供流程完整性可见性
    if isinstance(result, str):
        enhanced_result = result
        
        # HCA完整性警告
        if incomplete_hypotheses:
            enhanced_result += f"\n\n⚠️ **流程完整性提醒**: 有{len(incomplete_hypotheses)}个假设尚未完成HCA流程，无法用于结论形成"
        
        # 跳跃流程检测
        if process_integrity_warning:
            enhanced_result += "\n\n🚨 **流程完整性**: 假设需要经过挑战和适应才能用于结论形成"
        
        # 温和的流程指导
        if function_name == "start_new_hypothesis":
            enhanced_result += "\n\n💡 **流程指导**: 下一步需要调用 record_challenge() 进行挑战"
        elif function_name == "record_challenge":
            enhanced_result += "\n\n💡 **流程指导**: 下一步需要调用 complete_adaptation() 完成适应"
        elif function_name == "complete_adaptation":
            enhanced_result += "\n\n💡 **流程指导**: HCA循环完成，可以开始新假设或形成结论"
        
        # 漏洞分析相关的安全提醒
        if function_name in ["read_file", "shell"] and "security" in str(arguments).lower():
            enhanced_result += "\n\n🔍 **安全分析**: 关注输入验证、权限检查、边界条件等潜在漏洞点"
        
        return enhanced_result
    
    return result

def get_icla_test_agent(
    model_id: str = "gpt-4o",
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    debug_mode: bool = True,
) -> Agent:
    """创建基于 ICLA 框架的测试代理"""
    
    shell_tools = ShellTools(base_dir=HARDCODED_WORKSPACE_PATH)
    file_tools = FileTools(base_dir=HARDCODED_WORKSPACE_PATH)
    
    icla_tools = [
        # 新架构核心工具
        view_current_state,
        view_hca_history,
        start_new_hypothesis,
        record_challenge,
        complete_adaptation,
        validate_conclusion_readiness,
        
        # 传统工具（兼容性）
        update_main_md,
        calculate_intrinsic_reward, 
        terminate_with_report,
        create_archive_file,
        
        # 基础工具
        shell_tools,
        file_tools
    ]
    
    additional_context = f"<context>目标项目位于: {str(HARDCODED_WORKSPACE_PATH)}。所有相对路径操作都相对于此路径。</context>"
    
    agent_description = dedent(f"""\
        你是一个基于 ICLA (In-Context Learning Reinforcement Agent) 框架的自主代理。
        你的核心能力是通过假设-挑战-适应 (HCA) 循环进行自主学习和探索。
        
        你的任务是分析位于 {str(HARDCODED_WORKSPACE_PATH)} 的代码项目，发现潜在的安全漏洞。
        你必须通过内在奖励机制驱动自己的探索，不断提出假设、积极挑战它们，并从结果中学习。
        """)
    
    initial_session_state = {
        "main_md_content": dedent(f"""\
            # 自主审计日志: {str(HARDCODED_WORKSPACE_PATH)}
            # 时间步: 0
            # 累积奖励: 0.0
            
            ## 核心使命
            通过静态分析发现高置信度的安全漏洞。
            
            ## HCA序列状态
            - 当前假设编号: 准备H-01
            - 当前阶段: 环境探索
            
            ## 初始计划
            1. 了解目标项目的整体结构和部署环境
            2. 基于观察提出第一个具体假设 (H-01)
            3. 立即进入Challenge阶段验证H-01
            4. Adapt阶段给出结论和奖励，然后开始H-02
            
            ## 已完成假设
            暂无
            
            ## 最近奖励日志
            暂无
            """),
        "cumulative_reward": 0.0,
        "total_steps": 0,
        "reward_history": [],
        "archive_files": {},
        "task_completed": False,
        
        # 新架构状态结构
        "runtime_state": {
            "current_phase": "hypothesis",
            "hypothesis_count": 1,
            "current_hypothesis": {},
            "current_challenge": {},
            "current_adaptation": {},
            "phase_guidance": {
                "next_suggested_action": "分析项目结构，提出第一个安全假设",
                "available_actions": ["start_new_hypothesis", "view_current_state"],
                "gentle_reminder": "记住：假设必须经过H→C→A完整流程才能用于结论"
            }
        },
        
        "working_memory": {
            "hca_history": [],
            "learning_insights": [],
            "challenge_patterns": {
                "assumption_challenges": [],
                "evidence_challenges": [],
                "logic_challenges": [],
                "bias_challenges": []
            }
        }
    }
    
    return Agent(
        name="ICLA-TestAgent",
        agent_id="icla_test_agent_v1",
        user_id=user_id,
        session_id=session_id,
        model=OpenAILike(id=model_id, base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY),
        tools=icla_tools,
        tool_hooks=[icla_orchestrator_hook],  # 🎯 核心协调器钩子！
        storage=PostgresAgentStorage(table_name="icla_test_sessions", db_url=db_url),
        description=agent_description,
        instructions=[
            "# ICLA Agent - 新架构：平衡自主性与流程完整性",
            "",
            "## 核心哲学",
            "你是一个具有自主权的ICLA代理。你可以看到透明的HCA状态，使用简单的工具，所有决策都由你的推理驱动。",
            "",
            "## HCA流程约束（关键）",
            "【重要】假设不能直接跳到结论！要形成有效结论的唯一路径：",
            "H（start_new_hypothesis）→ C（record_challenge）→ A（complete_adaptation）→ 结论可用",
            "",
            "❌ **禁止**: 分析代码后直接得出结论",
            "✅ **正确**: 提出假设 → 寻找反驳证据 → 基于证据调整 → 得出结论",
            "",
            "## 你的自主权范围",
            "✅ **你可以自由决定**:",
            "- 何时开始分析（用shell/file工具探索代码）",
            "- 假设的具体内容和深度",
            "- 挑战的角度和方式",
            "- 适应的调整方向",
            "",
            "❌ **你不能跳过**:",
            "- 如果要得出\"发现漏洞\"的结论，必须有adapted状态的假设支持",
            "- 挑战阶段：必须寻找反驳证据，不能只验证假设正确性",
            "- 适应阶段：必须基于挑战结果进行反思调整",
            "",
            "## 新架构工具集",
            "**状态透明工具**:",
            "- **view_current_state()**: 查看当前HCA状态和进度",
            "- **view_hca_history()**: 查看HCA历史循环记录",
            "",
            "**状态更新工具**:",
            "- **start_new_hypothesis(content)**: 开始新假设",
            "- **record_challenge(type, content)**: 记录挑战内容", 
            "- **complete_adaptation(changes, reasoning)**: 完成适应",
            "- **validate_conclusion_readiness()**: 验证是否可以形成结论",
            "",
            "**传统工具**:",
            "- **calculate_intrinsic_reward()**: 评估学习成果",
            "- **terminate_with_report()**: 发现漏洞时提交报告",
            "",
            "## 状态信息获取",
            "⚠️ **重要**: 你在工具调用过程中看不到session_state！",
            "必须主动调用 view_current_state() 来获取完整状态信息。",
            "",
            "**状态信息解读**:",
            "- current_phase: 当前处于哪个HCA阶段 (hypothesis/challenge/adapt)",
            "- hypothesis_count: 当前假设编号 (从1开始)",
            "- current_hypothesis.status: 假设状态 (pending_challenge/challenged/adapted)",
            "",
            "**关键状态判断** (通过view_current_state()获取):",
            "- 如果status = 'adapted' → 该假设可用于结论",
            "- 如果status = 'pending_challenge' → 需要挑战",
            "- 如果status = 'challenged' → 需要适应",
            "",
            "## 核心使命：漏洞发现",
            "通过静态分析发现高置信度的安全漏洞。",
            "",
            "## HCA流程的三个必需阶段",
            "🔬 **1. 假设阶段**: 分析代码后，形成具体安全假设",
            "   - 调用: start_new_hypothesis('具体假设内容')",
            "   - 状态变化: pending_challenge → 无法用于结论",
            "",
            "⚔️ **2. 挑战阶段**: 寻找反驳证据，证明假设错误",
            "   - 调用: record_challenge('evidence', '找到的反驳证据')",
            "   - 状态变化: challenged → 仍无法用于结论",
            "",
            "🧠 **3. 适应阶段**: 基于挑战结果进行反思和调整",
            "   - 调用: complete_adaptation('调整内容', '推理过程')",
            "   - 状态变化: adapted → 可以用于结论",
            "",
            "## 明确的决策指导",
            "**什么时候必须做什么**:",
            "1. 想了解当前状态 → 调用 view_current_state()",
            "2. 准备开始新假设 → 调用 start_new_hypothesis()",
            "3. 需要挑战假设 → 调用 record_challenge()",
            "4. 完成挑战要适应 → 调用 complete_adaptation()",
            "5. 想形成最终结论 → 先调用 validate_conclusion_readiness()",
            "6. 确认发现漏洞 → 调用 terminate_with_report()",
            "",
            "**重要约束**: 假设状态必须是 'adapted' 才能用于最终结论！",
            "",
            "## 工作记忆说明",
            "你的session_state中的main_md_content包含工作记忆内容。",
            "这是你分析过程的累积记录，可以参考但不是决策依据。",
            "真正的决策依据是runtime_state中的结构化状态信息。",
            "",
            "## 状态驱动的决策流程",
            "**第一步**: 必须调用 view_current_state() 了解当前状态",
            "**第二步**: 根据返回的状态信息决定下一步行动：",
            "",
            "**如果没有current_hypothesis或ID为'尚未创建'**:",
            "→ 分析代码后调用 start_new_hypothesis('具体假设')",
            "",
            "**如果status = 'pending_challenge'**:",
            "→ 必须调用 record_challenge('类型', '反驳证据')",
            "→ 类型选择: assumption/evidence/logic/bias",
            "",
            "**如果status = 'challenged'**:",
            "→ 必须调用 complete_adaptation('调整内容', '推理过程')",
            "",
            "**如果status = 'adapted'**:",
            "→ 可以开始新假设或调用 validate_conclusion_readiness()",
            "",
            "⚠️ **重要**: 每次做决策前都要先调用 view_current_state()！",
            "",
            "## 安全分析约束（重要）",
            "⚠️ **静态分析环境约束**:",
            "- 只能进行代码文本分析，禁止网络请求(curl/wget等)",
            "- 无法执行动态测试或运行目标程序",
            "- 只能通过read_file和shell的静态命令(find/grep等)获取信息",
            "- 所有漏洞验证必须基于代码逻辑推理，不能依赖实际执行",
            "",
            "🔍 **安全分析重点**:",
            "- 输入验证漏洞（SQL注入、XSS、命令注入等）",
            "- 权限检查缺失",
            "- 边界条件处理不当",
            "- 敏感信息泄露",
            "- 加密和认证问题",
            "",
            "## Session State结构说明",
            "你的session_state包含以下关键信息：",
            "```",
            "runtime_state: {",
            "  current_phase: 'hypothesis'|'challenge'|'adapt',",
            "  hypothesis_count: 数字,",
            "  current_hypothesis: {",
            "    status: 'pending_challenge'|'challenged'|'adapted'",
            "  }",
            "}",
            "working_memory: { hca_history: [...] }",
            "main_md_content: '工作记忆文本'",
            "```"
            "",
            "## 核心原则",
            "1. **状态驱动决策**: 始终查看session_state决定下一步，不要猜测",
            "2. **流程完整性**: 要得出\"发现漏洞\"结论，必须有adapted状态的假设",
            "3. **安全为先**: 发现真正的安全漏洞，而不是理论可能性",
            "4. **透明操作**: 使用view_current_state()随时了解当前状态"
        ],
        additional_context=additional_context,
        session_state=initial_session_state,
        debug_mode=debug_mode,
        show_tool_calls=True,
        markdown=True,
        add_history_to_messages=True,
        num_history_responses=8,
        enable_agentic_memory=True,
        add_state_in_messages=True,
        read_chat_history=True
    )

async def main():
    """测试 ICLA 代理"""
    print("--- ICLA 测试代理示例 ---")
    icla_agent = get_icla_test_agent(user_id="icla_test_user", model_id="deepseek/deepseek-r1-0528:deepinfra")
    
    test_prompts = [
        "开始你的漏洞发现任务。你可以先调用view_current_state()查看状态，然后分析项目代码。",
        "基于你的代码分析，现在提出第一个安全假设并进入完整的HCA流程。",
        "检查你的HCA流程状态，确保每个假设都经过了挑战和适应阶段。",
        "如果发现了潜在漏洞，验证结论就绪性后提交报告；否则继续下一个假设。"
    ]
    
    print(f"ICLA Agent 已初始化，会话ID: {icla_agent.session_id}")
    print(f"目标项目路径: {str(HARDCODED_WORKSPACE_PATH)}")
    
    for i, prompt_text in enumerate(test_prompts):
        print(f"\n--- 测试提示 {i+1}: ---")
        print(f">>> {prompt_text}")
        print("--- 代理响应: ---")
        await pprint_run_response(icla_agent, prompt_text)
        
        if icla_agent.session_state.get("task_completed", False):
            print("\n🎉 任务已由代理自主完成！")
            break
        
        current_reward = icla_agent.session_state.get("cumulative_reward", 0.0)
        current_steps = icla_agent.session_state.get("total_steps", 0)
        print(f"\n📊 当前状态: 奖励={current_reward:.2f}, 步数={current_steps}")
    
    print("\n--- ICLA 测试完成 ---")

if __name__ == "__main__":
    print(f"初始化 ICLA 测试代理...")
    print(f"工作路径: {str(HARDCODED_WORKSPACE_PATH)}")
    print("此代理将展示自主学习、HCA循环和内在奖励机制。")
    
    import asyncio
    asyncio.run(main()) 

 

 