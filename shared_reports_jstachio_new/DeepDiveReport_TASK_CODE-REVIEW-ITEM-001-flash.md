# 深度安全审计报告: CODE-REVIEW-ITEM-001

**审计目标**: 模板解析与编译过程中的潜在模板注入风险 (主动缺陷)
**审计范围**: JStachio 编译时模板引擎 (compiler/apt 模块) 及运行时 HTML 转义组件。

---

## 一、发现的安全缺陷

### 1. 编译时 Java 代码注入：静态文本未转义
- **位置**: io.jstach.apt.internal.CodeAppendable.stringLiteralConcat
- **描述**: 方法将模板中的静态文本转换为 Java 字符串字面量，但未对文本中的双引号 (`"`) 和反斜杠 (`\`) 进行 Java 转义。
- **影响**: 生成的 Java 渲染类将包含非法字符串字面量，导致编译失败；在极端情况下，攻击者可通过闭合字符串并注入合法 Java 代码，实现编译时任意代码执行。
- **PoC**:
  ```mustache
  Hello: "; System.out.println("VULNERABLE!"); String x = "
  ```
- **修复建议**: 在 `stringLiteralConcat` 方法中，对 `line` 调用 `EscapeUtils.escapeJava(line)`，确保所有特殊字符被正确转义。

### 2. 编译时 Java 代码注入：`path` 参数未转义
- **位置**: io.jstach.apt.internal.context.RenderingCodeGenerator.renderFormatCallJStache
- **描述**: 在生成 Java 渲染代码时，Section/Partial 名称 `path` 无转义地被拼接到字符串字面量中。由于 `IdentifierMustacheTokenizerState` 允许标识符含 `"`、`\`，攻击者可构造恶意名称，实现编译时 Java 代码注入。
- **影响**: 与缺陷1类似，导致渲染类编译失败，或通过精心构造实现 RCE。
- **PoC**:
  ```java
  @JStachePartial(name="evil", path="x\"; System.out.println(\"INJECTED!\"); /* \" */")
  ```
- **修复建议**: 在 `renderFormatCallJStache` 中，对 `path` 参数调用 `EscapeUtils.escapeJava(path)`。

### 3. 运行时 XSS：未转义单引号
- **位置**: io.jstach.jstachio.escapers.HtmlEscaper
- **描述**: `HtmlEscaper` 未对单引号 (`'`) 转义。
- **影响**: 在 HTML 属性中使用单引号界定时，攻击者可注入单引号闭合属性并加入恶意 JS，导致 XSS。
- **PoC**:
  ```html
  <input type='text' value='{{userInput}}'>
  ```
  `userInput = '\' ONERROR="alert(1)" X='`
- **修复建议**: 在 `HtmlEscaper.append` 中新增对单引号的转义，例如 `a.append("&#x27;");`。

### 4. 编译时任意文件读取
- **位置**: io.jstach.apt.TextFileObject.openInputStream
- **描述**: 在 `fallbackToFilesystem()` 为 true 时，从文件系统根据相对路径读取模板，无路径规范化及 `..` 检查，导致路径逃逸。
- **影响**: 攻击者可通过 `JStachePartial` 等注解的 `path` 属性使用 `../` 序列，读取编译服务器上任意可访问文件（如 `/etc/passwd`）。
- **PoC**:
  ```java
  @JStachePartials({
    @JStachePartial(name="secret", path="../../../../../../etc/passwd")
  })
  ```
- **修复建议**: 在回退文件系统读取前，使用 `fullPath = fullPath.normalize()` 并检查 `fullPath.startsWith(projectPath.normalize())`，拒绝越界路径。

---

## 二、其他审计项

1. **Mustache 词法分析器**: 状态机设计健壮，错误处理完善，无可利用缺陷。
2. **编译时转义工具 (JavaUnicodeEscaper, EscapeUtils)**: 提供了正确的 Java 转义功能，关键在于保证调用方正确使用。
3. **运行时模板查找 (JStachioTemplateFinder)**: 仅查找已编译的 Java 类，不涉及文件系统路径，无直接风险。
4. **字符集处理**: 使用 UTF-8，字符集一致性良好，无安全风险。
5. **SPI 扩展点**: 使用 Java 标准 `ServiceLoader`，风险在 Classpath 管理，需要确保部署环境安全。
6. **JMustache 后备渲染**: 若启用，将引入 JMustache 的运行时模板加载风险，需另行审计 JMustache。

---

## 三、总结与建议

JStachio 在编译时和运行时的核心安全机制大体合理，但在以下关键环节存在安全缺陷：

1. **静态文本与 `path` 参数未转义，导致编译时 Java 代码注入**
2. **`HtmlEscaper` 未转义单引号，导致运行时 XSS**
3. **回退文件系统读取无路径规范化，导致编译时任意文件读取**

建议：
- 修复上述缺陷，增加必要的 Java 和 HTML 转义。
- 强化文件路径校验，防止越界访问。
- 在生产环境禁用 JMustache 后备渲染，或对 JMustache 模板加载机制进行严格审计。

---

*报告完毕*