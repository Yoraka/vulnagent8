# 攻击面调查计划

**项目名称**: mall 电商系统
**审计类型**: 白盒代码审计
**制定依据**: `DeploymentArchitectureReport.md`、`pom.xml`、`application.yml` 文件分析。
**概述**:
本计划旨在指导对 `mall` 电商系统的白盒代码审计工作，重点关注可能因直接暴露的API接口和内部业务逻辑漏洞而引发的安全风险。审计将优先处理直接面向公网的服务模块 (`mall-admin`, `mall-portal`, `mall-search`)，并深入检查其认证授权、输入验证、文件处理、敏感信息管理和依赖库安全。

---

### **详细检查项**

#### **1. 认证与授权模块代码审计 (Authentication & Authorization)**

-   [ ] CODE-REVIEW-ITEM-001: 用户认证模块代码审计 (`mall-admin`, `mall-portal`)
    *   **目标代码/配置区域**:
        *   `com.macro.mall.admin.service.impl.UmsAdminServiceImpl.java` (特别是 `login`, `register` 方法)
        *   `com.macro.mall.admin.controller.UmsAdminController.java` (处理登录、注册请求的方法)
        *   `com.macro.mall.portal.service.impl.UmsMemberServiceImpl.java` (`login`, `register` 方法)
        *   `com.macro.mall.portal.controller.UmsMemberController.java` (处理登录、注册请求的方法)
        *   `mall-security` 模块中的所有认证、授权相关类及配置 (如 `com.macro.mall.security.config.SecurityConfig.java` 或类似命名的文件)。
        *   `application.yml` 中 JWT 密钥 (`jwt.secret`) 和过期时间 (`jwt.expiration`) 配置。
    *   **要审计的潜在风险/漏洞类型**:
        1.  SQL注入 (如果登录查询构建不当)。
        2.  弱密码策略、密码明文存储或弱加密存储。
        3.  认证逻辑绕过 (例如，空用户名/密码处理不当, 强制浏览)。
        4.  不安全的会话管理或JWT令牌处理缺陷 (签名验证、过期校验、算法、密钥管理)。
        5.  用户名枚举。
        6.  重放攻击 (针对JWT)。
    *   **建议的白盒代码审计方法/关注点**:
        1.  审查所有用户认证相关的数据库查询是否使用了参数化查询或安全的ORM方法，避免字符串拼接构造SQL。
        2.  检查密码存储是否使用了强哈希算法（如 bcrypt, scrypt, Argon2）并加盐，验证加盐值是否唯一且不可预测。
        3.  分析登录接口对异常输入（空值、特殊字符）的处理逻辑，确保不会导致安全漏洞。
        4.  审查JWT令牌的生成、签名、验证过程，特别是硬编码的 `jwt.secret` (例如 `mall-admin-secret`, `mall-portal-secret`) 是否在生产环境中被随机生成并安全管理，以及算法选择是否安全（应避免 NONE 算法）。
        5.  检查登录失败时返回的错误信息是否统一，以防止用户名枚举。
        6.  检查会话管理机制是否安全（例如，JWT 撤销、黑名单机制）。
    *   **部署上下文与优先级**: `mall-admin` 和 `mall-portal` 是直接暴露服务，认证模块是核心安全屏障。优先级：极高。

-   [ ] CODE-REVIEW-ITEM-002: 访问控制与权限管理代码审计 (`mall-admin`, `mall-portal`)
    *   **目标代码/配置区域**:
        *   所有 Controller 层中的 `checkPermission` (`@PreAuthorize`) 或自定义权限注解的实现。
        *   `mall-security` 模块中权限拦截器、过滤器或鉴权点。
        *   涉及用户角色和权限的 Service 层逻辑。
        *   `UmsAdminService.java` 和 `UmsMemberService.java` 中用户权限相关的查询。
    *   **要审计的潜在风险/漏洞类型**:
        1.  不安全的直接对象引用 (IDOR)。
        2.  功能级访问控制缺陷 (BFLA - Broken Function Level Authorization)。
        3.  业务逻辑缺陷导致的权限绕过。
        4.  水平权限绕过和垂直权限提升。
    *   **建议的白盒代码审计方法/关注点**:
        1.  追踪请求参数中所有用于标识资源ID（如订单ID, 用户ID）的字段，检查业务逻辑层是否对这些ID执行了严格的权限校验，确保当前用户有权访问。
        2.  审查所有敏感API接口，确保其在方法级别或类级别应用了正确的权限控制注解或逻辑。
        3.  验证不同角色（例如，普通会员 vs 管理员）对相同API的访问权限，确保低权限用户无法访问高权限功能。
        4.  检查是否存在硬编码的角色或权限判断，导致难以管理和审计。
    *   **部署上下文与优先级**: 直接暴露服务，核心业务逻辑，影响面广。优先级：极高。

#### **2. 输入验证与数据处理代码审计 (Input Validation & Data Processing)**

-   [ ] CODE-REVIEW-ITEM-003: SQL注入审计
    *   **目标代码/配置区域**:
        *   所有 `DAO/*.xml` (MyBatis Mapper XML 文件) 中的 SQL 语句。
        *   所有 `com.macro.mall.mbg` 模块中生成的 SQL 语句 (确保未手动修改引入漏洞)。
        *   所有 Service 层中涉及数据库查询和更新的方法。
        *   尤其关注动态 SQL 拼接的场景，以及使用 `${}` 而非 `#{}` 的地方。
    *   **要审计的潜在风险/漏洞类型**: SQL注入。
    *   **建议的白盒代码审计方法/关注点**:
        1.  全面审查 MyBatis Mapper XML 文件，确保所有用户可控输入都通过 `#{}` 进行参数绑定，而不是 `${}`。
        2.  检查任何手动构建 SQL 语句的场景，确保对所有外部输入进行了严格的参数化处理。
        3.  核查 `Druid` 连接池的配置，确认是否开启了 SQL 注入防护、监控等增强功能。
    *   **部署上下文与优先级**: 所有服务都与数据库交互，SQL注入是高风险漏洞。优先级：极高。

-   [ ] CODE-REVIEW-ITEM-004: 跨站脚本 (XSS) 审计
    *   **目标代码/配置区域**:
        *   所有返回 HTML/JSON 数据的 Controller 方法。
        *   所有直接将用户输入渲染到页面的视图层代码 (如果存在)。
        *   涉及用户评论、商品描述等富文本输入的处理逻辑。
    *   **要审计的潜在风险/漏洞类型**: 存储型XSS、反射型XSS。
    *   **建议的白盒代码审计方法/关注点**:
        1.  追踪所有用户可控输入从 Controller 层到最终的输出点。
        2.  验证所有输出到响应中的用户输入是否进行了适当的HTML编码或转义。
        3.  特别关注富文本编辑器内容的存储和展示，确保采用了安全的过滤策略（例如，白名单过滤）。
    *   **部署上下文与优先级**: `mall-portal` 直接面向用户，存在XSS风险。优先级：中。

-   [ ] CODE-REVIEW-ITEM-005: 不安全的对象反序列化审计
    *   **目标代码/配置区域**:
        *   检查所有使用到序列化/反序列化（如 `java.io.ObjectInputStream`）或第三方反序列化库（如 Jackson, fastjson, XStream 等）的代码。
        *   检查消息队列 (`RabbitMQ`) 消息处理、Redis 缓存数据、JWT 数据中是否包含可控的序列化对象。
    *   **要审计的潜在风险/漏洞类型**: 不安全的反序列化。
    *   **建议的白盒代码审计方法/关注点**:
        1.  识别应用中所有发生序列化和反序列化的位置。
        2.  如果存在反序列化操作，检查是否对反序列化的类进行了白名单限制或类型检查，以防止任意类的加载。
        3.  评估第三方库或框架（如 Spring AMQP, Spring Redis）中默认的反序列化机制，确认其安全性。
    *   **部署上下文与优先级**: `mall-portal` 使用 RabbitMQ、Redis，潜在存在反序列化风险。优先级：中。

-   [ ] CODE-REVIEW-ITEM-006: 路径遍历与文件操作审计 (`mall-admin`)
    *   **目标代码/配置区域**:
        *   `mall-admin` 模块中所有处理文件上传（MinIO/OSS）和下载的API接口及相关 Service 层方法。
        *   `application.yml` 中关于文件上传的配置 (`minio/aliyun.oss` 配置)。
    *   **要审计的潜在风险/漏洞类型**: 路径遍历、任意文件上传、文件类型绕过。
    *   **建议的白盒代码审计方法/关注点**:
        1.  检查文件上传的路径是否可控，是否采用了沙箱目录或随机文件名，防止目录穿越。
        2.  严格审查文件上传类型（MIME Type）和文件扩展名的校验逻辑，防止上传恶意文件（如 WebShell）。
        3.  验证文件大小限制是否有效，防止拒绝服务攻击。
        4.  检查回调地址 (`aliyun.oss.callback`) 的安全性。
    *   **部署上下文与优先级**: `mall-admin` 存在文件上传功能，直接暴露。优先级：高。

-   [ ] CODE-REVIEW-ITEM-007: 服务器端请求伪造 (SSRF) 审计
    *   **目标代码/配置区域**:
        *   所有应用程序中涉及发送外部请求（如 HTTP Client, URL.openConnection, RestTemplate, Feign Client 等）的代码。
        *   尤其是那些请求 URL 部分可由用户控制的场景。
    *   **要审计的潜在风险/漏洞类型**: SSRF。
    *   **建议的白盒代码审计方法/关注点**:
        1.  识别所有出站网络请求的URI/URL来源，检查其是否完全由后端硬编码或经过严格校验。
        2.  如果URL部分或全部来自用户输入，确保对协议、主机、端口和路径进行了严格的白名单或黑名单过滤。
        3.  特别关注图片抓取、RSS订阅、文件下载等功能，这些功能通常是SSRF的Pivoting点。
    *   **部署上下文与优先级**: 存在外部API调用（如 OSS 回调），潜在风险。优先级：中。

#### **3. 安全配置与敏感信息管理审计**

-   [ ] CODE-REVIEW-ITEM-008: 硬编码敏感信息审计
    *   **目标代码/配置区域**:
        *   所有 `application.yml` 和 `application-*.properties` 文件。
        *   所有 Java 代码文件中。
        *   `docker-compose-env.yml` 和 `docker-compose-app.yml` 中的密码、密钥、API Keys。
    *   **要审计的潜在风险/漏洞类型**: 敏感信息硬编码、凭据泄露。
    *   **建议的白盒代码审计方法/关注点**:
        1.  审查所有配置文件和代码，查找数据库连接字符串、云服务凭据 (如 `aliyun.oss.accessKeyId`, `accessKeySecret`)、API 密钥、JWT 密钥 (`jwt.secret`), 支付密码、Redis 密码、消息队列凭据等敏感信息是否直接硬编码。
        2.  建议使用环境变量、配置中心或加密配置来管理敏感信息。
    *   **部署上下文与优先级**: 系统暴露，核心凭据泄露将导致严重后果。优先级：极高。

-   [ ] CODE-REVIEW-ITEM-009: 安全框架配置审计 (Spring Security, Spring Boot Actuator, Druid)
    *   **目标代码/配置区域**:
        *   `mall-security` 模块中的所有 Spring Security 配置类 (`WebSecurityConfig.java` 或类似)。
        *   每个模块的 `application.yml` 中 `secure.ignored.urls` 配置。
        *   `pom.xml` 中 `spring-boot-starter-actuator` 依赖的使用及其配置。
        *   `application.yml` 中 `spring.servlet.multipart.enabled` and `spring.servlet.multipart.max-file-size`。
        *   `application.yml` 中 `druid` 监控页面 (`/druid/**`) 配置。
    *   **要审计的潜在风险/漏洞类型**: 安全配置错误、敏感接口暴露、未授权访问。
    *   **建议的白盒代码审计方法/关注点**:
        1.  审查 Spring Security 配置，确保正确的认证和授权机制已启用，且最佳实践被遵循（如 CSRF 防护、HTTPS 配置、HSTS）。
        2.  检查 `secure.ignored.urls` 白名单是否过于宽泛，导致敏感路径（如 `/swagger-ui/`, `/v2/api-docs`, `/actuator/**`, `/druid/**`）在未经认证的情况下可直接访问。
        3.  确认 Spring Boot Actuator 端点是否配置正确，特别是生产环境中是否禁用了所有敏感端点或仅对授权用户开放。
        4.  评估 Druid 监控页面 `/druid/**` 是否有强认证保护，防止信息泄露或未授权操作。
        5.  检查文件上传配置（如最大文件大小）是否合理，以防止拒绝服务攻击。
    *   **部署上下文与优先级**: 直接暴露服务，配置错误可能导致大范围漏洞。优先级：极高。

#### **4. 日志记录与监控审计**

-   [ ] CODE-REVIEW-ITEM-010: 敏感数据日志记录审计
    *   **目标代码/配置区域**:
        *   所有 Controller、Service、DAO 层中涉及日志记录的代码。
        *   `logback-spring.xml` 或其他日志配置文件。
    *   **要审计的潜在风险/漏洞类型**: 敏感数据泄露 (如密码、Token、个人身份信息)。
    *   **建议的白盒代码审计方法/关注点**:
        1.  审查所有日志记录语句，确保不记录敏感用户数据（如明文密码、银行卡号、身份证号、会话Token等）。
        2.  检查异常日志中是否包含过多调试信息，例如堆栈跟踪中暴露的系统路径、数据库连接信息。
        3.  评估 Logstash 配置，确保日志传输和存储的安全性。
    *   **部署上下文与优先级**: 内部和外部服务日志都可能被收集。优先级：中。

#### **5. 第三方依赖与中间件安全审计**

-   [ ] CODE-REVIEW-ITEM-011: 第三方库及依赖审计
    *   **目标代码/配置区域**:
        *   `pom.xml` 文件中所有 `<dependency>` 和 `<dependencyManagement>` 部分。
        *   Docker 镜像 `openjdk:8`。
    *   **要审计的潜在风险/漏洞类型**: 已知漏洞 (CVEs) 的第三方依赖。
    *   **建议的白盒代码审计方法/关注点**:
        1.  使用自动化工具（如 OWASP Dependency-Check）对 `pom.xml` 中列出的所有依赖进行扫描，识别已知漏洞。
        2.  特别关注 `jjwt`, `druid`, `aliyun-oss`, `minio`, `springfox-swagger` 等关键库的版本。
        3.  检查基础镜像 `openjdk:8` 是否有已知的安全漏洞，并建议升级到更安全的版本。
    *   **部署上下文与优先级**: 所有模块都依赖这些库。优先级：高。

-   [ ] CODE-REVIEW-ITEM-012: MinIO/OSS 对象存储配置与使用安全审计
    *   **目标代码/配置区域**:
        *   `com.macro.mall.admin.controller.MinioController.java` 和 `com.macro.mall.admin.controller.AliyunOssController.java`。
        *   相关 Service 层处理对象存储的代码。
        *   `application.yml` 中 MinIO 和 Aliyun OSS 的配置。
    *   **要审计的潜在风险/漏洞类型**: 不安全的存储配置、未授权访问对象、越权上传/下载、ACL配置错误。
    *   **建议的白盒代码审计方法/关注点**:
        1.  审查 MinIO/OSS 的配置，确保 bucket 权限配置最小化原则，避免匿名读写。
        2.  检查文件上传和下载的 API，确保所有操作都经过严格的认证和授权。
        3.  审查生成的临时签名 URL（如果有的话），确保其有效性和访问范围限制。
        4.  检查硬编码的 AccessKeyId 和 SecretKey (`test` 值) 是否在生产环境被替换。
    *   **部署上下文与优先级**: MinIO 和 OSS 都直接暴露，配置不当会导致数据泄露或篡改。优先级：高。

-   [ ] CODE-REVIEW-ITEM-013: 消息队列 (RabbitMQ) 安全审计 (`mall-portal`)
    *   **目标代码/配置区域**:
        *   `mall-portal` 中处理 RabbitMQ 消息的 Service 层代码。
        *   `application.yml` 中 RabbitMQ 相关配置。
    *   **要审计的潜在风险/漏洞类型**: 消息毒丸、未经验证的消息处理、敏感信息泄露。
    *   **建议的白盒代码审计方法/关注点**:
        1.  检查消息消费者是否对接收到的消息内容进行校验和清理，防止注入攻击。
        2.  审查消息中是否包含敏感信息，并确保传输和存储的安全性。
        3.  验证 RabbitMQ 连接凭据是否安全管理，而非硬编码或弱密码。
    *   **部署上下文与优先级**: 内部服务间通信，不当处理可能影响内部系统。优先级：中。

-   [ ] CODE-REVIEW-ITEM-014: Elasticsearch 安全审计 (`mall-search`)
    *   **目标代码/配置区域**:
        *   `mall-search` 模块中所有与 Elasticsearch 交互的代码。
        *   尤其关注搜索查询的构建逻辑。
    *   **要审计的潜在风险/漏洞类型**: NoSQL 注入、敏感数据暴露、拒绝服务。
    *   **建议的白盒代码审计方法/关注点**:
        1.  检查所有用户输入如何被拼接到 Elasticsearch 查询中，确保避免 NoSQL 注入。
        2.  验证搜索结果是否根据用户权限进行过滤。
        3.  评估 Elasticsearch 连接的认证机制。
    *   **部署上下文与优先级**: `mall-search` 直接暴露。优先级：中。

#### **6. Dockerfile 与 Docker Compose 安全审计**

-   [ ] CODE-REVIEW-ITEM-015: Docker 镜像与容器安全配置审计
    *   **目标代码/配置区域**:
        *   `/data/mall_code/document/sh/Dockerfile`
        *   `/data/mall_code/document/docker/docker-compose-app.yml`
        *   `/data/mall_code/document/docker/docker-compose-env.yml`
    *   **要审计的潜在风险/漏洞类型**: 镜像历史泄露、非最小权限运行、端口过度暴露、敏感信息挂载到容器。
    *   **建议的白盒代码审计方法/关注点**:
        1.  检查 Dockerfile 是否使用了最小化基础镜像，并避免在镜像中打包不必要的工具或敏感信息。
        2.  确认容器是否以非 root 用户运行。
        3.  审查 Docker Compose 文件中的端口映射和卷挂载，`minio` 等服务的默认凭据是否被更改。
        4.  检查生产环境中是否将敏感的数据库、Redis 等服务端口直接映射到宿主机公网IP。
    *   **部署上下文与优先级**: 影响整个应用部署环境的安全基线。优先级：高。