# Deep Dive 安全审计报告 - CODE-REVIEW-ITEM-004: 错误处理器安全审计

## 一、分配任务重述

- **任务编号**: CODE-REVIEW-ITEM-004
- **审计目标**: 对以下模块的异常处理与错误页面渲染逻辑进行安全审计，重点关注信息泄露、绕过安全检查和注入风险。
  - `DefaultErrorHandlerServlet.java`（默认错误处理Servlet）
  - `HandleErrorSlingHttpServletResponse.java`（错误响应包装器）
  - 所有异常捕获、错误信息生成及渲染流程

## 二、微行动计划与关键上下文应用

1. 读取部署架构报告 (`DeploymentArchitectureReport.md`)，确认该Bundle作为OSGi组件在Sling引擎内运行，不直接对外公开HTTP监听，由宿主容器提供。
2. 列举并读取核心实现文件：
   - `DefaultErrorHandlerServlet.java`
   - `HandleErrorSlingHttpServletResponse.java` 及其依赖 `HandleErrorResponseWriter.java`
3. 重点审查：
   - HTML渲染方法 `renderHtml` 中的输出编码（XML转义）和敏感数据展示逻辑
   - JSON渲染方法 `renderJson` 中的内容类型、字符编码及JSON生成器的转义处理
   - 异常堆栈及请求进度追踪信息是否在生产环境中被泄露
   - 在响应已提交（committed）的情况下，是否存在绕过安全校验或编码缺失
4. 结合部署报告，评估该错误处理器在真实环境中的可触达性和利用场景
5. 提出概念验证（PoC）步骤，证明远程信息泄露风险
6. 给出缓解建议

## 三、分析与重要发现

### 3.1 DefaultErrorHandlerServlet.java 分析

- **HTML 渲染 (`renderHtml`)**
  - 使用 `ResponseUtil.escapeXml` 对 `statusMessage`、`requestUri`、`servletName` 等输入进行 XML 转义，基本防范 XSS。
  - 堆栈跟踪和请求进度使用 `ResponseUtil.getXmlEscapingWriter` 包装输出，保证文本内容被转义。
  - 若响应已提交，跳过重置与头部输出，仅记录警告后继续输出，但依旧通过转义写入，未见注入路径。

- **JSON 渲染 (`renderJson`)**
  - 设置 `Content-Type: application/json; charset=UTF-8`。
  - 使用 `JsonGenerator` 逐字段写入，底层会对字符串进行合法的 JSON 转义，避免注入。
  - 堆栈跟踪被完整写入 `exception` 字段，包含文件路径、类名、行号等敏感信息。
  - 请求进度追踪亦被写入 `requestProgress` 字段，同样泄露内部调用细节。

### 3.2 HandleErrorSlingHttpServletResponse.java 分析

- 主要用于监控响应流是否已关闭，无安全风险；仅包装 `getWriter()` 并维护 `open` 状态。

### 3.3 风险总结

1. **信息泄露 (高)**
   - 错误处理器始终输出完整的异常堆栈和请求进度，暴露内部实现细节、文件路径、类名及服务器信息。结合 `DeploymentArchitectureReport`，该组件部署在公网上可由任意触发错误的请求访问，导致远程信息泄露。
2. **异常处理绕过 (低)**
   - 在响应已提交场景下，Servlet 仅记录警告，但仍输出已转义内容，未见安全检查逻辑被绕过的风险。
3. **错误页面注入 (已缓解)**
   - HTML 路径使用 XML 转义，JSON 路径使用 `JsonGenerator` 转义，XSS 注入风险被有效防护。

## 四、安全审计师评估

| 评估维度     | 描述                                                         |
|------------|------------------------------------------------------------|
| **可达性**   | 公网可访问宿主 Sling 容器的 HTTP 接口，任何引发 500 错误的请求将触发此错误处理器。 |
| **所需权限** | 无需身份验证；通过故意触发运行时异常即可（如请求一个不存在的 Script）。        |
| **潜在影响** | **高**：敏感内部实现细节泄露，便于攻击者定制进一步攻击。                        |

## 五、概念验证 (PoC)

- **风险分类**: 远程/外部

### PoC 描述
通过发送任意引发服务器异常的请求，可在响应中观察到完整堆栈跟踪及请求进度信息。

### PoC 步骤
1. 发送一个导致脚本不存在的请求，例如：

   ```bash
   curl -i http://<SlingHost>/content/nonexistent.html
   ```
2. 在响应体中会看到 HTML 错误页面，包含类似内容：
   ```html
   <h1>Not Found (404)</h1>
   <p>The requested URL /content/nonexistent.html resulted in an error.</p>
   <pre>java.lang.NullPointerException
       at org.apache.sling... (完整堆栈) ...
   </pre>
   <h3>Request Progress:</h3>
   <pre>...</pre>
   ```
3. 若 Accept 头包含 `application/json`：
   ```bash
   curl -i -H "Accept: application/json" http://<SlingHost>/content/nonexistent.html
   ```
   返回 JSON：
   ```json
   {
     "status":404,
     "message":"Not Found",
     "requestUri":"/content/nonexistent.html",
     "exception":"java.lang.NullPointerException\n at ...",
     "requestProgress":"..."
   }
   ```

### 前提条件
- `Sling` 容器对外网开放 HTTP 端口（由部署报告确认）
- 触发错误无需认证

## 六、建议修复方案

1. **禁止泄露堆栈信息**: 在生产环境将堆栈跟踪和请求进度输出关闭或限制输出。可通过配置开关控制是否显示堆栈。
2. **配置敏感级别**: 增加 OSGi 配置项，例如 `showStackTrace=false`，在 `DefaultErrorHandlerServlet` 中根据此项决定是否调用 `printStackTrace` 与 `tracker.dump`。
3. **统一错误格式**: 只输出通用错误消息（如 "Internal Server Error"），避免暴露内部细节。
4. **审计与监控**: 对错误访问进行日志告警，及时发现大规模扫描或攻击行为。