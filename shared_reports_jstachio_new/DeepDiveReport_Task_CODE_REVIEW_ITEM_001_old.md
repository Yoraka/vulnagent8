Deep Dive Security Audit Report for CODE-REVIEW-ITEM-001: 模板解析与编译过程中的潜在模板注入风险

1. 漏洞一：编译期代码注入 (Compile-Time Code Injection)
   - 位置：`CodeAppendable.stringLiteralConcat(String s)` (文件：`compiler/apt/src/main/java/io/jstach/apt/internal/CodeAppendable.java`)
   - 描述：该方法用于将模板中静态文本块写入生成的 Java 源代码时，直接将未经充分 Java 字符串字面量转义的文本插入到双引号字符串中，允许攻击者通过在模板静态文本中包含 `"` 或 `\` 等字符，破坏字符串字面量并注入任意 Java 代码。
   - 影响：在模板渲染时执行恶意代码；任何使用受攻击模板的 Java 应用均可受到攻击。
   - PoC 示例：模板片段
     ```mustache
     {{! 注释 }}"; System.exit(0); //{{userName}}
     ```
     将在生成的渲染器中插入 `System.exit(0);`。

2. 漏洞二：编译期路径遍历 (Compile-Time Path Traversal)
   - 位置：`TextFileObject.openInputStream(String name)` 回退文件系统加载逻辑 (文件：`compiler/apt/src/main/java/io/jstach/apt/TextFileObject.java`)
   - 描述：当资源未通过 `Filer` 加载且 `config.fallbackToFilesystem()` 默认为 `true` 时，`name` 参数未经正规化或禁止 `..` 路径段，直接与 `src/main/resources` 前缀拼接并解析到项目根目录下，导致可读取任意文件。
   - 影响：攻击者可通过在模板中使用 `{{> ../../../../etc/passwd }}` 等路径，读取本地任意文件（开发机或 CI 服务器）。

3. 改进建议：HTML 单引号转义缺失 (HTML Single-Quote Escaping)
   - 位置：`HtmlEscaper.java` (文件：`api/jstach/jstachio/src/main/java/io/jstach/jstachio/escapers/HtmlEscaper.java`)
   - 描述：该类转义 `& < > "`，但未转义单引号 `'`。在单引号包裹的属性中使用 `{{variable}}` 时，可发生 XSS。
   - 影响：攻击者可在单引号属性上下文中注入如 `x' onmouseover='alert(1)'`。
   - 建议：将 `'` 转义为 `&#39;`。

审核完成。