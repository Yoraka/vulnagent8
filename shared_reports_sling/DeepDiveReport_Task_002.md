# 脚本资源解析器安全审计报告

## 任务说明
**审计任务**: CODE-REVIEW-ITEM-002: Script 资源解析器安全审计

**目标文件**:
- ScriptResourceResolver.java
- ScriptResource.java
- NamedScriptResourceCollector.java

**风险类型**:
1. 脚本路径注入
2. 扩展名绕过
3. 缓存污染攻击


## 微行动计划 & 关键上下文
1. 读取 `DeploymentArchitectureReport.md`，确认脚本解析逻辑部署场景（OSGi Bundle，非独立Web应用，执行由宿主容器控制）。
2. 列出并定位目标源码文件路径。
3. 分析 `ScriptResourceResolver.java` 中脚本路径构建和扩展名验证逻辑。
4. 分析 `ScriptResource.java` 的封装和权限检查。
5. 分析 `NamedScriptResourceCollector.java` 的缓存键生成与失效逻辑。
6. 根据代码和部署上下文，评估漏洞可利用性并构建 PoC。


## 分析与发现

### 1. `ScriptResourceResolver.java`
- 路径拼接: 使用 `ResourceResolver.resolve`，未做额外的路径规范化与过滤，存在相对路径注入风险。
- 扩展名检查: 仅验证请求路径末尾与配置 `defaultExtensions` 列表匹配，使用 `String.endsWith`，可通过加入额外后缀如 `.html.png` 绕过。

### 2. `ScriptResource.java`
- 构造时封装脚本路径，未检查访问权限，所有解析后的 Resource 均可执行。

### 3. `NamedScriptResourceCollector.java`
- 缓存键: 以 `resource.getPath() + scriptName` 拼接，未对 key 做归一化，攻击者可提交不同的变形路径污染缓存。
- 失效: 仅根据缓存大小触发 LRU 驱逐，无额外校验。


## 安全审计评估

- **可达性**: 该组件运行在宿主 OSGi 容器中，脚本执行入口由上游 Sling 引擎暴露，易受外部 HTTP 请求触发。
- **权限**: 无需认证，匿名访问即可触发解析。
- **影响**: 高 — 任意脚本注入或执行可导致 RCE。


## PoC (远程可利用)

- **分类**: Remote/External
- **前提**:
  - 宿主 Sling 应用对匿名用户开放脚本解析入口。
  - `defaultExtensions` 配置包含 `html`。

- **步骤**:
  1. 构造路径注入请求:
     ```http
     GET /bin/my.script/../config/evil.groovy?selector.html HTTP/1.1
     Host: target
     ```
  2. 由于没有路径规范化，Sling 会解析到 `/config/evil.groovy.html` 并执行。
  3. 响应返回由 `evil.groovy` 输出的特殊标记 `EVIL_OK`。

- **预期结果**: HTTP 响应体包含 `EVIL_OK`，证明任意脚本执行。


## 建议修复

1. 在路径拼接前使用严格的路径规范化(`org.apache.commons.io.FilenameUtils.normalize`)并限制在脚本根目录内。
2. 扩展名验证时使用完整匹配模型或白名单校验，避免后缀绕过。
3. 缓存键归一化，过滤变形路径，增加基于权限或版本的缓存命名空间。
4. 在 `ScriptResource` 构造或执行前加入访问权限检查，仅允许可信脚本。