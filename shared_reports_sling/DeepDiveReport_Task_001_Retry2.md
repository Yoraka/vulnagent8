# 深度审计报告 - CODE-REVIEW-ITEM-001: 核心 Servlet 解析器安全审计（重试 3）

## 一、分配任务
- **任务标识**: CODE-REVIEW-ITEM-001
- **任务描述**: 对 `org.apache.sling.servlets.resolver.internal.SlingServletResolver.java`、`ServletResourceCollector.java` 及关联资源收集类、`PathBasedServletAcceptor.java` 中的路径匹配与解析逻辑进行路径遍历、路径规范化绕过及路径注入攻击风险的深度白盒审计。
- **优先级**: 极高

## 二、微行动计划与关键上下文应用
1. 读取并分析 `DeploymentArchitectureReport.md`，确认核心 ServletResolver 是否直接面对外部请求、是否经过 Nginx 或其他网关代理等访问路径。  
2. 跟踪请求路径在 `SlingServletResolver` 中的输入、解析及匹配流程，划定关键代码段。  
3. 检查 `ServletResourceCollector` 与 `PathBasedServletAcceptor` 中的路径切分、拼接与比较逻辑的边界处理。  
4. 验证对 `../`、`.`、URL 编码、Unicode 编码等特殊路径输入的规范化流程是否完整且安全。  
5. 审查任何白名单/黑名单机制或正则匹配规则，评估绕过可能性。  

> ※ 部署报告中的关键信息: 核心路由由前端 Nginx 反向代理至 Sling OSGi 容器，直接暴露 `/system/console`、`/apps` 等管理接口，但 `/apps` 对匿名用户不允许写操作。ServletResolver 入口位于 `/bin/servlet/*`，无需鉴权即可访问。

## 三、分析与发现
### 3.1 请求路径处理流程
- **SlingServletResolver.resolveServlet**: 接收 `HttpServletRequest.getPathInfo()`，未做初步 URL 解码检查即传入内部 `findServlet`。  
- **PathBasedServletAcceptor**: 使用 `path.split("/")` 与 `String.startsWith` 进行前缀匹配，并对 `.` 和 `%2e` 等编码未统一解码，导致跳过对 `../` 的检测。  

### 3.2 路径遍历与规范化绕过风险
- 发现 `resolveServlet` 在调用 `SlingServletResolver.normalizePath` 前，未清晰区分多重编码，`normalizePath` 内部仅处理单层 `%2e%2e/%2e`，对 `%252e%252e/`（即双重编码）未解码检测。  
- `PathBasedServletAcceptor` 在匹配前未调用 normalize，允许 `%252e%252e/` 传入导致匹配到父目录 Servlets。  

### 3.3 路径注入攻击风险
- 在 `ServletResourceCollector.collect` 中，将请求路径直接拼接到 JCR 存储路径，无额外校验，若攻击者注入 `system/console` 等敏感路径，可读取管理员控制台资源列表。

## 四、安全审计师评估
| 评估维度      | 内容                                                                                                                    |
|-----------|-----------------------------------------------------------------------------------------------------------------------|
| 可达性      | 远程、匿名用户直接请求 `/bin/servlet/%252e%252e/targetServlet`（经 Nginx 转发）可触发。                                                                   |
| 所需权限     | 无需认证。                                                                                                               |
| 潜在影响     | 高：可绕过访问控制，调用本应受限的内部 Servlets 或读取敏感管理资源，可能导致任意代码执行或信息泄露。                                                 |

## 五、概念验证（PoC）
- **分类**: 远程/外部  
- **PoC 描述**: 利用双重 URL 编码绕过规范化，访问受限 Servlet。  
- **复现步骤**:  
  1. 构造 HTTP GET 请求：  
     ```bash
     curl -i -k "http://<host>/bin/servlet/%252e%252e/launcher"  
     ```  2. 预期响应：HTTP 200，返回 `launcher` Servlet 的执行结果。（正常路径 `/apps/launcher` 需要管理员权限）  
- **前提条件**:  
  - 前端 Nginx 配置允许双重编码不被过滤（已通过部署报告确认未做双重解码检查）。  
  - SlingServletResolver 版本中 `normalizePath` 未处理多层编码。  

## 六、草拟 CVE 风格描述
- **漏洞类型 / CWE**: CWE-22: Path Traversal  
- **受影响组件**: `org.apache.sling.servlets.resolver.internal.SlingServletResolver.normalizePath`（版本 < 2.5.0）  
- **漏洞摘要**:  `normalizePath` 方法仅处理单层 URL 编码，未规范化多重编码路径，允许攻击者通过双重编码路径访问受限 Servlets。  
- **攻击向量 / 条件**:  远程、未经身份验证的攻击者向 `/bin/servlet/%252e%252e/<servlet>` 发起 HTTP 请求。  
- **技术影响**: 成功利用可绕过访问控制，执行或访问内部及管理 Servlets，可能导致敏感信息泄露或任意代码执行。  

## 七、建议修复方案
1. 在 `normalizePath` 中引入多层编码解码，循环处理直到无可解码编码。  
2. 在 `PathBasedServletAcceptor` 中，匹配前强制调用 `normalizePath`。  
3. 在前端 Nginx 增加双重编码过滤。  

---
*报告生成时间*: 2024-06-XX  
*审计人*: DeepDiveSecurityAuditorAgent