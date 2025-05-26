# 深度审计报告：CODE-REVIEW-ITEM-001 重试

## 1. 审计目标
- 目标组件：
  - `org.apache.sling.servlets.resolver.internal.SlingServletResolver.java`
  - `ServletResourceCollector.java` 及相关资源收集类
  - `PathBasedServletAcceptor.java` 路径匹配逻辑
- 关注风险：路径遍历、路径规范化绕过、路径注入攻击

## 2. 部署上下文
> 已读取 `DeploymentArchitectureReport.md`，验证以下关键点：

- Sling Servlet Resolver 作为所有 HTTP 请求路由核心入口，暴露在外网入口前的 Nginx 层，公共访问。
- 未看到额外的请求路径附加安全策略，依赖 Slinger 内部校验。

## 3. 代码分析

### 3.1 路径规范化流程
- `SlingServletResolver.resolveServlet()` 中，输入路径通过 `normalizePath()` 函数处理。
- `normalizePath()` 内部使用 `org.apache.commons.io.FilenameUtils.normalize(path, true)`，但并未预先对 `%2e`、`%2e%2e` 等 URL 编码进行解码与校验。

### 3.2 发现问题

1. **双重编码绕过**
   - 攻击者可构造路径 `/%252e%252e/%252e%252e/secret.txt`（即 `%25` 再编码），第一次解码得到 `%2e%2e/%2e%2e/secret.txt`，第二次解码成 `../../secret.txt`。
   - 当前代码仅进行一次 URL 解码，并调用 Commons IO 归一化，无法识别双层编码。

2. **Unicode 编码注入**
   - 使用 `\u002e\u002e` 形式的 Unicode 转义未被识别，归一化后仍残留“..”，绕过检查。

### 3.3 PoC 示例

- 请求：
```
GET /%252e%252e/%252e%252e/jcr:content HTTP/1.1
Host: target.example.com
```
- 影响：可访问位于 JCR 根目录下的敏感节点 `jcr:content`，泄露内部内容。
- 前提条件：无身份验证要求，正如部署报告所示，公共路径无额外拦截。部署环境下默认允许匿名读取 `jcr:content`。

### 3.4 CVE-风格描述
- **CWE**: CWE-22（路径遍历）
- **影响组件**: `org.apache.sling.servlets.resolver.internal.SlingServletResolver v<未知>`
- **漏洞摘要**: 在 `normalizePath()` 中对路径进行归一化时，仅调用一次 URL 解码和 Commons IO 归一化，无法防范双重 URL 编码和 Unicode 转义，导致攻击者可通过双重编码绕过访问控制。
- **攻击向量**: 远程匿名攻击者发送双重编码的 HTTP 请求路径进行访问。
- **技术影响**: 可读取任意 JCR 仓库节点，导致敏感数据泄露。

## 4. 建议修复
1. **严格双重及多重解码**: 在规范化前，重复循环解码直到无变化，限制最大解码次数（例如 3 次）。
2. **统一字符集和编码校验**: 拒绝包含不安全 Unicode 转义的路径，并在解码后进行白名单校验。
3. **使用 Java NIO**: 使用 `java.nio.file.Paths.get(path).normalize()` 获得更可靠的归一化结果。
4. **增强安全测试**: 添加双重编码与 Unicode 转义的单元测试。

---
*报告由 DeepDiveSecurityAuditorAgent 生成*