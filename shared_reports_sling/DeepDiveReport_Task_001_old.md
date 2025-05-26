# DeepDiveSecurityAuditorAgent 深度审计报告：CODE-REVIEW-ITEM-001

## 1. 分配任务
**任务标识**: CODE-REVIEW-ITEM-001

**审计范围**:
- 核心 Servlet 解析器安全审计，重点关注路径遍历、路径规范化绕过和路径注入风险。
- 目标文件：
  - `SlingServletResolver.java`
  - `ServletResourceCollector.java` 及相关资源收集类
  - `PathBasedServletAcceptor.java`

**潜在风险类型**:
1. 路径遍历漏洞
2. 路径规范化绕过
3. 路径注入攻击

**部署上下文**: 该组件作为 OSGi Bundle 运行于 Apache Sling 引擎中，由主机容器（Jetty/Nginx）对外提供 HTTP 服务，影响所有请求路由，优先级极高。

---

## 2. 微行动计划与关键上下文应用
1. 读取并分析 `DeploymentArchitectureReport.md`，确认组件在 OSI 容器中的部署模式及安全边界。
2. 静态代码审计：
   - 路径归一化与检查：检查 `ResourceUtil.normalize`、`isPathAllowed`、`resolveServletInternal` 中路径处理逻辑。
   - 路径选择与权限：审查 `PathBasedServletAcceptor.accept` 方法对 selectors、extensions、HTTP 方法、严格路径模式的验证。
   - 编码处理：评估对 URL 编码/Unicode 等特殊字符的处理及潜在绕过风险。
3. 结合部署上下文评估可达性与前提条件。
4. 根据发现提炼风险场景，尝试构建 PoC 步骤（理论性说明）。
5. 撰写详细报告，包含可达性、权限需求、影响评估、PoC 细节与修复建议。

---

## 3. 关键发现与分析

### 3.1 路径归一化与检查
- 在 `resolveServletInternal` 中，对以 `/` 开头的脚本路径调用 `ResourceUtil.normalize`。根据源码，normalize 会去掉双斜杠和 `.`、`..` 等，但**未进行严格的 URL 解码处理**。若请求路径中包含 `%2e%2e/` 等编码，客户端绕过 normalize 后直接调用此逻辑，可能引发路径遍历。
- 方法 `isPathAllowed(path, executionPaths)`：
  - 若 `executionPaths` 未配置或包含 `/`，所有路径都被允许；部署报告表明默认 `servletresolver_paths` 配置为根 (`/`)，即允许任意子路径执行，降低安全性。
  - 对`..`或`./`的处理仅依赖 `normalize`，未校验重解码后路径是否回退到白名单以外的父目录。

### 3.2 严格路径检查（PathBasedServletAcceptor）
- `PathBasedServletAcceptor.accept` 仅在 OSGi 属性 `sling.servlet.paths.strict=true` 时启用严格匹配。默认未开启，导致大多数路径挂载的 Servlet 无选择器或扩展名验证，增加攻击面。
- 对 selectors 和 extensions 的比较基于字符串相等，不关心编码变体或多值注入。

### 3.3 编码处理与注入风险
- 整个流程对 URL 编码/Unicode 编码没有统一解码策略：请求经过容器解码后，Sling API 返回的 `request.getRequestPathInfo()` 已部分解码，但若分段编码（双重编码），仍有可能绕过 `normalize`。
- 未对点号（`.`）和斜杠（`/`）进行额外过滤，`${path}/`、`%2e%2e/` 等构造可能绕过检查。

---

## 4. 安全审计师评估

| 评估项   | 描述                                                                                                           |
|---------|----------------------------------------------------------------------------------------------------------------|
| 可达性   | 组件位于 Sling 引擎核心，HTTP 请求可通过主机容器公开访问；任何外部请求均会触及此解析器。                                          |
| 所需权限 | 公开无认证访问（匿名用户）。                                                                                         |
| 影响     | 高：利用路径遍历或绕过可访问或执行非授权脚本/Servlet，导致任意代码执行或信息泄露。                                          |

---

## 5. 概念验证 (PoC)

**分类**: 远程/外部

**PoC 简要说明**: 利用双重 URL 编码绕过 `normalize` 并通过 `isPathAllowed` 执行未授权脚本。

**复现步骤**:
1. 部署并运行 Apache Sling 附加了本 Bundle 的 Sling 引擎，确保 `servletresolver_paths` 包含 `/apps` 或为默认根路径 `/`。
2. 在 `/apps/mysite` 下放置测试 Servlet，如 `/apps/mysite/traversalTest`，内容返回固定标识 `TRAVERSAL_OK`。
3. 发送 HTTP 请求（匿名访问）：
   ```
   GET /%252e%252e/apps/mysite/traversalTest HTTP/1.1
   Host: target
   ```
   说明：`%252e` 解码一次后为 `%2e`，再解码后为 `.`，双重编码绕过单次 `normalize`。
4. 观察响应体包含 `TRAVERSAL_OK`，证明已成功调用目录外的脚本。

**预期结果**: HTTP 200，响应体包含 `TRAVERSAL_OK`。

**关键前提条件**:
- `servletresolver_paths` 配置为根路径或包含目标 Servlet 所在目录。
- Sling 引擎对 `%252e` 只解码一次才进行 `normalize`。

---

## 6. 修复建议

1. **统一解码与严格归一化**: 在 `resolveServletInternal` 前，对请求路径进行完全解码，并使用 Apache Commons `NormalizedPath` 等库进行安全归一化。
2. **强化白名单路径策略**: 避免默认根路径执行，建议显式配置允许的执行目录，并在 `isPathAllowed` 中拒绝含 `..` 或非法字符的路径。
3. **启用严格路径检查**: 在 OSGi 配置中开启 `sling.servlet.paths.strict=true`，为挂载的 Servlet 指定明确的 selectors、extensions 和 HTTP 方法限制。
4. **增加安全测试**: 对 URL 编码、Unicode 编码和特殊分段路径进行单元测试，确保 `normalize` 后路径不能绕过检查。

---

*报告作者: DeepDiveSecurityAuditorAgent*
*日期: 2024-06-19*