# DeepDive 安全审计报告：CODE-REVIEW-ITEM-001 — 核心 Servlet 解析器安全审计

## 一、分配任务
**任务标识**：CODE-REVIEW-ITEM-001

**任务内容**：对以下核心代码/配置区域进行路径遍历、路径规范化绕过、路径注入等风险的白盒代码审计：
- `SlingServletResolver.java`
- `ServletResourceCollector.java` 及相关资源收集类
- `PathBasedServletAcceptor.java` 路径匹配逻辑

**优先级**：极高（核心 Servlet 解析入口，影响所有请求路由）


## 二、微行动计划与关键上下文应用
1. **读取部署架构报告**（`DeploymentArchitectureReport.md`）
   - 验证组件的部署上下文：仅作为 OSGi Bundle，无独立网络暴露；执行路径通过 OSGi 配置管理，默认允许“/”所有脚本执行。
2. **阅读并分析核心代码**
   - `resolveServletInternal`：判断绝对路径执行分支与深度查找分支的触发条件；分析对 `../`、`./`、URL 编码等的处理。
   - `isInvalidPath`：检查对“多于两个点”段的拒绝逻辑；是否允许“..”。
   - `ResourceUtil.normalize` 用于规范化相对路径，结合代码语义判断可否绕过。
   - `isPathAllowed` & `getExecutionPaths`：确认默认配置下执行路径开放程度。
   - `PathBasedServletAcceptor`：严格模式如何限制路径、扩展名、选择器、方法，默认是否启用。
3. **结合部署常识与报告校验**
   - 默认 `servletresolver_paths` 配置“/”，`getExecutionPaths` 将其标记为 `null`，表示允许所有路径执行。
   - 绝对路径分支依据 `ResourceUtil.normalize` 解析的路径，不存在外部公开暴露的脚本路径，无风险。
   - 深度查找分支仅基于 JCR 中已有脚本/servlet 资源，不接受未注册的任意文件系统路径。
4. **总结是否存在漏洞**
   - 考虑攻击向量：用户无法直接控制 `scriptNameOrResourceType`；核心解析逻辑安全；无条件路径遍历可利用。  


## 三、分析与发现

### 3.1 路径遍历与规范化绕过
- `isInvalidPath` 仅拒绝段内全部为`.`且长度>2（如“...”），允许“..”段。  
- 绝对路径执行分支：通过 `ResourceUtil.normalize` 将标准相对路径（含“..”）规范化后查询 JCR 资源。  
- JCR 资源解析的安全性由底层 Sling Resource API 提供，非文件系统直接访问，不存在经典文件系统路径遍历。  

### 3.2 路径注入
- 脚本/servlet 资源查找基于 OSGi 注册的 `SlingServletConfig` 与 JCR 资源类型，不直接拼接用户原始请求路径，注入攻击无入口。  

### 3.3 路径黑/白名单机制
- 默认执行路径为“/”（`executionPaths=null`），对所有注册脚本执行开放；并无单独内置黑名单，依赖部署时限动配置。  
- `PathBasedServletAcceptor` 严格模式需显式设置 `sling.servlet.paths.strict=true`，默认未启用。

### 3.4 编码格式处理
- `ResourceUtil.normalize` 未对 URL 编码、Unicode 编码额外处理；但脚本资源类型来源于 JCR 内容类型，未受编码路径直接影响。

## 四、安全审计师评估

| 评估项   | 说明                                                         |
|--------|------------------------------------------------------------|
| 可达性   | 作为 OSGi Bundle，在宿主 Sling 引擎中运行；默认未对外直接暴露特殊脚本路径，仅通过 Sling 引擎公开的 HTTP 接口。 | 
| 所需权限  | 仅可访问公开注册的 Script/Servlet 资源，无权限提升或文件系统访问能力。                      |
| 潜在影响  | 无——在默认部署与配置下，无法通过路径遍历、路径注入或编码绕过执行未注册的脚本或资源。            |


## 五、概念验证 (PoC)
**PoC**：无可利用路径遍历或注入漏洞，不存在可操作的攻击向量，跳过 PoC 部分。


## 六、尝试草拟 CVE 风格描述
> **无匹配漏洞** —— 审计中未发现符合高质量、证据确凿标准的漏洞，跳过 CVE 描述。


## 七、建议修复方案
- 如需更严格控制脚本执行路径，建议在 OSGi 配置中启用 `sling.servlet.paths.strict=true`，并根据需求配置 `sling.servlet.paths` 白名单。
- 在可能对外暴露的环境中，审慎配置执行路径，避免不必要的“/”全局开放。


---

*报告完毕*