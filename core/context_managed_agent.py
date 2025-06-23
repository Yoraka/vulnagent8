"""
智能上下文管理的Agent类
实现token监控、HCA历史记录和自动截断功能
"""

from typing import Optional, Dict, Any, List, Union, Callable, Iterator, Tuple, Type, AsyncIterator, Sequence
import json
from datetime import datetime
from agno.agent import Agent
from agno.models.base import Model
from agno.models.response import ModelResponse
from agno.models.message import Message
from agno.run.response import RunResponse
from agno.tools import tool
from agno.utils.log import logger, set_log_level_to_debug  # 使用Agno的logger系统
from pydantic import BaseModel
from agno.media import Audio, Image, Video, File
import time
import threading


class ContextManagedAgent(Agent):
    """
    重写的Agent类，实现智能上下文管理
    
    核心功能：
    1. Token使用监控 (70%提醒, 80%截断)
    2. HCA历史记录完整保存
    3. 智能消息截断 (保留50%最新内容)
    4. 上下文进度提醒
    5. 可配置的工具调用阻断阈值
    
    可配置参数：
    - max_context_tokens: 最大上下文token数，默认25000
    - warning_threshold: 警告阈值（比例），默认0.7（70%）
    - truncate_threshold: 截断阈值（比例），默认0.8（80%）
    - tool_block_threshold: 工具调用阻断阈值（比例），默认0.85（85%）
    - keep_ratio: 截断时保留消息的比例，默认0.5（50%）
    - summary_max_chars: 摘要消息最大字符数，默认1200
    """
    
    def __init__(self, *args, **kwargs):
        """初始化ContextManagedAgent"""
        # 使用多种方式确保调试信息能被看到
        print("=" * 80)
        print("🎯 ContextManagedAgent.__init__ 开始!")
        print("=" * 80)
        
        # 使用标准logging而不是loguru
        import logging
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)
        
        self.max_context_tokens = kwargs.pop('max_context_tokens', 25000)
        self.warning_threshold = kwargs.pop('warning_threshold', 0.7)
        self.truncate_threshold = kwargs.pop('truncate_threshold', 0.8)
        self.keep_ratio = kwargs.pop('keep_ratio', 0.5)
        # 🔥 新增：工具调用阻断阈值，默认85%，超过此阈值会要求先压缩上下文
        self.tool_block_threshold = kwargs.pop('tool_block_threshold', 0.85)
        
        # -------  新增: tool 消息压缩 / 丢弃策略可调参数  -------
        # 保留最近 N 条 tool 消息的完整正文，其余可被压缩或删除
        self.keep_recent_tool_messages = kwargs.pop('keep_recent_tool_messages', 2)
        # 压缩后 tool 消息最大字符数 (≈ token ×2)
        self.max_tool_message_chars = kwargs.pop('max_tool_message_chars', 1200)
        # ---- 新增: 摘要消息最大长度，可通过构造参数 summary_max_chars 调整 ----
        self.summary_max_chars = kwargs.pop('summary_max_chars', 1200)
        # 是否保留旧版 _ai_summarize_history_with_context_protection 流程
        self.use_legacy_summary = kwargs.pop('use_legacy_summary', False)
        
        logger.critical(f"🎯 上下文管理配置:")
        logger.critical(f"   max_context_tokens: {self.max_context_tokens}")
        logger.critical(f"   warning_threshold: {self.warning_threshold*100:.1f}%")
        logger.critical(f"   truncate_threshold: {self.truncate_threshold*100:.1f}%")
        logger.critical(f"   tool_block_threshold: {self.tool_block_threshold*100:.1f}%")
        logger.critical(f"   keep_ratio: {self.keep_ratio*100:.1f}%")
        
        # 初始化状态
        self._warning_sent = False
        self._last_warning_sent = False
        self._last_run_token_usage = 0  # 记录上一次运行的token使用量
        
        # 调用父类初始化
        logger.critical(f"🎯 调用super().__init__...")
        super().__init__(*args, **kwargs)
        logger.critical(f"🎯 super().__init__完成!")
        
        # v1.6+ 版本通过 RunResponse.metrics 提供完整 token/cost 数据，
        # 已不需要 monkey-patch 模型方法；保留日志，说明已跳过。
        if hasattr(self, 'model') and self.model:
            logger.debug("🔧 跳过 _patch_model_methods，直接使用 metrics")
        else:
            logger.debug("🔧 无 model 可用，亦无需打补丁")
        
        # 初始化session_state
        if not hasattr(self, 'session_state'):
            self.session_state = {}
            
        # 确保上下文管理状态存在并初始化所有必要字段
        if self.session_state is None:
            self.session_state = {}
        if 'context_management' not in self.session_state:
            self.session_state['context_management'] = {}
            
        context_management = self.session_state['context_management']
        # 使用字典的get方法设置默认值，这样不会覆盖已有的值
        context_management.setdefault('warning_sent', False)
        context_management.setdefault('last_warning_sent', False)
        context_management.setdefault('total_tokens_calculated', 0)
        context_management.setdefault('truncations_performed', 0)
        context_management.setdefault('last_calculation_time', None)
        context_management.setdefault('last_run_token_usage', 0)
        context_management.setdefault('truncation_count', 0)
        
        # 确保session_state中有HCA历史记录结构
        self._ensure_hca_history_structure()
        
        # 添加HCA查询工具
        self._add_hca_tools()
        
        # 添加全局Message.log补丁，确保所有assistant日志都会触发token监控
        self._patch_message_log()
        
        # 运行期消息缓冲，支持单轮 run 内即时截断
        self._live_messages: List[Message] = []
        # TODO(上下文管理优化): 计划后续完全移除 _live_messages 缓冲区，直接统一操作 run_messages.messages，以简化逻辑并避免数据来源混乱。

        # ------------------------------------------------------------------
        # 🛠️  新增: tool 消息压缩 / 丢弃 辅助方法
        # ------------------------------------------------------------------

        def _capture_tool_result(function_name: str, next_func: Callable, arguments: Dict[str, Any]):  # type: ignore
            """Agno tool_hook: 记录工具调用结果"""
            logger.debug(f"🔧 capture_tool_result: 执行工具 {function_name} args={arguments}")

            # 👉 若当前执行的工具就是 summarize_context，则直接放行，不做超限拦截
            if function_name == "summarize_context":
                try:
                    return next_func(**(arguments or {}))
                except Exception as _tool_err:
                    logger.error(f"❌ summarize_context 执行失败: {_tool_err}")
                    raise

            # 👉 对其它工具进行上下文超限检查
            try:
                agent_obj = None
                if isinstance(arguments, dict):
                    agent_obj = arguments.get("agent")
                if agent_obj is None:
                    # 若工具函数签名不含 agent 参数，则直接使用闭包中的 self
                    agent_obj = self
                if hasattr(agent_obj, "_get_actual_token_usage"):
                    usage = agent_obj._get_actual_token_usage(is_new_run=True)

                    # 🔄 若当前 run 尚未完成，metrics 可能取不到；改用 session_state 的上一次值
                    if usage.get("total_tokens", 0) == 0:
                        cm = agent_obj.session_state.get("context_management", {})
                        last_tokens = cm.get("last_run_token_usage", 0)
                        usage["total_tokens"] = last_tokens
                        usage["usage_percentage"] = (
                            (last_tokens / agent_obj.max_context_tokens) * 100
                            if agent_obj.max_context_tokens > 0 else 0.0
                        )

                    # 🔥 使用可配置的工具调用阻断阈值，避免无限工具调用循环
                    if usage.get("usage_percentage", 0) >= (agent_obj.tool_block_threshold * 100):
                        limit_chars = getattr(agent_obj, "summary_max_chars", 1200)
                        
                        # 直接要求摘要，不使用延迟截断
                        return (
                            f"❌ 当前上下文已使用 {usage['usage_percentage']:.1f}% "
                            f"({usage['total_tokens']}/{agent_obj.max_context_tokens})，为保证后续分析，请先调用\n"
                            f"summarize_context(summary=\"<不超过{limit_chars}字的对话摘要>\") 压缩上下文后再重试本工具。"
                        )
            except Exception as _chk_err:
                logger.debug(f"⚠️ 超限检查失败: {_chk_err}")

            # 执行原工具并获取原始结果
            raw_result = next_func(**(arguments or {}))  # 执行原工具

            try:
                raw_str = str(raw_result)
                logger.debug(f"🔧 capture_tool_result: 工具 {function_name} 返回长度 {len(raw_str)} 字符")
            except Exception:
                logger.debug(f"🔧 capture_tool_result: 工具 {function_name} 返回不可序列化结果")

            # 返回原始结果，不截断（让最新的工具调用保持完整）
            return raw_result

        # 注册到 agent 的 tool_hooks 列表
        if not hasattr(self, "tool_hooks") or self.tool_hooks is None:
            self.tool_hooks = []
        self.tool_hooks.append(_capture_tool_result)

        # ---- 将 hook 绑定到已注册的所有 tool / Toolkit.Function ----
        try:
            from agno.tools.function import Function as _AgnoFunction  # type: ignore

            for _t in (self.tools or []):
                try:
                    # 若为 Toolkit，遍历内部 functions (dict.values)
                    if hasattr(_t, "functions") and isinstance(getattr(_t, "functions"), dict):
                        for _fname, _f in _t.functions.items():  # type: ignore
                            if isinstance(_f, _AgnoFunction):
                                _f.tool_hooks = (_f.tool_hooks or []) + [_capture_tool_result]
                    # Toolkit.functions 若为 list（兼容老版本）
                    elif hasattr(_t, "functions") and isinstance(getattr(_t, "functions"), list):
                        for _f in _t.functions:  # type: ignore
                            if isinstance(_f, _AgnoFunction):
                                _f.tool_hooks = (_f.tool_hooks or []) + [_capture_tool_result]
                    # 单个 Function 或 @tool 包装后的对象
                    elif isinstance(_t, _AgnoFunction):
                        _t.tool_hooks = (_t.tool_hooks or []) + [_capture_tool_result]
                except Exception as _bind_err:  # pragma: no cover
                    logger.debug(f"⚠️ 绑定 tool_hook 失败: {_bind_err}")
        except Exception:
            pass
    
    def _ensure_hca_history_structure(self):
        """确保session_state中有完整的HCA历史记录结构"""
        if not hasattr(self, 'session_state') or self.session_state is None:
            self.session_state = {}
        
        if self.session_state is None:
            self.session_state = {}
        if 'hca_complete_history' not in self.session_state:
            self.session_state['hca_complete_history'] = []
        
        if 'context_management' not in self.session_state:
            self.session_state['context_management'] = {
                'truncation_count': 0,
                'last_truncation_time': None,
                'total_tokens_processed': 0
            }
    
    def _add_hca_tools(self):
        """添加HCA历史查询工具"""
        
        @tool
        def query_hca_history(agent: ContextManagedAgent, keyword: str = "", tail: int = 10) -> str:
            """
            查询HCA历史记录
            
            Args:
                keyword: 搜索关键词，为空则显示所有记录
                tail: 显示最近N条记录，默认10条，设为-1显示全部
            """
            history = agent.session_state.get('hca_complete_history', [])
            
            if not history:
                return "📚 **HCA历史记录**: 暂无记录"
            
            # 如果有关键词，先过滤
            if keyword.strip():
                filtered_history = []
                keyword_lower = keyword.lower()
                for record in history:
                    # 在所有字段中搜索关键词
                    searchable_text = f"{record.get('hypothesis', '')} {record.get('challenge', '')} {record.get('adaptation', '')} {record.get('evidence', '')}".lower()
                    if keyword_lower in searchable_text:
                        filtered_history.append(record)
                history = filtered_history
                
                if not history:
                    return f"📚 **HCA历史记录**: 未找到包含'{keyword}'的记录"
            
            # 确定显示范围
            if tail == -1:
                display_history = history
                title = f"📚 **完整HCA历史记录** (共{len(history)}条)"
            else:
                display_history = history[-tail:] if len(history) > tail else history
                title = f"📚 **最近{len(display_history)}条HCA记录** (共{len(history)}条)"
            
            if keyword.strip():
                title = f"📚 **包含'{keyword}'的HCA记录** (共{len(display_history)}条)"
            
            result = f"{title}\n\n"
            
            for i, record in enumerate(display_history, 1):
                result += f"**{record.get('id', f'#{i}')}** - {record.get('timestamp', 'N/A')}\n"
                result += f"- 假设: {record.get('hypothesis', 'N/A')}\n"
                result += f"- 挑战: {record.get('challenge', 'N/A')}\n"
                result += f"- 适应: {record.get('adaptation', 'N/A')}\n"
                result += f"- 状态: {record.get('status', 'N/A')}\n"
                if record.get('evidence'):
                    result += f"- 证据: {record.get('evidence')[:100]}...\n"
                result += "---\n"
            
            # 添加统计信息
            completed = len([r for r in history if r.get('status') == 'completed'])
            result += f"\n📊 **统计**: 总计{len(history)}条，已完成{completed}条"
            
            return result
        
        # 将工具添加到agent
        if not hasattr(self, 'tools') or self.tools is None:
            self.tools = []
        elif not isinstance(self.tools, list):
            self.tools = list(self.tools) if self.tools else []
        self.tools.append(query_hca_history)
        
        # 保存工具函数的引用
        self._hca_query_tool = query_hca_history

        # ------------------------------------------------------------------
        # ✨ 新增: 上下文摘要工具
        # ------------------------------------------------------------------

        @tool
        def summarize_context(agent: ContextManagedAgent, summary: str) -> str:
            """⚙️ **上下文压缩工具**

            用途：在对话 token 占用率接近上限时，由 LLM 调用本工具提交 *简要摘要* 以替换过往冗长对话。

            约束：
            1. 入参必须为 JSON 格式，如：`{"summary": "这里是不超过 N 字的总结"}`
            2. 总结应专注于**对话要点**与**阶段性结论**，避免生成最终报告。
            3. 字数 ≤ `agent.summary_max_chars`（默认 1200）。
            """

            max_len = getattr(agent, "summary_max_chars", 1200)

            # 基础校验：摘要不得过长
            if len(summary) > max_len:
                return f"❌ 摘要过长，请压缩到 {max_len} 字以内再重试"

            from agno.models.message import Message

            # 确保 messages 容器存在
            if not hasattr(agent, "messages") or agent.messages is None:
                # 尝试回退到 _live_messages
                fallback_msgs = list(getattr(agent, "_live_messages", []))
                agent.messages = fallback_msgs

            if not isinstance(agent.messages, list):
                # 若 messages 类型异常，重新初始化
                agent.messages = list(agent.messages) if agent.messages else []

            # 🔥 立即执行截断，利用完整性保护机制保护工具调用链
            if hasattr(agent, "_truncate_context_messages"):
                success = agent._truncate_context_messages(force=True)
                if success:
                    # 截断成功后，插入摘要消息
                    summary_msg = Message(role="assistant", content=f"[Summary]\n{summary}")
                    
                    # 插入到适当位置（在system消息之后，其他消息之前）
                    if hasattr(agent, "messages") and agent.messages:
                        insert_pos = 1 if agent.messages and getattr(agent.messages[0], "role", "") == "system" else 0
                        agent.messages.insert(insert_pos, summary_msg)
                    
                    if hasattr(agent, "_live_messages") and agent._live_messages:
                        insert_pos = 1 if agent._live_messages and getattr(agent._live_messages[0], "role", "") == "system" else 0
                        agent._live_messages.insert(insert_pos, summary_msg)
                    
                    # 记录统计信息
                    agent.session_state.setdefault("context_management", {})
                    cm = agent.session_state["context_management"]
                    cm["truncation_count"] = cm.get("truncation_count", 0) + 1
                    cm["last_truncation_time"] = datetime.now().isoformat()
                    
                    return "✅ 已立即执行上下文压缩并插入摘要"
                else:
                    return "⚠️ 截断失败，上下文未能有效压缩"
            else:
                return "❌ 截断功能不可用"

        # 将 summarize_context 工具加入 agent
        self.tools.append(summarize_context)
    
    def _patch_model_methods(self):
        """给model打补丁，拦截_process_model_response方法"""
        logger.debug(f"🔧 ContextManagedAgent: 给Model打补丁 - {type(self.model).__name__}({self.model.id})")
        logger.debug(f"🔧 Model对象: {self.model}")
        logger.debug(f"🔧 Model有_process_model_response: {hasattr(self.model, '_process_model_response')}")
        logger.debug(f"🔧 Model有_aprocess_model_response: {hasattr(self.model, '_aprocess_model_response')}")
        
        if not hasattr(self.model, '_process_model_response'):
            logger.debug(f"❌ Model没有_process_model_response方法，跳过补丁")
            return
        if not hasattr(self.model, '_aprocess_model_response'):
            logger.debug(f"❌ Model没有_aprocess_model_response方法，跳过补丁")
            return
            
        original_process = self.model._process_model_response
        original_aprocess = self.model._aprocess_model_response
        logger.debug(f"🔧 原始方法获取成功: {original_process}, {original_aprocess}")
        
        logger.debug("🔧 步骤E: 创建补丁函数")
        def patched_sync(*args, **kwargs):
            # 简洁包装，仅保持原逻辑，避免重复token监控
            logger.debug("🚀 同步补丁调用")
            return original_process(*args, **kwargs)
        
        async def patched_async(*args, **kwargs):
            logger.debug("🚀 异步补丁调用")
            return await original_aprocess(*args, **kwargs)
        
        # 应用补丁
        self.model._process_model_response = patched_sync
        self.model._aprocess_model_response = patched_async
        logger.debug(f"✅ 补丁应用成功!")
        logger.debug(f"✅ 新的_process_model_response: {self.model._process_model_response}")
        logger.debug(f"✅ 新的_aprocess_model_response: {self.model._aprocess_model_response}")
    
    def _safe_get_first(self, value, default=0):
        """安全获取列表中的第一个值或直接返回数值"""
        if isinstance(value, list) and len(value) > 0:
            return value[0]
        elif isinstance(value, (int, float)):
            return value
        return default

    def _get_actual_token_usage(self, is_new_run: bool = False) -> Dict[str, Union[int, float]]:
        """获取实际token使用情况
        
        Args:
            is_new_run: 是否是新运行开始时的检查
        """
        try:
            # 从run_response.metrics获取数据
            if hasattr(self, 'run_response') and self.run_response and self.run_response.metrics:
                metrics = self.run_response.metrics
                logger.debug(f"从run_response.metrics获取数据: {metrics}")
                    
                total_tokens = self._safe_get_first(metrics.get('total_tokens', 0))
                usage_percentage = (total_tokens / self.max_context_tokens) * 100 if self.max_context_tokens > 0 else 0.0
                
                return {
                    'total_tokens': total_tokens,
                    'usage_percentage': usage_percentage,
                    'data_source': 'metrics'
                }
                
            # 只在非新运行时显示警告
            if not is_new_run:
                logger.warning("⚠️ 无法从metrics获取有效的token数据")
            return {'total_tokens': 0, 'usage_percentage': 0, 'data_source': 'no_metrics_available'}
            
        except Exception as e:
            logger.error(f"❌ 获取token使用数据失败: {str(e)}")
            return {'total_tokens': 0, 'usage_percentage': 0, 'data_source': 'error'}

    def _calculate_context_usage(self) -> Dict[str, Any]:
        """计算当前上下文使用情况 - 已废弃，使用_get_actual_token_usage代替"""
        # 🔥 废弃方法：直接调用正确的token计算方法
        logger.warning("⚠️ _calculate_context_usage已废弃，请使用_get_actual_token_usage")
        usage_info = self._get_actual_token_usage()
        # 补充缺失的字段以保持兼容性
        usage_info.update({
            'usage_percentage': (usage_info.get('total_tokens', 0) / self.max_context_tokens) * 100 if self.max_context_tokens > 0 else 0.0,
            'remaining_tokens': max(0, self.max_context_tokens - usage_info.get('total_tokens', 0)),
            'should_warn': False,
            'should_truncate': False
        })
        usage_info['max_tokens'] = self.max_context_tokens
        return usage_info
    
    def _add_context_warning_to_result(self, original_result: str, usage_info: Dict[str, Any]) -> str:
        """在工具结果中添加上下文使用警告和状态信息"""
        context_status = ""
        
        # 获取截断统计信息
        truncation_count = self.session_state.get('context_management', {}).get('truncation_count', 0)
        last_truncation = self.session_state.get('context_management', {}).get('last_truncation_time')
        
        # 📊 始终显示上下文状态
        context_status += f"\n\n📊 **上下文管理状态**: {usage_info['total_tokens']}/{self.max_context_tokens} tokens ({usage_info['usage_percentage']:.1f}%)"
        
        if truncation_count > 0:
            context_status += f"\n🔄 **截断历史**: 已执行{truncation_count}次截断，最近一次: {last_truncation[:19] if last_truncation else 'N/A'}"
            context_status += f"\n💡 **提醒**: 详细对话历史已压缩，可用工具查询HCA历史获取分析进度"
        
        # ⚠️ 警告阶段 (70%-80%)
        if usage_info['usage_percentage'] >= (self.warning_threshold * 100):
            warning = f"""
⚠️ **上下文使用警告**: 已使用{usage_info['usage_percentage']:.1f}%
🔧 **机制说明**: 下一轮运行前将自动压缩最旧的对话历史，当前HCA状态不受影响
📚 **数据保护**: session_state中的HCA历史、奖励等核心数据完全安全
剩余容量: {usage_info['remaining_tokens']} tokens
"""
            context_status += warning
        
        return f"{original_result}{context_status}"
    
    def _create_truncation_summary(self, truncated_messages: List, count: int) -> Any:
        """创建被截断消息的摘要"""
        # 提取关键信息
        hca_findings = []
        tool_calls = []
        important_discoveries = []
        
        for msg in truncated_messages:
            content = str(msg.content) if msg.content else ""
            
            # 提取HCA相关信息
            if any(keyword in content.lower() for keyword in ['h-', 'hypothesis', '假设', 'cvss', '漏洞']):
                hca_findings.append(content[:200] + "..." if len(content) > 200 else content)
            
            # 提取工具调用
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    try:
                        # 兼容多种形态（对象或 dict）
                        if isinstance(tc, dict):
                            _fn_data = tc.get("function", {}) if isinstance(tc.get("function"), dict) else {}
                            name = _fn_data.get("name") or tc.get("tool_name") or tc.get("name")
                            args = _fn_data.get("arguments") or tc.get("tool_args") or tc.get("arguments")
                        else:
                            # 对象形式
                            fn_obj = getattr(tc, "function", None)
                            name = getattr(fn_obj, "name", None) or getattr(tc, "tool_name", None)
                            args = getattr(fn_obj, "arguments", None) or getattr(tc, "tool_args", None)
                        if name:
                            tool_calls.append(f"{name}({args})" if args else name)
                    except Exception:
                        # 忽略解析失败的条目，确保摘要生成不中断
                        continue
            
            # 提取重要发现
            if any(keyword in content.lower() for keyword in ['发现', 'found', 'vulnerability', 'exploit']):
                important_discoveries.append(content[:150] + "..." if len(content) > 150 else content)
        
        # 构建摘要消息
        summary_content = f"""
📋 **上下文压缩摘要** (截断了{count}条消息)
截断时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🔍 **HCA相关发现** ({len(hca_findings)}条):
{chr(10).join(f"- {finding}" for finding in hca_findings[:5])}
{'...(更多内容已截断)' if len(hca_findings) > 5 else ''}

🛠️ **工具调用记录** ({len(tool_calls)}次):
{chr(10).join(f"- {call}" for call in tool_calls[:10])}
{'...(更多调用已截断)' if len(tool_calls) > 10 else ''}

💡 **重要发现** ({len(important_discoveries)}条):
{chr(10).join(f"- {discovery}" for discovery in important_discoveries[:3])}
{'...(更多发现已截断)' if len(important_discoveries) > 3 else ''}

⚠️ **注意**: 详细的HCA历史可通过 query_hca_history() 工具查询
"""
        
        # 创建摘要消息对象 (使用标准Message类)
        from agno.models.message import Message
        return Message(role="system", content=summary_content)
    
    def record_hca_to_history(self, hca_data: Dict[str, Any]):
        """记录HCA数据到完整历史中"""
        self._ensure_hca_history_structure()
        
        hca_record = {
            'id': hca_data.get('id', f"HCA-{len(self.session_state['hca_complete_history']) + 1:03d}"),
            'timestamp': datetime.now().isoformat(),
            'hypothesis': hca_data.get('hypothesis', ''),
            'challenge': hca_data.get('challenge', ''),
            'adaptation': hca_data.get('adaptation', ''),
            'status': hca_data.get('status', 'pending'),
            'evidence': hca_data.get('evidence', ''),
            'cvss_score': hca_data.get('cvss_score', None),
            'files_analyzed': hca_data.get('files_analyzed', []),
            'tools_used': hca_data.get('tools_used', [])
        }
        
        self.session_state['hca_complete_history'].append(hca_record)
        logger.info(f"📚 **HCA记录已保存**: {hca_record['id']}")
    

    
    async def arun(self, *args, **kwargs):
        """重写异步arun方法，在运行结束后进行上下文管理"""
        if not hasattr(self, 'session_state'):
            self.session_state = {}
        if 'context_management' not in self.session_state:
            self.session_state['context_management'] = {}
        try:
            current_usage = self._get_actual_token_usage(is_new_run=True)
            if current_usage['total_tokens'] >= (self.max_context_tokens * self.truncate_threshold):
                logger.info(f"🔄 上一次运行token使用率达到{current_usage['usage_percentage']:.1f}%，执行截断")
                self._truncate_context_messages()
        except Exception as e:
            logger.error(f"❌ 运行前检查失败: {str(e)}")
        response = await super().arun(*args, **kwargs)
        try:
            current_usage = self._get_actual_token_usage()
            self.session_state['context_management']['last_run_token_usage'] = current_usage['total_tokens']
        except Exception as e:
            logger.error(f"❌ 运行后更新失败: {str(e)}")
        return response

    def run(self, message: str = None, **kwargs) -> RunResponse:
        """重写run方法，在运行结束后进行上下文管理"""
        if not hasattr(self, 'session_state'):
            self.session_state = {}
        if 'context_management' not in self.session_state:
            self.session_state['context_management'] = {}
        try:
            current_usage = self._get_actual_token_usage(is_new_run=True)
            if current_usage['total_tokens'] >= (self.max_context_tokens * self.truncate_threshold):
                logger.info(f"🔄 上一次运行token使用率达到{current_usage['usage_percentage']:.1f}%，执行截断")
                self._truncate_context_messages()
        except Exception as e:
            logger.error(f"❌ 运行前检查失败: {str(e)}")
        response = super().run(message, **kwargs)
        try:
            current_usage = self._get_actual_token_usage()
            self.session_state['context_management']['last_run_token_usage'] = current_usage['total_tokens']
        except Exception as e:
            logger.error(f"❌ 运行后更新失败: {str(e)}")
        return response

    def _handle_post_response(self, run_response: RunResponse):
        """在每个 run_response 之后执行的逻辑（截断等）"""
        if not run_response:
            return
            
        if not run_response.metrics:
            return
            
        try:
            # 从RunResponse.metrics获取token使用情况
            # 使用类的_safe_get_first方法
            
            if isinstance(run_response.metrics, dict):
                # 直接处理字典
                metrics_dict = run_response.metrics
                total_tokens_raw = metrics_dict.get('total_tokens', 0)
                total_tokens = self._safe_get_first(total_tokens_raw)
                
                if total_tokens == 0:
                    input_tokens = self._safe_get_first(metrics_dict.get('input_tokens', 0))
                    output_tokens = self._safe_get_first(metrics_dict.get('output_tokens', 0))
                    total_tokens = input_tokens + output_tokens
            elif hasattr(run_response.metrics, '__dict__'):
                # 处理对象
                metrics_dict = run_response.metrics.__dict__
                total_tokens_raw = metrics_dict.get('total_tokens', 0)
                total_tokens = self._safe_get_first(total_tokens_raw)
            else:
                total_tokens = getattr(run_response.metrics, 'total_tokens', 0)
            
            usage_percentage = (total_tokens / self.max_context_tokens) * 100 if self.max_context_tokens > 0 else 0.0
            
            logger.info(f"📊 ContextManagedAgent Token使用: {total_tokens}/{self.max_context_tokens} ({usage_percentage:.1f}%)")
            
            # 更新session状态
            if not hasattr(self, 'session_state'):
                self.session_state = {}
            if 'context_management' not in self.session_state:
                self.session_state['context_management'] = {}
            self.session_state['context_management']['last_run_token_usage'] = total_tokens
            
            # 检查是否有标记需要截断的情况
            needs_truncation = self.session_state['context_management'].get('needs_truncation', False)
            if needs_truncation:
                reason = self.session_state['context_management'].get('truncation_reason', '未知原因')
                logger.warning(f"🔄 ContextManagedAgent 执行延迟截断: {reason}")
                
                # 执行截断
                success = self._truncate_context_messages()
                if success:
                    logger.info(f"✅ 截断执行成功")
                else:
                    logger.error(f"❌ 截断执行失败")
                
                # 清除截断标记
                self.session_state['context_management']['needs_truncation'] = False
                self.session_state['context_management'].pop('truncation_reason', None)
            
            # 延迟截断逻辑已删除，现在所有截断都是立即执行
            
            # --- 同步 _live_messages ←→ run_response.messages & current_run ---
            try:
                # 1) 确保 _live_messages 包含本轮最新全部消息（含 tool-msg）
                if run_response.messages:
                    self._live_messages = list(run_response.messages)
                # 2) 保证 current_run.messages 与 _live_messages 保持一致
                if (
                    hasattr(self.memory, "current_run")
                    and getattr(self.memory.current_run, "messages", None) is not None
                ):
                    self.memory.current_run.messages = list(self._live_messages)  # type: ignore
                # 3) 将 _live_messages 写回 run_response，供上层日志或链路使用
                run_response.messages = list(self._live_messages)
            except Exception:
                pass
            
        except Exception as e:
            logger.error(f"❌ Token监控失败: {str(e)}")
            import traceback
            traceback.print_exc()

    def _run(
        self,
        message: Optional[Union[str, List, Dict, Message]] = None,
        *,
        stream: bool = False,
        session_id: str,
        user_id: Optional[str] = None,
        audio: Optional[Sequence[Audio]] = None,
        images: Optional[Sequence[Image]] = None,
        videos: Optional[Sequence[Video]] = None,
        files: Optional[Sequence[File]] = None,
        messages: Optional[Sequence[Union[Dict, Message]]] = None,
        knowledge_filters: Optional[Dict[str, Any]] = None,
        stream_intermediate_steps: bool = False,
        run_response: RunResponse,
        **kwargs: Any,
    ) -> Iterator[RunResponse]:
        """重写_run方法，在model.response()后插入截断逻辑"""
        logger.debug("🎯 ContextManagedAgent._run 开始执行")

        # --- 调试: 打印即将发送给模型的完整消息统计 ---
        try:
            all_msgs = self.get_run_messages(
                message=message,
                session_id=session_id,
                user_id=user_id,
                messages=messages,
                audio=audio,
                images=images,
                videos=videos,
                files=files,
            )
            tool_cnt = sum(1 for m in all_msgs if getattr(m, "role", "") == "tool")
            tool_chars = sum(len(str(m.content)) for m in all_msgs if getattr(m, "role", "") == "tool")
            current_cnt = len(self.memory.current_run.messages) if getattr(self.memory, "current_run", None) else 0
            prefix_cnt = len(all_msgs) - current_cnt
            logger.debug(
                f"[PROMPT-DEBUG] total_msgs={len(all_msgs)}, prefix_msgs={prefix_cnt}, "
                f"current_run_msgs={current_cnt}, tool_msgs={tool_cnt}, tool_chars={tool_chars}"
            )
        except Exception as _pd_err:
            logger.debug(f"PROMPT-DEBUG error: {_pd_err}")

        # 调用父类方法获取生成器
        for response in super()._run(
            message=message,
            stream=stream,
            session_id=session_id,
            user_id=user_id,
            audio=audio,
            images=images,
            videos=videos,
            files=files,
            messages=messages,
            knowledge_filters=knowledge_filters,
            stream_intermediate_steps=stream_intermediate_steps,
            run_response=run_response,
            **kwargs
        ):
            # 在每个response后检查是否需要截断
            self._handle_post_response(response)
            yield response

    async def _arun(
        self,
        message: Optional[Union[str, List, Dict, Message]] = None,
        *,
        stream: bool = False,
        session_id: str,
        user_id: Optional[str] = None,
        audio: Optional[Sequence[Audio]] = None,
        images: Optional[Sequence[Image]] = None,
        videos: Optional[Sequence[Video]] = None,
        files: Optional[Sequence[File]] = None,
        messages: Optional[Sequence[Union[Dict, Message]]] = None,
        stream_intermediate_steps: bool = False,
        knowledge_filters: Optional[Dict[str, Any]] = None,
        run_response: RunResponse,
        **kwargs: Any,
    ) -> AsyncIterator[RunResponse]:
        """重写异步_arun，在调用父类前打印上下文统计"""
        logger.debug("🎯 ContextManagedAgent._arun 开始执行")

        # --- 调试: 打印即将发送给模型的完整消息统计 ---
        try:
            all_msgs = self.get_run_messages(
                message=message,
                session_id=session_id,
                user_id=user_id,
                messages=messages,
                audio=audio,
                images=images,
                videos=videos,
                files=files,
            )
            tool_cnt = sum(1 for m in all_msgs if getattr(m, "role", "") == "tool")
            tool_chars = sum(len(str(m.content)) for m in all_msgs if getattr(m, "role", "") == "tool")
            current_cnt = len(self.memory.current_run.messages) if getattr(self.memory, "current_run", None) else 0
            prefix_cnt = len(all_msgs) - current_cnt
            logger.debug(
                f"[PROMPT-DEBUG] total_msgs={len(all_msgs)}, prefix_msgs={prefix_cnt}, "
                f"current_run_msgs={current_cnt}, tool_msgs={tool_cnt}, tool_chars={tool_chars}"
            )
        except Exception as _pd_err:
            logger.debug(f"PROMPT-DEBUG error: {_pd_err}")
        # 调用父类异步方法
        async for response in super()._arun(
            message=message,
            stream=stream,
            session_id=session_id,
            user_id=user_id,
            audio=audio,
            images=images,
            videos=videos,
            files=files,
            messages=messages,
            stream_intermediate_steps=stream_intermediate_steps,
            knowledge_filters=knowledge_filters,
            run_response=run_response,
            **kwargs
        ):
            self._handle_post_response(response)
            yield response

    def _perform_context_management_check(self):
        """执行上下文管理检查"""
        logger.debug("🔍 执行上下文管理检查...")
        
        usage_data = self._calculate_context_usage()
        
        # 记录当前状态
        data_source = usage_data.get('data_source', 'unknown')
        logger.debug(f"CONTEXT_DEBUG: 当前上下文: {usage_data['total_tokens']}/{self.max_context_tokens} tokens ({usage_data['usage_percentage']:.1f}%) - 数据源: {data_source}")
        
        # 检查警告
        if usage_data['should_warn'] and not self._warning_sent:
            logger.warning(f"⚠️ 上下文使用率过高: {usage_data['usage_percentage']:.1f}% (阈值: {self.warning_threshold*100:.1f}%)")
            logger.warning(f"   当前Token数: {usage_data['total_tokens']}/{self.max_context_tokens}")
            logger.warning(f"   剩余Token: {usage_data['remaining_tokens']}")
            logger.warning(f"   数据源: {data_source}")
            self._warning_sent = True
        
        # 检查截断
        if usage_data['should_truncate']:
            logger.warning(f"🔥 上下文即将超限: {usage_data['usage_percentage']:.1f}% (阈值: {self.truncate_threshold*100:.1f}%)")
            logger.warning(f"   当前Token数: {usage_data['total_tokens']}/{self.max_context_tokens}")
            logger.warning(f"   开始执行截断...")
            truncated = self._truncate_context_messages()
            if truncated:
                logger.info(f"✅ 上下文截断完成")
            else:
                logger.warning(f"⚠️ 截断失败或无需截断")
        
        return usage_data
    
    def _log_pre_run_status(self, args, kwargs):
        """记录运行前状态（主要用于日志）"""
        session_id = kwargs.get('session_id', 'unknown')
        logger.debug(f"🚀 **[执行前检查] session_id: {session_id}**")
        
        # 执行前检查（此时可能没有最新的run_response）
        usage_data = self._calculate_context_usage()
        logger.debug(f"   运行前Token状态: {usage_data['total_tokens']}/{self.max_context_tokens} ({usage_data['usage_percentage']:.1f}%)")
        logger.debug(f"   数据源: {usage_data.get('data_source', 'unknown')}")
        
        return usage_data

    def _perform_post_run_context_management(self):
        """执行后进行上下文管理（此时有最新的run_response数据）"""
        logger.debug("📋 **[执行后检查] 开始上下文管理**")
        
        # 获取最新的token使用情况（此时应该有run_response数据）
        usage_data = self._calculate_context_usage()
        
        data_source = usage_data.get('data_source', 'unknown')
        logger.debug(f"   执行后Token状态: {usage_data['total_tokens']}/{self.max_context_tokens} ({usage_data['usage_percentage']:.1f}%)")
        logger.debug(f"   数据源: {data_source}")
        
        # 如果使用的是真实token数据，记录详细信息
        if data_source == 'run_response_metrics':
            logger.debug(f"   ✅ 真实Token详情:")
            logger.debug(f"      输入Token: {usage_data.get('input_tokens', 0)}")
            logger.debug(f"      输出Token: {usage_data.get('output_tokens', 0)}")
            logger.debug(f"      缓存Token: {usage_data.get('cached_tokens', 0)}")
            logger.debug(f"      推理Token: {usage_data.get('reasoning_tokens', 0)}")
        
        # 执行上下文管理检查
        self._perform_context_management_check()
        
        return usage_data
    
    def _estimate_tokens_for_message(self, message: str) -> int:
        """估算消息的token数量"""
        logger.debug(f"💬 **[Token估算] 估算消息Token数**")
        
        if not message:
            logger.debug(f"   消息为空，返回0")
            return 0
        
        # 简单的token估算：字符数 × 0.35 (基于一般的中英文混合比例)
        char_count = len(str(message))
        estimated_tokens = int(char_count * 0.35)
        
        logger.debug(f"   消息长度: {char_count} 字符")
        logger.debug(f"   估算Token: {char_count} × 0.35 = {estimated_tokens}")
        
        return estimated_tokens
    
    def print_response(
        self, 
        message: Optional[str] = None,
        **kwargs,
    ) -> RunResponse:
        """重写print_response方法，添加上下文管理"""
        logger.info("\n🖨️ **[响应输出] print_response 开始**")
        
        # 执行前上下文检查
        usage_info = self._calculate_context_usage()
        logger.debug(f"   输出前上下文: {usage_info['total_tokens']}/{usage_info['max_tokens']} ({usage_info['usage_percentage']:.1f}%)")
        
        # 调用原始方法（仅传递关键字参数，避免位置参数数量不匹配）
        logger.debug(f"   🚀 调用 super().print_response()...")
        result = super().print_response(message, **kwargs)
        logger.debug(f"   ✅ super().print_response() 完成")
        
        # 执行后再次检查并添加警告
        final_usage = self._calculate_context_usage()
        logger.debug(f"   输出后上下文: {final_usage['total_tokens']}/{final_usage['max_tokens']} ({final_usage['usage_percentage']:.1f}%)")
        
        # 检查是否需要添加警告信息到响应
        if result and hasattr(result, 'content') and result.content:
            logger.debug(f"   📝 检查是否需要添加上下文警告...")
            enhanced_content = self._add_context_warning_to_result(result.content, final_usage)
            if enhanced_content != result.content:
                logger.debug(f"   ✅ 已添加上下文状态信息到响应")
                result.content = enhanced_content
            else:
                logger.debug(f"   ℹ️ 无需添加额外状态信息")
        
        logger.info(f"🖨️ **[响应输出] print_response 结束**\n")
        return result
    
    def get_context_status(self) -> Dict[str, Any]:
        """获取当前上下文状态信息"""
        usage_info = self._calculate_context_usage()
        
        return {
            'usage_info': usage_info,
            'hca_history_count': len(self.session_state.get('hca_complete_history', [])),
            'truncation_count': self.session_state.get('context_management', {}).get('truncation_count', 0),
            'last_truncation': self.session_state.get('context_management', {}).get('last_truncation_time'),
            'message_count': len(self.messages) if hasattr(self, 'messages') and self.messages else 0
        }

    def _handle_message_post_log(self, assistant_message: Optional[Message]):
        """在assistant_message.log(metrics=True)后立即调用的token监控逻辑"""
        logger.debug(f"🔍 >>> _handle_message_post_log 被调用! assistant_message={type(assistant_message)}")
        logger.debug(f"🔍 >>> assistant_message.role={getattr(assistant_message, 'role', 'None')}")
        logger.debug(f"🔍 >>> assistant_message.content预览={getattr(assistant_message, 'content', 'None')[:100] if getattr(assistant_message, 'content', None) else 'None'}")
        
        if not assistant_message:
            logger.debug(f"🔍 >>> assistant_message 为 None，返回")
            return
            
        if not hasattr(assistant_message, 'metrics') or not assistant_message.metrics:
            logger.debug(f"🔍 >>> assistant_message.metrics 为 None，返回。hasattr(assistant_message, 'metrics')={hasattr(assistant_message, 'metrics')}")
            return
            
        logger.debug(f"🔍 >>> assistant_message.metrics 存在: {type(assistant_message.metrics)}")
        logger.debug(f"🔍 >>> metrics.total_tokens={getattr(assistant_message.metrics, 'total_tokens', 'None')}")
        logger.debug(f"🔍 >>> metrics.input_tokens={getattr(assistant_message.metrics, 'input_tokens', 'None')}")
        logger.debug(f"🔍 >>> metrics.output_tokens={getattr(assistant_message.metrics, 'output_tokens', 'None')}")
        
        # 确保session_state存在
        if not hasattr(self, 'session_state'):
            self.session_state = {}
        if 'context_management' not in self.session_state:
            self.session_state['context_management'] = {}
            
        try:
            # 从assistant_message.metrics获取token使用情况
            metrics = assistant_message.metrics
            
            # 获取当前消息的token数据
            total_tokens = getattr(metrics, 'total_tokens', 0)
            input_tokens = getattr(metrics, 'input_tokens', 0)
            output_tokens = getattr(metrics, 'output_tokens', 0)
            cached_tokens = getattr(metrics, 'cached_tokens', 0)
            reasoning_tokens = getattr(metrics, 'reasoning_tokens', 0)
            
            usage_percentage = (total_tokens / self.max_context_tokens) * 100 if self.max_context_tokens > 0 else 0.0
            
            # 智能输出策略：只在需要关注时输出
            should_output = False
            output_level = "info"
            
            # 调试模式：显示所有调用（用于测试）
            debug_mode = getattr(self, 'debug_mode', False)
            
            if usage_percentage >= (self.truncate_threshold * 100):
                # 达到截断阈值：关键输出
                should_output = True
                output_level = "critical"
            elif usage_percentage >= (self.warning_threshold * 100):
                # 达到警告阈值：警告输出
                should_output = True
                output_level = "warning"
            elif usage_percentage >= 30:  # 降低阈值从50%到30%
                # 超过30%：简单提醒
                should_output = True
                output_level = "notice"
            elif debug_mode:
                # 调试模式：显示所有调用
                should_output = True
                output_level = "debug"
            # 否则静默（不输出）
            
            if should_output:
                # 根据级别选择输出格式
                if output_level == "critical":
                    logger.error(f"🚨 ContextManagedAgent 关键警告: Token使用 {total_tokens}/{self.max_context_tokens} ({usage_percentage:.1f}%) - 即将截断!")
                elif output_level == "warning":
                    logger.warning(f"⚠️ ContextManagedAgent 警告: Token使用 {total_tokens}/{self.max_context_tokens} ({usage_percentage:.1f}%) - 接近上限")
                elif output_level == "notice":
                    logger.info(f"📊 ContextManagedAgent 提醒: Token使用 {total_tokens}/{self.max_context_tokens} ({usage_percentage:.1f}%)")
                elif output_level == "debug":
                    logger.debug(f"🔍 ContextManagedAgent 调试: Token使用 {total_tokens}/{self.max_context_tokens} ({usage_percentage:.1f}%)")
                
                # 详细信息（只在警告级别以上显示）
                if output_level in ["warning", "critical"] and (input_tokens > 0 or output_tokens > 0):
                    details = f"输入:{input_tokens}, 输出:{output_tokens}"
                    if cached_tokens > 0:
                        details += f", 缓存:{cached_tokens}"
                    if reasoning_tokens > 0:
                        details += f", 推理:{reasoning_tokens}"
                    logger.debug(f"   详情: {details}")
            
            # 更新session状态
            self.session_state['context_management']['last_run_token_usage'] = total_tokens
            
            # --- 将消息写入实时缓冲 ---
            try:
                if assistant_message not in getattr(self, "_live_messages", []):
                    self._live_messages.append(assistant_message)
            except Exception:
                pass
            
            # --- 🔥 新增：截断 run_messages 中的工具消息 ---
            self._truncate_tool_messages_in_run_messages()
            

            
            # 判断是否需要截断 - 但不在这里执行，而是标记需要截断
            if total_tokens >= (self.max_context_tokens * self.truncate_threshold):
                logger.warning(f"🔄 ContextManagedAgent 截断流程触发: token使用率{usage_percentage:.1f}% >= 阈值")

                # 1️⃣ 先尝试压缩旧的 tool 消息
                compressed = self._compress_old_tool_messages()
                if compressed:
                    logger.info("💡 已压缩旧 tool 消息，重新计算token…")
                    usage_info = self._calculate_context_usage()
                    total_tokens = usage_info.get('total_tokens', total_tokens)
                    usage_percentage = usage_info.get('usage_percentage', usage_percentage)

                # ⚠️ [已禁用] 删除旧 tool 消息会破坏工具调用链完整性，故直接跳过此步骤
                # if total_tokens >= (self.max_context_tokens * self.truncate_threshold):
                #     dropped = self._drop_old_tool_messages()
                #     if dropped:
                #         logger.info("🗑️ 已删除旧 tool 消息，重新计算token…")
                #         usage_info = self._calculate_context_usage()
                #         total_tokens = usage_info.get('total_tokens', total_tokens)
                #         usage_percentage = usage_info.get('usage_percentage', usage_percentage)

                # 3️⃣ 🔥 新逻辑：AI响应后立即执行总结，不管tool_calls状态
                if total_tokens >= (self.max_context_tokens * self.truncate_threshold):
                    if self.use_legacy_summary:
                        logger.warning(f"⚠️ AI响应后token超限({usage_percentage:.1f}%)，立即执行[旧]AI总结流程")
                        try:
                            summarized = self._ai_summarize_history_with_context_protection()
                            if summarized:
                                logger.info("🤖 旧AI总结完成，重新计算token使用")
                                usage_info = self._calculate_context_usage()
                                total_tokens = usage_info.get('total_tokens', total_tokens)
                                usage_percentage = usage_info.get('usage_percentage', usage_percentage)
                            else:
                                logger.warning("⚠️ 旧AI总结失败，继续使用传统截断")
                        except Exception as e:
                            logger.error(f"❌ 旧AI总结执行失败: {e}，继续使用传统截断")
                    else:
                        logger.info("🛑 已禁用旧AI总结逻辑，改由 summarize_context 工具处理。")
            
                    # 4️⃣ 兜底截断 —— 仅在启用 legacy_summary 时保留
                    if self.use_legacy_summary and total_tokens >= (self.max_context_tokens * self.truncate_threshold):
                        logger.warning("⚠️ AI总结后仍超限，执行对话条数截断 (legacy mode)")
                        success = self._truncate_context_messages()
                        if success:
                            logger.info("✂️ 已即时截断上下文 (legacy mode)")
                        else:
                            logger.error("❌ 即时截断失败 (legacy mode)")
                            # 标记需要截断，在Agent层面执行
                            self.session_state['context_management']['needs_truncation'] = True
                            self.session_state['context_management']['truncation_reason'] = f"token使用率达到{usage_percentage:.1f}%"
                
        except Exception as e:
            logger.error(f"❌ Token监控失败: {str(e)}")
            import traceback
            traceback.print_exc()

    def _patch_message_log(self):
        """为 agno.models.message.Message.log 打补丁，实现全局 token 监控回调"""
        import logging
        from agno.models.message import Message as _AgnoMessage

        logger = logging.getLogger(__name__)

        # 如果首次打补丁，则包装原始 log 方法
        if not getattr(_AgnoMessage, "_token_monitor_patched", False):
            original_log = _AgnoMessage.log

            def patched_log(msg_self, *args, **kwargs):  # type: ignore
                """包装后的全局 log 方法"""
                # 先执行原始行为，保持现有输出不变
                result = original_log(msg_self, *args, **kwargs)

                try:
                    # 在 assistant 或 tool 消息且带 token metrics 时触发
                    if (
                        msg_self.role in {"assistant", "tool"}
                        and getattr(msg_self, "metrics", None) is not None
                        and getattr(msg_self.metrics, "total_tokens", 0) > 0
                    ):
                        # 调用已注册的所有监控回调
                        for hook in getattr(_AgnoMessage, "_token_monitor_hooks", []):
                            try:
                                hook(msg_self)
                            except Exception as hook_err:  # pragma: no cover
                                logger.debug(f"⚠️ token 监控 hook 执行失败: {hook_err}")
                except Exception as e:  # pragma: no cover
                    logger.debug(f"⚠️ patched_log 内部错误: {e}")

                return result

            # 设置补丁及标记
            _AgnoMessage.log = patched_log  # type: ignore
            _AgnoMessage._token_monitor_patched = True  # type: ignore
            _AgnoMessage._token_monitor_hooks = []  # type: ignore
            logger.critical("🎯 Message.log 补丁应用成功!")

                    # 每个 Agent 实例注册自己的回调，使得多个 Agent 可以共存
        def _agent_hook(message):  # type: ignore
            try:
                # 避免同一条消息被多个 Agent 重复处理
                if getattr(message, "_token_monitor_handled", False):
                    return
                # 设置标记，表示已处理
                setattr(message, "_token_monitor_handled", True)
                self._handle_message_post_log(message)
                
                # 工具消息处理完成，无需额外操作
            except Exception as e:  # pragma: no cover
                logger.debug(f"⚠️ agent hook 执行失败: {e}")

        # 避免重复注册
        hooks: list = getattr(_AgnoMessage, "_token_monitor_hooks", [])  # type: ignore
        if _agent_hook not in hooks:
            hooks.append(_agent_hook)
            _AgnoMessage._token_monitor_hooks = hooks  # type: ignore
            logger.debug("🔧 已向 Message.log 注册当前 Agent 的 token 监控 hook")


    

    
    def _generate_ai_summary(self, messages_to_summarize) -> str:
        """生成AI总结内容"""
        try:
            # 构建总结提示
            messages_text = ""
            for i, msg in enumerate(messages_to_summarize):
                role = getattr(msg, 'role', 'unknown')
                content = getattr(msg, 'content', '')
                if content:
                    messages_text += f"{role}: {content[:500]}...\n" if len(content) > 500 else f"{role}: {content}\n"
            
            summary_prompt = f"""请将以下对话历史总结为简洁的要点，保留关键信息和分析结果：

{messages_text}

请用中文总结，格式如下：
## 对话历史总结
- 主要讨论的问题：
- 关键发现：
- 重要结论：
- 当前进展：
"""
            
            # 获取总结模型
            summary_model = self._get_or_create_summary_model()
            if not summary_model:
                return ""
            
            # 调用AI生成总结
            from agno.models.message import Message
            summary_messages = [Message(role="user", content=summary_prompt)]
            
            response = summary_model.response(messages=summary_messages)
            if response and hasattr(response, 'content') and response.content:
                return response.content.strip()
            
            return ""
            
        except Exception as e:
            logger.error(f"❌ 生成AI总结失败: {e}")
            return ""
    
    def _has_pending_tool_calls_in_messages(self):
        """检查最近的消息中是否有未完成的工具调用"""
        try:
            # 获取最新的消息列表：优先 run_messages.messages，其次 current_run.messages，最后 _live_messages
            messages: List = []
            if (
                hasattr(self, "run_messages")
                and self.run_messages is not None
                and getattr(self.run_messages, "messages", None) is not None
            ):
                messages = list(self.run_messages.messages)
            elif hasattr(self.memory, "current_run") and getattr(self.memory.current_run, "messages", None):
                messages = list(self.memory.current_run.messages)  # type: ignore
            elif getattr(self, "_live_messages", []):
                messages = list(self._live_messages)
            
            if not messages:
                return False
            
            # 🔥 关键修复：只检查最近的几条消息，避免历史污染
            # 从后往前查找最近的assistant消息（包含tool_calls）
            recent_limit = 10  # 只检查最近10条消息
            recent_messages = messages[-recent_limit:] if len(messages) > recent_limit else messages
            
            # 找到最后一个包含tool_calls的assistant消息
            last_tool_call_msg = None
            last_tool_call_index = -1
            
            for i in range(len(recent_messages) - 1, -1, -1):
                msg = recent_messages[i]
                if (getattr(msg, 'role', '') == 'assistant' and 
                    hasattr(msg, 'tool_calls') and msg.tool_calls):
                    last_tool_call_msg = msg
                    last_tool_call_index = i
                    break
            
            if not last_tool_call_msg:
                # 没有找到最近的tool_calls，说明没有待处理的工具调用
                logger.debug("🔧 未找到最近的tool_calls消息")
                return False
            
            # 提取最后一个tool_calls消息的所有tool_call_ids
            expected_tool_call_ids = set()
            try:
                for tc in last_tool_call_msg.tool_calls:
                    if hasattr(tc, 'id'):
                        expected_tool_call_ids.add(tc.id)
                    elif isinstance(tc, dict) and 'id' in tc:
                        expected_tool_call_ids.add(tc['id'])
            except:
                pass
            
            if not expected_tool_call_ids:
                logger.debug("🔧 最近的tool_calls消息没有有效的tool_call_id")
                return False
            
            # 在该assistant消息之后查找对应的tool响应
            found_tool_response_ids = set()
            for i in range(last_tool_call_index + 1, len(recent_messages)):
                msg = recent_messages[i]
                if getattr(msg, 'role', '') == 'tool' and hasattr(msg, 'tool_call_id'):
                    if msg.tool_call_id in expected_tool_call_ids:
                        found_tool_response_ids.add(msg.tool_call_id)
            
            # 检查是否所有tool_calls都有对应的响应
            pending = expected_tool_call_ids - found_tool_response_ids
            if pending:
                logger.debug(f"🔧 最近的工具调用中有 {len(pending)} 个未完成: {pending}")
                return True
            else:
                logger.debug(f"🔧 最近的工具调用已全部完成 ({len(expected_tool_call_ids)} 个)")
                return False
            
        except Exception as e:
            logger.error(f"❌ 检查未完成工具调用失败: {e}")
            return False

    # ------------------------------------------------------------------
    # 🛠️  新增: tool 消息压缩 / 丢弃 辅助方法
    # ------------------------------------------------------------------
    
    def _truncate_tool_messages_in_run_messages(self):
        """智能截断 run_messages 中的工具消息，保护最近的工具调用"""
        if not (hasattr(self, "run_messages") and self.run_messages and hasattr(self.run_messages, "messages")):
            return
        
        # 找到所有工具消息的索引
        tool_indices = []
        for i, msg in enumerate(self.run_messages.messages):
            if getattr(msg, "role", "") == "tool":
                tool_indices.append(i)
        
        if not tool_indices:
            return
        
        # 保护最近的 N 条工具消息
        keep_recent = getattr(self, "keep_recent_tool_messages", 3)
        protected_indices = set(tool_indices[-keep_recent:])
        
        max_len = getattr(self, "max_tool_message_chars", 300)  # 注意这里是300，不是10000
        changed = False
        
        for i in tool_indices:
            if i in protected_indices:
                # 跳过受保护的最近工具消息
                continue
                
            msg = self.run_messages.messages[i]
            content = getattr(msg, "content", "")
            if content and len(content) > max_len:
                original_len = len(content)
                msg.content = content[:max_len] + f"\n…(内容过长已截断，原长 {original_len} 字)"
                changed = True
                logger.debug(f"🔥 截断旧工具消息 #{i}: {original_len} -> {len(msg.content)} 字符")
        
        if changed:
            logger.debug(f"🔥 已截断 run_messages 中的旧工具消息，保护最近 {keep_recent} 条")

    def _compress_old_tool_messages(self) -> bool:
        """压缩较旧且内容过长的 tool 消息，保留最近N条原文"""
        try:
            # === 调试: 压缩前统计 ===
            _msgs_debug = []
            if hasattr(self.memory, "current_run") and getattr(self.memory.current_run, "messages", None):
                _msgs_debug = list(self.memory.current_run.messages)  # type: ignore
            elif getattr(self, "_live_messages", []):
                _msgs_debug = list(self._live_messages)
            tool_cnt_before = sum(1 for _m in _msgs_debug if getattr(_m, "role", "") == "tool")
            tool_chars_before = sum(len(getattr(_m, "content", "")) for _m in _msgs_debug if getattr(_m, "role", "") == "tool")
            logger.debug(f"[TOOL-COMPRESS] before: total_msgs={len(_msgs_debug)}, tool_msgs={tool_cnt_before}, tool_chars={tool_chars_before}")

            # 优先使用 current_run.messages（包含 tool-msg）
            msgs = []
            if hasattr(self.memory, "current_run") and getattr(self.memory.current_run, "messages", None):
                msgs = list(self.memory.current_run.messages)  # type: ignore
            elif getattr(self, "_live_messages", []):
                msgs = list(self._live_messages)
            if not msgs:
                return False

            # 重新计算 tool 下标
            tool_indices = [idx for idx, m in enumerate(msgs) if getattr(m, "role", "") == "tool"]
            protected = set(tool_indices[-self.keep_recent_tool_messages:])
            changed = False
            for idx, msg in enumerate(msgs):
                if idx in protected:
                    continue
                if getattr(msg, "role", "") != "tool":
                    continue
                content = getattr(msg, "content", "")
                if content and len(content) > self.max_tool_message_chars:
                    msg.content = (
                        content[: self.max_tool_message_chars]
                        + f"\n…(内容过长已截断，原长 {len(content)} 字)"
                    )
                    changed = True

            if changed:
                # 同步修改后的列表到 _live_messages 和 current_run
                self._live_messages = list(msgs)
                if hasattr(self.memory, "current_run") and getattr(self.memory.current_run, "messages", None) is not None:
                    self.memory.current_run.messages = list(msgs)  # type: ignore
                
                # 🔥 关键修复：同步到 run_messages.messages（模型实际使用的列表）
                if (
                    hasattr(self, "run_messages")
                    and self.run_messages is not None
                    and getattr(self.run_messages, "messages", None) is not None
                ):
                    # 找到 run_messages 中的工具消息并更新
                    for i, run_msg in enumerate(self.run_messages.messages):
                        if getattr(run_msg, "role", "") == "tool":
                            # 在压缩后的消息中找到对应的工具消息
                            for compressed_msg in msgs:
                                if (getattr(compressed_msg, "role", "") == "tool" and 
                                    getattr(compressed_msg, "tool_name", None) == getattr(run_msg, "tool_name", None)):
                                    self.run_messages.messages[i] = compressed_msg
                                    break
                    logger.debug("🔥 已同步压缩结果到 run_messages.messages")
            return changed

            # === 调试: 压缩后统计 ===
        finally:
            try:
                _msgs_after = []
                if hasattr(self.memory, "current_run") and getattr(self.memory.current_run, "messages", None):
                    _msgs_after = list(self.memory.current_run.messages)  # type: ignore
                tool_cnt_after = sum(1 for _m in _msgs_after if getattr(_m, "role", "") == "tool")
                tool_chars_after = sum(len(getattr(_m, "content", "")) for _m in _msgs_after if getattr(_m, "role", "") == "tool")
                logger.debug(f"[TOOL-COMPRESS] after : total_msgs={len(_msgs_after)}, tool_msgs={tool_cnt_after}, tool_chars={tool_chars_after}")
            except Exception:
                pass

    def _drop_old_tool_messages(self) -> bool:
        """删除更旧的 tool 消息，仅保留最近N条，用于压缩仍不足时兜底"""
        try:
            # === 调试: 删除前统计 ===
            _msgs_before = []
            if hasattr(self.memory, "current_run") and getattr(self.memory.current_run, "messages", None):
                _msgs_before = list(self.memory.current_run.messages)  # type: ignore
            elif getattr(self, "_live_messages", []):
                _msgs_before = list(self._live_messages)
            tool_cnt_before = sum(1 for _m in _msgs_before if getattr(_m, "role", "") == "tool")
            logger.debug(f"[TOOL-DROP] before: total_msgs={len(_msgs_before)}, tool_msgs={tool_cnt_before}")

            # 读取完整消息列表
            msgs = []
            if hasattr(self.memory, "current_run") and getattr(self.memory.current_run, "messages", None):
                msgs = list(self.memory.current_run.messages)  # type: ignore
            elif getattr(self, "_live_messages", []):
                msgs = list(self._live_messages)
            if not msgs:
                return False

            tool_indices = [idx for idx, m in enumerate(msgs) if getattr(m, "role", "") == "tool"]
            if len(tool_indices) <= self.keep_recent_tool_messages:
                return False  # 没有可删除的

            protected = set(tool_indices[-self.keep_recent_tool_messages:])
            new_msgs = [m for idx, m in enumerate(msgs) if not (idx in tool_indices and idx not in protected)]

            if len(new_msgs) == len(msgs):
                return False  # 无变动

            # 更新缓冲 & current_run
            self._live_messages = new_msgs
            if hasattr(self.memory, "current_run") and getattr(self.memory.current_run, "messages", None) is not None:
                self.memory.current_run.messages = list(new_msgs)  # type: ignore
            
            # 🔥 关键修复：同步删除到 run_messages.messages
            if (
                hasattr(self, "run_messages")
                and self.run_messages is not None
                and getattr(self.run_messages, "messages", None) is not None
            ):
                # 重建 run_messages.messages，移除被删除的工具消息
                tool_indices_to_remove = set(tool_indices) - protected
                new_run_msgs = [
                    msg for i, msg in enumerate(self.run_messages.messages)
                    if not (getattr(msg, "role", "") == "tool" and i in tool_indices_to_remove)
                ]
                self.run_messages.messages[:] = new_run_msgs  # 原地修改列表
                logger.debug("🔥 已同步删除结果到 run_messages.messages")
            
            logger.info(f"🗑️ 已删除 {len(msgs) - len(new_msgs)} 条旧 tool 消息，仅保留最近 {self.keep_recent_tool_messages} 条")
            # === 调试: 删除后统计 ===
            tool_cnt_after = sum(1 for _m in new_msgs if getattr(_m, "role", "") == "tool")
            logger.debug(f"[TOOL-DROP] after : total_msgs={len(new_msgs)}, tool_msgs={tool_cnt_after}")
            return True
        except Exception as e:
            logger.error(f"❌ 删除 tool 消息失败: {e}")
            return False

    def _get_or_create_summary_model(self):
        """获取或创建用于AI总结的独立模型实例，避免与主Agent流程冲突"""
        try:
            # 如果已经有缓存的总结模型，直接使用
            if hasattr(self, '_summary_model') and self._summary_model:
                return self._summary_model
            
            # 创建独立的模型实例
            if hasattr(self, 'model') and self.model:
                # 获取主模型的配置
                model_class = type(self.model)
                model_config = {}
                
                # 复制主要配置参数
                if hasattr(self.model, 'id'):
                    model_config['id'] = self.model.id
                if hasattr(self.model, 'api_key'):
                    model_config['api_key'] = self.model.api_key
                if hasattr(self.model, 'base_url'):
                    model_config['base_url'] = self.model.base_url
                if hasattr(self.model, 'temperature'):
                    model_config['temperature'] = getattr(self.model, 'temperature', 0.7)
                if hasattr(self.model, 'max_tokens'):
                    model_config['max_tokens'] = getattr(self.model, 'max_tokens', None)
                
                # 复制超时时间和重试次数，若主模型未设置则给予宽松默认
                if hasattr(self.model, 'timeout') and getattr(self.model, 'timeout', None):
                    model_config['timeout'] = getattr(self.model, 'timeout')
                else:
                    model_config['timeout'] = 60
                if hasattr(self.model, 'max_retries') and getattr(self.model, 'max_retries', None):
                    model_config['max_retries'] = getattr(self.model, 'max_retries')
                else:
                    model_config['max_retries'] = 5
                
                # 为总结模型创建专用 httpx.Client 并开启事件调试
                try:
                    import httpx, sys

                    def _dbg(name):
                        def _handler(event):
                            print(f"[SUMMARY-HTTPX] {name}: {event!r}", file=sys.stderr)
                        return _handler

                    debug_client = httpx.Client(
                        timeout=model_config.get('timeout', 60),
                        http2=True,  # 使用 HTTP/2 并保留 keep-alive，避免服务端提前断开
                        event_hooks={
                            "request": [_dbg("request")],
                            "response": [_dbg("response")],
                        },
                    )
                    model_config['http_client'] = debug_client
                except Exception as _dbg_err:
                    logger.debug(f"⚠️ 创建调试 httpx.Client 失败: {_dbg_err}")
                
                # 创建新的模型实例
                self._summary_model = model_class(**model_config)
                logger.debug(f"🔍 创建独立总结模型实例: {model_class.__name__}({model_config})")
                return self._summary_model
            else:
                # 如果没有主模型，使用默认配置
                from agno.models.openai import OpenAIChat
                self._summary_model = OpenAIChat(id="gpt-4o-mini")  # 使用更便宜的模型进行总结
                logger.debug("🔍 创建默认总结模型实例: OpenAIChat(gpt-4o-mini)")
                return self._summary_model
                
        except Exception as e:
            logger.error(f"❌ 创建总结模型实例失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    # TODO(重构): 计划在 summarize_context 工具稳定后，删除旧的 _ai_summarize_history_with_context_protection 实现
    def _ai_summarize_history_with_context_protection(self) -> bool:
        """使用AI模型总结历史对话，但保护当前工作上下文（适用于持续工具调用场景）"""
        try:
            # 获取当前消息列表：优先 run_messages.messages，其次 current_run.messages，最后 _live_messages
            msgs: List = []
            if (
                hasattr(self, "run_messages")
                and self.run_messages is not None
                and getattr(self.run_messages, "messages", None) is not None
            ):
                msgs = list(self.run_messages.messages)
            elif hasattr(self.memory, "current_run") and getattr(self.memory.current_run, "messages", None):
                msgs = list(self.memory.current_run.messages)
            elif getattr(self, "_live_messages", []):
                msgs = list(self._live_messages)
            
            if len(msgs) <= 5:  # 消息太少，不需要总结
                return False
            
            # 🔥 新策略：保护最近的消息 + 保留所有user消息 + 总结其余历史
            base_protect_count = min(6, max(3, len(msgs) // 4))  # 保护最近1/4，上限6条
            
            # 🔧 关键修复：确保保护边界不会拆分 assistant(tool_calls)+tool 链
            protect_count = self._ensure_tool_call_context_integrity(msgs, base_protect_count)
            if protect_count != base_protect_count:
                logger.debug(
                    f"🔧 _ensure_tool_call_context_integrity 调整保护边界: {base_protect_count} -> {protect_count}"
                )

            # 如果需要保护的消息数量大于等于总长度，则无需摘要
            if protect_count >= len(msgs):
                logger.debug("🔧 保护数量 >= 总消息数，跳过AI总结")
                return False

            # 1) 保护最近的消息（包含当前工作上下文）
            recent_msgs = list(msgs[-protect_count:])

            # 2) 从历史中提取所有user消息单独保留
            historical_part = msgs[:-protect_count]

            # 重新计算需要保留的 user 消息与需要摘要的历史消息
            user_msgs_to_keep = [m for m in historical_part if getattr(m, 'role', '') == 'user']
            history_msgs = [m for m in historical_part if getattr(m, 'role', '') != 'user']

            logger.debug(
                f"🔧 消息分组: 最近{len(recent_msgs)}条(保护) + 保留user{len(user_msgs_to_keep)}条 + 总结{len(history_msgs)}条"
            )
            
            if not history_msgs:
                logger.debug("🔧 没有需要总结的历史消息，跳过AI总结")
                return False

            # 构建总结提示
            history_text = ""
            for i, msg in enumerate(history_msgs):
                role = getattr(msg, 'role', 'unknown')
                content = str(getattr(msg, 'content', ''))[:1000]  # 限制长度避免总结请求过长
                history_text += f"\n[{role}]: {content}"
            
            summary_prompt = f"""请将以下对话历史总结为一个简洁的摘要（不超过800字），重点保留对后续工具调用有用的信息：

{history_text}

要求：
1. 保留所有重要的技术发现、漏洞信息和分析结果
2. 保留关键的工具调用结果和数据
3. 保留重要的决策、结论和下一步计划
4. 保留可能影响后续分析的上下文信息
5. 按主题分类组织信息（而非时间顺序）
6. 突出重点，但保持足够的技术细节供后续参考

注意：这个摘要将用于支持后续的自主工具调用，请确保包含足够的上下文信息。"""

            # 🔥 关键修复：每次都创建全新的模型实例，避免连接状态问题
            # 清除缓存的模型实例
            if hasattr(self, '_summary_model'):
                delattr(self, '_summary_model')
            
            summary_model = self._get_or_create_summary_model()
            if not summary_model:
                logger.warning("⚠️ 无法获取总结模型实例，跳过AI总结")
                return False
            
            logger.info(f"🤖 开始AI总结历史对话（{len(history_msgs)}条消息 -> 1条摘要，保护最近{len(user_msgs_to_keep)}条包含真实用户消息）")
            
            # 创建总结消息
            from agno.models.message import Message
            summary_request = Message(role="user", content=summary_prompt)
            
            # 调用独立模型生成总结
            logger.debug(f"🔍 AI总结: 使用独立模型实例 {type(summary_model)} 进行总结")
            logger.debug(f"🔍 AI总结: 总结请求长度 {len(summary_prompt)} 字符")
            
            # 添加重试机制处理连接错误
            max_retries = 3
            retry_delay = 2.0  # 增加初始延迟
            
            for attempt in range(max_retries + 1):
                try:
                    if attempt > 0:
                        logger.info(f"🔄 AI总结重试第 {attempt} 次，延迟 {retry_delay} 秒")
                        import time
                        time.sleep(retry_delay)
                        retry_delay *= 2  # 指数退避
                    
                    response = summary_model.response([summary_request])
                    logger.debug(f"🔍 AI总结: 模型响应类型 {type(response)}")
                    
                    if not response:
                        logger.warning("⚠️ AI总结失败，模型返回None")
                        if attempt < max_retries:
                            continue
                        return False
                        
                    if not hasattr(response, 'content') or not response.content:
                        logger.warning(f"⚠️ AI总结失败，响应无内容: {response}")
                        if attempt < max_retries:
                            continue
                        return False
                        
                    logger.debug(f"🔍 AI总结: 响应内容长度 {len(response.content)} 字符")
                    break  # 成功，跳出重试循环
                    
                except Exception as model_err:
                    import traceback, sys
                    print("=== SUMMARY CALL EXCEPTION ===", file=sys.stderr)
                    traceback.print_exception(type(model_err), model_err, model_err.__traceback__, file=sys.stderr)

                    _ca = getattr(model_err, "__cause__", None) or getattr(model_err, "__context__", None)
                    if _ca:
                        print("── inner cause ──", file=sys.stderr)
                        traceback.print_exception(type(_ca), _ca, _ca.__traceback__, file=sys.stderr)
                    print("=== END ===", file=sys.stderr)
                    # 更精确的异常类型判断
                    error_msg = str(model_err).lower()
                    error_type = type(model_err).__name__.lower()
                    
                    # 只有真正的连接相关异常才重试
                    is_connection_error = (
                        'connection' in error_msg or 
                        'timeout' in error_msg or 
                        'network' in error_msg or
                        'connectionerror' in error_type or
                        'timeouterror' in error_type or
                        'httperror' in error_type
                    )
                    
                    # 排除不应该重试的情况
                    is_auth_error = 'auth' in error_msg or 'unauthorized' in error_msg or '401' in error_msg
                    is_rate_limit = 'rate limit' in error_msg or '429' in error_msg
                    is_model_error = 'model' in error_msg and 'not found' in error_msg
                    
                    should_retry = is_connection_error and not (is_auth_error or is_rate_limit or is_model_error)
                    
                    if should_retry and attempt < max_retries:
                        logger.warning(f"⚠️ AI总结连接错误 (尝试 {attempt + 1}/{max_retries + 1}): {model_err}")
                        import time
                        time.sleep(2.0 * (attempt + 1))  # 递增延迟
                        continue
                    else:
                        logger.error(f"❌ AI总结模型调用失败: {model_err}")
                        logger.error(f"   错误类型: {type(model_err)}")
                        logger.error(f"   错误消息: {error_msg}")
                        logger.error(f"   是否连接错误: {is_connection_error}")
                        logger.error(f"   是否应该重试: {should_retry}")
                        logger.error(f"   尝试次数: {attempt + 1}/{max_retries + 1}")
                        
                        if attempt == max_retries:
                            # 最后一次尝试失败，返回 False 让上层使用传统截断
                            logger.warning("⚠️ AI总结多次重试失败，将使用传统截断")
                            return False
            else:
                # 所有重试都失败了
                logger.error("❌ AI总结所有重试都失败")
                return False
            
            # 创建总结消息
            summary_content = f"""
📋 **历史上下文摘要** (压缩了{len(history_msgs)}条消息，保护了最近{len(user_msgs_to_keep)}条)
压缩时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{response.content}

⚠️ **注意**: 
- 这是为支持持续工具调用而生成的上下文摘要
- 最近{len(user_msgs_to_keep)}条消息保持完整，包含真实用户消息和当前工作上下文
- 详细的HCA历史记录可通过 query_hca_history() 工具查询
"""
            
            # 🔥 新逻辑：构建最终消息列表 = user消息 + 摘要 + 最近消息
            from agno.models.message import Message
            summary_msg = Message(role="assistant", content=summary_content)
            new_msgs = user_msgs_to_keep + [summary_msg] + recent_msgs
            
            # 更新所有消息存储位置
            self._live_messages = new_msgs
            if hasattr(self.memory, "current_run") and getattr(self.memory.current_run, "messages", None) is not None:
                self.memory.current_run.messages = new_msgs
            
            # 同步到 run_messages（关键！）
            if (hasattr(self, "run_messages") and self.run_messages is not None and 
                getattr(self.run_messages, "messages", None) is not None):
                self.run_messages.messages[:] = new_msgs  # 原地替换
            
            # 更新统计
            self.session_state.setdefault("context_management", {})
            ctx_mgmt = self.session_state["context_management"]
            ctx_mgmt["ai_summary_count"] = ctx_mgmt.get("ai_summary_count", 0) + 1
            ctx_mgmt["last_ai_summary_time"] = datetime.now().isoformat()
            
            logger.info(f"✅ AI总结完成: {len(msgs)} -> {len(new_msgs)} 条消息 (保留{len(user_msgs_to_keep)}条user + 1条摘要 + {len(recent_msgs)}条最近)")
            return True
            
        except Exception as e:
            logger.error(f"❌ AI总结失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _create_summarized_messages(self, history_msgs, recent_msgs, summary_content, protect_count):
        """创建包含摘要的消息列表：智能重排确保tool_calls在最后"""
        from agno.models.message import Message
        
        # 创建摘要消息
        summary_msg = Message(role="assistant", content=summary_content)
        
        logger.debug(f"🔧 创建摘要消息列表: 历史{len(history_msgs)}条 -> 摘要1条, 保护最新{len(recent_msgs)}条")
        
        if not recent_msgs:
            # 如果没有最新消息需要保护，只返回摘要
            return [summary_msg]
        
        # 🔥 最简单有效的策略：摘要作为user消息插入，避免连续assistant消息
        # 核心原则：OpenAI API不允许连续的assistant消息
        
        if not recent_msgs:
            result = [summary_msg]
        else:
            # 检查第一个保护消息的角色
            first_msg_role = getattr(recent_msgs[0], 'role', '')
            
            if first_msg_role == 'assistant':
                # 如果第一个保护消息是assistant，摘要改为user角色避免冲突
                logger.debug("🔧 检测到保护消息以assistant开头，摘要改为user角色")
                from agno.models.message import Message
                user_summary_msg = Message(
                    role="user", 
                    content=f"[上下文摘要] {summary_content}"
                )
                result = [user_summary_msg] + recent_msgs
            else:
                # 其他情况，摘要保持assistant角色
                logger.debug("🔧 保护消息不以assistant开头，摘要保持assistant角色")
                result = [summary_msg] + recent_msgs
        
        logger.debug(f"🔧 摘要消息列表创建完成: 总计{len(result)}条消息")
        logger.debug(f"🔧 最终消息顺序: {[getattr(msg, 'role', 'unknown') for msg in result]}")
        
        return result
    
    def _has_incomplete_tool_calls(self, msgs):
        """检查消息列表中是否有不完整的工具调用"""
        tool_call_ids = set()
        tool_response_ids = set()
        
        for msg in msgs:
            role = getattr(msg, 'role', '')
            
            # 收集所有的tool_call_ids
            if role == 'assistant' and hasattr(msg, 'tool_calls') and msg.tool_calls:
                try:
                    for tc in msg.tool_calls:
                        if hasattr(tc, 'id'):
                            tool_call_ids.add(tc.id)
                        elif isinstance(tc, dict) and 'id' in tc:
                            tool_call_ids.add(tc['id'])
                except:
                    pass
            
            # 收集所有的tool响应ids
            elif role == 'tool' and hasattr(msg, 'tool_call_id'):
                tool_response_ids.add(msg.tool_call_id)
        
        # 如果有tool_calls但没有对应的响应，就是不完整的
        incomplete = tool_call_ids - tool_response_ids
        if incomplete:
            logger.debug(f"🔧 发现不完整的工具调用: {incomplete}")
            return True
        
        return False
    
    def _repair_incomplete_tool_calls_in_recent(self, recent_msgs):
        """修复最新消息中的不完整工具调用"""
        from agno.models.message import Message
        
        result = []
        pending_tool_calls = {}  # tool_call_id -> assistant_msg
        
        for msg in recent_msgs:
            role = getattr(msg, 'role', '')
            
            if role == 'assistant' and hasattr(msg, 'tool_calls') and msg.tool_calls:
                # 记录这个assistant消息的tool_calls
                result.append(msg)
                try:
                    for tc in msg.tool_calls:
                        tool_call_id = None
                        if hasattr(tc, 'id'):
                            tool_call_id = tc.id
                        elif isinstance(tc, dict) and 'id' in tc:
                            tool_call_id = tc['id']
                        
                        if tool_call_id:
                            pending_tool_calls[tool_call_id] = msg
                except:
                    pass
            
            elif role == 'tool' and hasattr(msg, 'tool_call_id'):
                # 这是一个tool响应，移除对应的pending
                result.append(msg)
                if msg.tool_call_id in pending_tool_calls:
                    del pending_tool_calls[msg.tool_call_id]
            
            else:
                # 其他消息直接添加
                result.append(msg)
        
        # 为所有pending的tool_calls创建虚拟响应
        for tool_call_id, assistant_msg in pending_tool_calls.items():
            virtual_response = Message(
                role="tool",
                content="[上下文优化：工具调用已完成，结果已整合到历史摘要中]",
                tool_call_id=tool_call_id
            )
            result.append(virtual_response)
            logger.debug(f"🔧 为tool_call_id {tool_call_id} 创建虚拟响应")
        
        return result
    

    

    

    

    
    def _has_tool_call_context(self, msgs):
        """检查消息列表中是否有工具调用上下文"""
        for msg in msgs:
            if (hasattr(msg, 'tool_calls') and msg.tool_calls) or getattr(msg, 'role', '') == 'tool':
                return True
        return False
    
    def _find_assistant_with_tool_calls(self, msgs):
        """在消息列表中找到包含tool_calls的assistant消息的索引"""
        for i, msg in enumerate(msgs):
            if (getattr(msg, 'role', '') == 'assistant' and 
                hasattr(msg, 'tool_calls') and msg.tool_calls):
                return i
        return -1
    
    def _find_last_real_user_message(self, msgs):
        """找到最后一个真实的用户消息索引"""
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i].role == "user" and not getattr(msgs[i], 'from_history', False):
                return i
        return -1
    
    def _ensure_tool_call_context_integrity(self, messages: List, target_keep_count: int) -> int:
        """
        确保工具调用上下文的完整性，调整保留消息数量
        
        规则：
        1. 如果保留的消息中有 assistant 消息包含 tool_calls，必须保留对应的 tool 消息
        2. 如果保留的消息中有 tool 消息，必须保留对应的 assistant 消息
        3. 确保工具调用链的完整性
        4. 🔥 特别保护：检测正在执行的工具调用，确保不被截断
        """
        if target_keep_count >= len(messages):
            return target_keep_count
        
        # 🔥 关键修复：首先检查是否有正在执行的工具调用（最后一条assistant消息包含tool_calls但没有对应的tool响应）
        # 从后往前查找最后一个assistant消息
        last_assistant_idx = -1
        logger.debug(f"🔍 工具调用完整性检查：开始检查 {len(messages)} 条消息")
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            role = getattr(msg, 'role', '')
            has_tool_calls = hasattr(msg, 'tool_calls') and msg.tool_calls
            logger.debug(f"🔍 消息 #{i}: role={role}, has_tool_calls={has_tool_calls}")
            if role == 'assistant' and has_tool_calls:
                last_assistant_idx = i
                logger.debug(f"🔍 找到最后一个工具调用assistant消息: #{i}")
                break
        
        if last_assistant_idx != -1:
            # 检查这个assistant消息的tool_calls是否都有对应的tool响应
            assistant_msg = messages[last_assistant_idx]
            tool_call_ids = set()
            try:
                for tc in assistant_msg.tool_calls:
                    if hasattr(tc, 'id'):
                        tool_call_ids.add(tc.id)
                    elif isinstance(tc, dict) and 'id' in tc:
                        tool_call_ids.add(tc['id'])
            except:
                pass
            
            logger.debug(f"🔍 工具调用IDs: {tool_call_ids}")
            
            if tool_call_ids:
                # 检查后续是否有对应的tool响应
                found_tool_responses = set()
                for i in range(last_assistant_idx + 1, len(messages)):
                    msg = messages[i]
                    msg_role = getattr(msg, 'role', '')
                    tool_call_id = getattr(msg, 'tool_call_id', None)
                    logger.debug(f"🔍 检查消息 #{i}: role={msg_role}, tool_call_id={tool_call_id}")
                    if (msg_role == 'tool' and 
                        hasattr(msg, 'tool_call_id') and 
                        msg.tool_call_id in tool_call_ids):
                        found_tool_responses.add(msg.tool_call_id)
                        logger.debug(f"🔍 找到工具响应: {msg.tool_call_id}")
                
                logger.debug(f"🔍 找到的工具响应: {found_tool_responses}")
                
                # 如果有未完成的工具调用，必须保留这个assistant消息及其后续所有消息
                pending_tool_calls = tool_call_ids - found_tool_responses
                logger.debug(f"🔍 未完成的工具调用: {pending_tool_calls}")
                if pending_tool_calls:
                    needed_count = len(messages) - last_assistant_idx
                    logger.debug(f"🔍 需要保留消息数: {needed_count}, 当前目标保留数: {target_keep_count}")
                    # 🔥 关键修复：无论需要保留的消息数是否大于目标数，都要确保完整性
                    if needed_count > target_keep_count:
                        logger.warning(f"🔥 检测到正在执行的工具调用 {pending_tool_calls}，强制保留 {needed_count} 条消息")
                        target_keep_count = needed_count
                    else:
                        # 即使needed_count较小，也要确保不破坏工具调用链
                        logger.warning(f"🔥 检测到正在执行的工具调用 {pending_tool_calls}，保持当前保留数量 {target_keep_count}")
                        # 验证当前保留数量是否足够包含完整的工具调用链
                        if last_assistant_idx < len(messages) - target_keep_count:
                            # 如果assistant消息不在保留范围内，强制调整
                            target_keep_count = len(messages) - last_assistant_idx
                            logger.warning(f"🔥 调整保留数量以包含完整工具调用链: {target_keep_count}")
                else:
                    logger.debug(f"🔍 所有工具调用都已完成")
        else:
            logger.debug(f"🔍 未找到任何工具调用assistant消息")
        
        # 分析从 target_keep_count 开始的消息
        start_idx = len(messages) - target_keep_count
        kept_messages = messages[start_idx:]
        
        # 检查是否有不完整的工具调用
        adjusted_keep_count = target_keep_count
        
        # 向前扫描，寻找可能被截断的工具调用链
        for i in range(max(0, start_idx - 10), start_idx):  # 向前检查最多10条消息
            msg = messages[i]
            role = getattr(msg, 'role', '')
            
            # 如果发现 assistant 消息包含 tool_calls
            if role == 'assistant' and hasattr(msg, 'tool_calls') and msg.tool_calls:
                # 检查后续的 tool 消息是否在保留范围内
                tool_call_ids = []
                try:
                    for tc in msg.tool_calls:
                        if hasattr(tc, 'id'):
                            tool_call_ids.append(tc.id)
                        elif isinstance(tc, dict) and 'id' in tc:
                            tool_call_ids.append(tc['id'])
                except:
                    continue
                
                if tool_call_ids:
                    # 检查对应的 tool 消息是否在保留范围内
                    tool_messages_in_kept = []
                    for j in range(i + 1, len(messages)):
                        next_msg = messages[j]
                        if (getattr(next_msg, 'role', '') == 'tool' and 
                            hasattr(next_msg, 'tool_call_id') and 
                            next_msg.tool_call_id in tool_call_ids):
                            tool_messages_in_kept.append(j)
                    
                    # 如果有 tool 消息在保留范围内，需要保留这个 assistant 消息
                    if any(j >= start_idx for j in tool_messages_in_kept):
                        needed_count = len(messages) - i
                        if needed_count > adjusted_keep_count:
                            adjusted_keep_count = needed_count
                            logger.debug(f"🔧 发现不完整工具调用链，扩展保留范围到 {adjusted_keep_count}")
        
        # 检查保留消息的开头是否有孤立的 tool 消息
        if kept_messages:
            first_msg = kept_messages[0]
            if getattr(first_msg, 'role', '') == 'tool':
                # 向前寻找对应的 assistant 消息
                tool_call_id = getattr(first_msg, 'tool_call_id', None)
                if tool_call_id:
                    for i in range(start_idx - 1, max(0, start_idx - 10), -1):
                        msg = messages[i]
                        if (getattr(msg, 'role', '') == 'assistant' and 
                            hasattr(msg, 'tool_calls') and msg.tool_calls):
                            # 检查是否包含对应的 tool_call_id
                            for tc in msg.tool_calls:
                                tc_id = getattr(tc, 'id', None) or (tc.get('id') if isinstance(tc, dict) else None)
                                if tc_id == tool_call_id:
                                    needed_count = len(messages) - i
                                    if needed_count > adjusted_keep_count:
                                        adjusted_keep_count = needed_count
                                        logger.debug(f"🔧 发现孤立 tool 消息，扩展保留范围到 {adjusted_keep_count}")
                                    break
                            break
        
        # 确保不超过总消息数
        return min(adjusted_keep_count, len(messages))

    def _truncate_context_messages(self, force: bool = False) -> bool:
        """截断早期的上下文消息，保留最新的部分"""
        try:
            # --- 若存在未完成的工具调用链，跳过截断以免破坏完整性 ---
            try:
                if (not force) and self._has_pending_tool_calls_in_messages():
                    logger.debug("🛑 检测到未完成的 tool 调用链，暂不截断以保持上下文完整")
                    return False
            except Exception:
                pass

            # --- 🔥 核心修复：直接使用当前运行中的消息列表 ---
            # 在运行中的 run 内部，直接使用 run_messages.messages
            messages = None
            
            # 优先使用当前运行的消息列表（最准确、最完整）
            if hasattr(self, 'run_messages') and self.run_messages and hasattr(self.run_messages, 'messages'):
                messages = self.run_messages.messages
                logger.debug(f"🔍 >>> 使用当前运行的 run_messages.messages: {len(messages)}条消息")
            else:
                # 回退到 memory 存储
                if not hasattr(self, 'memory') or not self.memory:
                    logger.warning("⚠️ 无法访问memory和run_messages，跳过截断")
                    return False
                
                # 检查Memory类型并获取消息
                if hasattr(self.memory, 'messages'):
                    # 旧版AgentMemory
                    messages = self.memory.messages
                    logger.debug(f"🔍 >>> 回退使用AgentMemory.messages: {len(messages) if messages else 0}条消息")
                else:
                    logger.warning("⚠️ 无法获取当前运行的消息列表，跳过截断")
                    return False
            
            if not messages:
                logger.warning("⚠️ 消息列表为空，跳过截断")
                return False
            
            # 计算要保留的消息数量
            total_messages = len(messages)
            keep_count = int(total_messages * self.keep_ratio)
            if keep_count < 1:
                keep_count = 1
            
            logger.debug(f"🔍 >>> 截断前: {total_messages}条消息，保留: {keep_count}条")
            
            # 🔥 关键修复：确保工具调用上下文完整性
            # 调整 keep_count 以保护完整的工具调用链
            adjusted_keep_count = self._ensure_tool_call_context_integrity(messages, keep_count)
            if adjusted_keep_count != keep_count:
                logger.info(f"🔧 为保护工具调用上下文，调整保留数量: {keep_count} -> {adjusted_keep_count}")
                keep_count = adjusted_keep_count
            
            # 保存被截断的旧消息以生成摘要
            truncated_messages = messages[:-keep_count]

            # 执行截断并同步到当前运行的消息列表
            kept_msgs = messages[-keep_count:]

            # 生成摘要并插入最前面，供后续模型参考
            if truncated_messages:
                summary_msg = self._create_truncation_summary(truncated_messages, len(truncated_messages))
                kept_msgs.insert(0, summary_msg)
                
            # 🔥 核心修复：直接修改当前运行的消息列表
            if hasattr(self, 'run_messages') and self.run_messages and hasattr(self.run_messages, 'messages'):
                self.run_messages.messages[:] = kept_msgs  # 原地替换
                logger.debug("🔥 已截断并更新 run_messages.messages")
            else:
                # 回退：修改 memory.messages（适用于旧版 AgentMemory）
                if hasattr(self.memory, 'messages'):
                    self.memory.messages = kept_msgs
                    logger.debug("🔥 已截断并回退更新 memory.messages")
                else:
                    logger.error("❌ 无法找到可修改的消息列表")
                    return False
            
            # 更新截断统计
            self.session_state['context_management']['truncation_count'] = \
                self.session_state['context_management'].get('truncation_count', 0) + 1
            self.session_state['context_management']['last_truncation_time'] = \
                datetime.now().isoformat()
            
            logger.info(f"✂️ 执行截断: {total_messages} -> {keep_count} 条消息，已生成摘要消息")

            return True
            
        except Exception as e:
            logger.error(f"❌ 截断失败: {e}")
            return False
    

 