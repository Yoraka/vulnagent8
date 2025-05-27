# 精炼攻击面调查计划：CODE-REVIEW-ITEM-002

## 原始接收的任务描述

**CODE-REVIEW-ITEM-002: Web UI (Gradio) 输入验证与输出编码**
*   **目标代码/配置区域**:
    *   `webui.py` 主应用入口文件。
    *   所有Gradio接口定义文件 (例如用户提到的 `src/webui/interface.py`，以及其他构建Gradio UI元素和处理回调的Python文件)。
    *   所有处理用户输入并将其传递给后端逻辑或在UI中展示的函数。
*   **要审计的潜在风险/漏洞类型**:
    1.  **主动缺陷**: 跨站脚本 (XSS) - 反射型和存储型（如果输入未正确净化并在UI中显示）。
    2.  **主动缺陷**: 命令注入（如果用户输入被不安全地用于构造系统命令）。
    3.  **主动缺陷**: 服务器端请求伪造 (SSRF) (如果用户输入被用于构造对内部或外部服务的请求）。
    4.  **主动缺陷**: 路径遍历 （如果用户输入用于文件系统操作）。
    5.  **被动缺失**: Gradio组件配置不当，可能导致信息泄露或非预期行为。
*   **建议的白盒代码审计方法/关注点**:
    1.  审计所有Gradio输入字段的处理逻辑，检查是否对用户输入进行了严格的验证、净化或编码，以防止XSS和注入。
    2.  审查Gradio回调函数，特别是那些接收用户输入并执行后端操作的函数，关注数据如何被使用。
    3.  检查所有将数据显示在UI上的地方，确保执行了恰当的HTML编码。
    4.  Gradio本身可能提供一些安全特性，检查其是否被正确使用。
*   **部署上下文与优先级**: Web UI (端口 7788) 是主要的用户交互入口。**优先级：高**。

## 精炼的攻击关注点/细化任务列表

### 1. 跨站脚本 (XSS)

*   **关注点 1.1: `gr.Chatbot` 中的用户输入和Agent输出渲染**
    *   **文件与函数**:
        *   `src/webui/components/browser_use_agent_tab.py`:
            *   `run_agent_task` 函数内: `webui_manager.bu_chat_history.append({"role": "user", "content": task})`
            *   `handle_submit` 函数内: `webui_manager.bu_chat_history.append({"role": "user", "content": response})`
            *   `_handle_new_step` 函数 (通过 `step_callback_wrapper` 调用): `final_content` (包含 `_format_agent_output` 的结果和截图HTML) 被添加到 `webui_manager.bu_chat_history`.
            *   `_ask_assistant_callback` 函数: `webui_manager.bu_chat_history.append({"role": "assistant", "content": f"**Need Help:** {query}..."})`
            *   `_format_agent_output` 函数: `json.dumps` 的输出用 `<pre><code>` 包装。
    *   **理由**: 用户的原始文本输入 (`task`, `response`) 以及Agent的输出（包括来自LLM的潜在内容 `query`, 或格式化的JSON `AgentOutput`）被直接或间接添加到聊天历史中。如果Gradio的 `gr.Chatbot` 组件在渲染这些内容时未进行充分的HTML编码，恶意构造的输入可能导致XSS。特别注意 `_format_agent_output` 中 `json.dumps` 的 `ensure_ascii=false` 参数和 `<pre><code>` 包装，以及 `_handle_new_step` 中截图HTML的构建。
    *   **建议检查**:
        *   Gradio `gr.Chatbot` 对聊天消息内容的默认HTML编码行为。
        *   输入 `task` 和 `response` 是否可以包含并执行HTML/JavaScript。
        *   `AgentOutput` 的各字段和 `query` 是否可能包含未净化的、可导致XSS的HTML片段。

*   **关注点 1.2: `gr.Markdown` 组件的内容渲染**
    *   **文件与函数**:
        *   `src/webui/components/deep_research_agent_tab.py`:
            *   `run_deep_research` 函数内: 从 `plan_file_path` 和 `report_file_path` 读取内容并通过 `gr.update(value=plan_content/report_content)` 更新 `markdown_display` 组件。Agent执行错误 `e` 也可能被格式化并显示。
            *   `stop_deep_research` 函数内: 从 `report_file_path` 读取内容并更新 `markdown_display`。
    *   **理由**: `.md`文件的内容（可能受用户输入间接影响）或错误信息被传递给 `gr.Markdown` 组件。需确认该组件如何处理嵌入的HTML标签和JavaScript。如果处理不当，可能导致XSS。
    *   **建议检查**:
        *   Gradio `gr.Markdown` 组件对原始HTML和JavaScript的默认处理行为 (是否会过滤或直接渲染)。
        *   `research_plan.md` 和 `report.md` 的内容生成过程，是否存在用户输入未净化直接写入文件的可能性。

*   **关注点 1.3: `mcp_json_file` 内容在 `gr.Textbox` 中显示**
    *   **文件与函数**:
        *   `src/webui/components/agent_settings_tab.py`: `update_mcp_server` 函数。
        *   `src/webui/components/deep_research_agent_tab.py`: `update_mcp_server` 函数。
    *   **代码片段**: `mcp_server_config = gr.Textbox(label="MCP server", ...)`，其值来自 `json.dumps(mcp_server, indent=2)`。
    *   **理由**: 用户上传的JSON文件内容，经过 `json.load` 和 `json.dumps` 后，被设置到 `mcp_server_config` (一个 `gr.Textbox`) 中。如果 `json.dumps` 的输出（特别是字符串值）包含HTML特殊字符，并且Gradio的 `gr.Textbox` 在显示时未完全编码，可能导致XSS。
    *   **建议检查**: `gr.Textbox` 如何渲染其内容，特别是多行文本时。`json.dumps` 是否可能产生可利用的HTML字符序列。

*   **关注点 1.4: 配置项在UI中回显**
    *   **文件与函数**: 遍布各个 `components` 文件，如 `agent_settings_tab.py`。
    *   **涉及组件**: `gr.Textbox` (如 `override_system_prompt`, `llm_base_url`), `gr.Dropdown` (如 `llm_model_name` 通过 `update_model_dropdown` 填充)。
    *   **理由**: 如果这些配置项的值（来自用户输入）在UI的其他地方（例如，通过 `gr.Info`, `gr.Warning`, `gr.Error`，或动态更新的 `label`/`info` 属性）被回显而未进行HTML编码，则存在XSS风险。
    *   **建议检查**: 查找所有将用户输入的配置值重新显示在UI上的点，确认是否有适当的编码。

### 2. 路径遍历 / 任意文件操作

*   **关注点 2.1: 浏览器相关路径配置**
    *   **文件与函数**: `src/webui/components/browser_use_agent_tab.py`中的`run_agent_task`函数，它会读取`browser_settings_tab.py`中定义的组件值。
    *   **涉及配置项**: `browser_user_data_dir`, `save_recording_path`, `save_trace_path`, `save_agent_history_path`, `save_download_path` (从 `browser_settings` Tab获取)。
    *   **代码片段**: `os.makedirs(save_agent_history_path, exist_ok=true)` 等。`history_file` 和 `gif_path` 的构建也依赖 `save_agent_history_path`。
    *   **理由**: 如果用户可以完全控制这些路径配置字符串，并且后端代码（如 `os.makedirs`, `open`, `agent.save_history`）在使用这些路径前未进行严格的规范化（例如，解析 `../`）和验证（例如，检查是否在预期的基础目录下），则可能导致在服务器任意位置创建目录、写入或读取文件。
    *   **建议检查**:
        *   这些路径配置项的输入方式和验证逻辑。
        *   所有使用这些路径进行文件系统操作的地方，确认路径的拼接和使用是否安全。

*   **关注点 2.2: Deep Research Agent 的保存目录和任务ID**
    *   **文件与函数**: `src/webui/components/deep_research_agent_tab.py` 中的 `run_deep_research` 和 `_read_file_safe`。
    *   **涉及配置项/变量**: `max_query` (实际是 `base_save_dir` 输入框), `resume_task_id`。
    *   **代码片段**: `os.makedirs(base_save_dir, exist_ok=true)`，路径拼接如 `os.path.join(base_save_dir, str(running_task_id), "research_plan.md")`。
    *   **理由**: 用户提供的 `base_save_dir` 和（可能被操纵的）`resume_task_id` 被用于构建文件和目录路径。如果 `base_save_dir` 可控且包含 `../`，或 `resume_task_id` 可包含路径字符，可能导致路径遍历，从而在非预期位置创建目录、读取或写入文件。
    *   **建议检查**:
        *   `base_save_dir` 和 `resume_task_id` 输入的净化和验证。
        *   路径拼接的安全性。

*   **关注点 2.3: `mcp_json_file` 文件上传处理**
    *   **文件与函数**: `src/webui/components/agent_settings_tab.py` 和 `src/webui/components/deep_research_agent_tab.py` 中的 `update_mcp_server` 函数。
    *   **理由**: 虽然Gradio的 `gr.File` 通常将上传的文件保存到临时位置，但需要确认回调函数 `update_mcp_server` 中的 `mcp_file` 参数（类型为 `str`，应为Gradio提供的临时文件路径）的处理。如果该路径字符串可以被某种方式操纵（例如，通过原始文件名或Gradio的内部处理缺陷），并且 `os.path.exists(mcp_file)` 或 `open(mcp_file, 'r')` 未能正确处理，则理论上存在风险。主要风险在于文件内容，但路径处理也需确认。
    *   **建议检查**: Gradio如何处理上传的文件名并生成临时文件路径，以及 `update_mcp_server` 中对该路径的使用是否安全。

### 3. 命令注入

*   **关注点 3.1: 浏览器二进制路径配置**
    *   **文件与函数**: `src/webui/components/browser_use_agent_tab.py` 的 `run_agent_task` 函数，读取 `browser_settings` Tab的 `browser_binary_path`。
    *   **代码片段**: `webui_manager.bu_browser = CustomBrowser(config=BrowserConfig(browser_binary_path=browser_binary_path, ...))`
    *   **理由**: 如果用户可以设置 `browser_binary_path` 指向一个恶意可执行文件，并且 `CustomBrowser` (或其依赖的库如Playwright) 在启动浏览器时直接使用此路径而未加验证，则可能导致命令注入。
    *   **建议检查**:
        *   `browser_binary_path` 的输入验证。
        *   `CustomBrowser` 如何处理和使用 `browser_binary_path` 参数来启动进程。是否允许执行任意路径的程序。

### 4. 服务器端请求伪造 (SSRF)

*   **关注点 4.1: LLM基础URL配置**
    *   **文件与函数**: `src/webui/components/browser_use_agent_tab.py` 的 `_initialize_llm` 函数 (间接通过`run_agent_task`调用)，读取 `agent_settings` Tab的 `llm_base_url` 和 `planner_llm_base_url`。
    *   **代码片段**: `llm_provider.get_llm_model(..., base_url=llm_base_url or null, ...)`
    *   **理由**: 用户提供的 `llm_base_url` 和 `planner_llm_base_url` 被用于初始化LLM Provider。如果 `get_llm_model` 或其内部调用的HTTP客户端库（如 `requests`, `httpx`）直接使用这些URL发起网络请求，而没有对URL的目标、协议、端口等进行严格的白名单校验或限制，则攻击者可能构造恶意URL指向内部网络服务，导致SSRF。
    *   **建议检查**:
        *   `llm_base_url` 和 `planner_llm_base_url` 的输入验证。
        *   `llm_provider.get_llm_model` 及其调用的网络库如何处理这些自定义URL，是否有SSRF防护措施（如IP黑名单、域名白名单、禁止file://等协议）。

### 5. Gradio组件配置与一般安全

*   **关注点 5.1: `allow_custom_value=true` 在下拉框中的使用**
    *   **文件与函数**: `src/webui/components/agent_settings_tab.py`。
    *   **涉及组件**: `llm_model_name`, `planner_llm_model_name`, `tool_calling_method` (虽然不是直接路径或URL，但若其值被不当使用也可能引发问题)。
    *   **理由**: 允许自定义值增加了输入向量。如果这些自定义值未在后端被正确验证和处理（例如，用作文件名、命令参数或直接在日志/UI中未编码地显示），则可能引入各种风险。
    *   **建议检查**: 这些自定义值在后端逻辑中的具体用途和处理方式。

*   **关注点 5.2: 输出编码的普遍性**
    *   **理由**: 除了上述明确指出的XSS点，需要系统性检查所有将用户提供的数据（直接或间接）或Agent处理结果显示在Gradio UI上的地方，确保实施了正确的上下文编码 (HTML实体编码, URL编码, JavaScript编码等)。
    *   **建议检查**: 审查Gradio各组件的默认安全行为，以及应用代码中任何手动构建HTML或JavaScript的地方。

---
**特别注意：本Agent输出的所有建议、关注点和细化任务仅作为下阶段Agent的参考和建议，绝不构成硬性约束或限制。下阶段Agent有权根据实际情况补充、调整、忽略或重新评估这些建议。**