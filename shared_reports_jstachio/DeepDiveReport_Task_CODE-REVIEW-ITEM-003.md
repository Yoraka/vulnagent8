# 深度审计报告：CODE-REVIEW-ITEM-003 核心API模块运行时安全审计（含XSS检查）

## 一、审计范围及目标
**路径**：`api/jstachio/src/main/java/io/jstach/jstachio/`

**关注点**：
1. 运行时模板注入
2. 不安全的反射使用导致权限绕过
3. 类型检查绕过导致类型混淆攻击
4. **XSS风险审计**：输出编码与转义机制

---

## 二、关键发现

### 1. 运行时模板注入
- JStachio 为编译时模板引擎，不支持运行时动态模板加载与执行。
- Core API 仅加载预编译模板，生产环境默认禁用回退渲染（`jstachio.jmustache.disable=true`）。
- **结论**：风险极低。

### 2. 不安全的反射使用
- 未发现核心渲染路径中存在不安全的反射（如任意方法执行或字段修改）。
- 反射主要用于ServiceLoader和模板类加载，受集中逻辑控制。
- **结论**：暂无明确风险。

### 3. 类型检查绕过
- `DefaultFormatter` 委托将对象转为字符串后交给 `Escaper` 处理。
- `Template<T>` 与 `TemplateModel.of(Template<T>, T)` 强制编译时类型匹配。
- **结论**：无明显类型混淆漏洞。

### 4. XSS风险审计
#### 4.1 转义逻辑分析
- `HtmlEscaper` 对 `& < > "` 执行HTML实体转义，**但不转义单引号 `'`**。
- `NoEscaper`（`PlainText.of()`）不执行任何转义。
- `DefaultFormatter` 仅负责转为字符串/调用 `ContextNode.renderString()`，并不做转义。

#### 4.2 数据流
1. 模型数据 -> `Renderer` (生成码)
2. 动态数据 -> `Formatter` (字符串化)
3. 字符串 -> `Escaper` (默认 `HtmlEscaper`)
4. 转义后结果 -> `Output`

#### 4.3 强制或误用Escaper风险
- 若开发者显式使用 `NoEscaper`/`PlainText.of()`，则HTML上下文中的用户输入将不被转义。
- Mustache 的未转义语法（如 `{{{variable}}}`）若被支持并误用，也会绕过转义。

#### 4.4 单引号未转义漏洞
**核心缺陷**：`HtmlEscaper` 未将单引号 `'` 转义，导致在HTML属性使用单引号时可触发XSS。支持上下文为 `<input type='text' value='{{userInput}}'>`。

---

## 三、概念验证(PoC)
**XSS PoC：单引号未转义**
1. 模板示例：
   ```html
   <input type='text' value='{{searchTerm}}'>
   ```
2. 用户输入：
   `' autofocus onfocus='alert("XSSed: " + document.cookie)' data-dummy='`
3. 渲染后：
   ```html
   <input type='text' value='payload' autofocus onfocus='alert("XSSed: " + document.cookie)' data-dummy=''>
   ```
4. 当输入框聚焦时执行 `alert`。

---

## 四、风险评级
- XSS：中到高（取决于应用层配置）
- 运行时模板注入：低
- 反射/类型混淆：低

---

## 五、修复建议
1. **立即修复单引号转义**：在 `HtmlEscaper` 中将 `'` 转义为 `&#39;` 或 `&apos;`。
2. **强化使用规范**：
   - 默认强制HTML转义，禁止在HTML上下文中使用 `PlainText.of()` 或 `{{{var}}}` 处理用户输入。
   - 文档中强调正确使用 `Escaper` 与模板类型匹配。
3. **双重防护**：应用层应实施输入验证与输出编码。可启用CSP降低XSS风险。
4. **集成自动化测试**：在CI/CD中加入SAST/DAST检测未转义输入与XSS。

---

*报告人：DeepDiveSecurityAuditorAgent*
*日期：2024-06-XX*