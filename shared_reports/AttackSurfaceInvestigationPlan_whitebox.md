# 攻击面调查计划 - 白盒代码审计

## 引言

本攻击面调查计划旨在指导对“mall”电商项目的白盒代码审计工作。该计划基于对《部署架构报告》、项目技术栈（Spring Boot, Spring Security, MyBatis, Elasticsearch, RabbitMQ, Redis, MongoDB, Nginx, Docker）以及核心业务模块（mall-admin, mall-portal, mall-search）的分析。鉴于多个服务直接暴露端口，且涉及用户交互、敏感数据处理及复杂的业务逻辑，代码层面的安全审查至关重要。

审计策略将优先聚焦于**认证授权、输入验证、敏感数据处理**等高风险模块，并逐步扩展至其他功能点和安全配置。

## 白盒代码审计详细检查项

以下是为后续代码审计员提供的具体检查任务列表：

- [x] CODE-REVIEW-ITEM-001: mall-admin 用户认证模块代码审计

    *   **目标代码/配置区域**:
        *   `com.example.mall.admin.service.impl.UmsAdminServiceImpl.java` (特别是 `login` 和 `register` 方法)
        *   `com.example.mall.admin.controller.UmsAdminController.java` (处理登录、注册请求的方法)
        *   相关的Spring Security配置类 (如 `SecurityConfig.java` 或类似命名的文件)
        *   `pom.xml` 中与认证、JWT相关的库版本。
    *   **要审计的潜在风险/漏洞类型**:
        1.  SQL注入 (如果登录查询构建不当)。
        2.  弱密码策略或密码明文/弱加密存储。
        3.  认证逻辑绕过 (例如，空用户名/密码处理不当)。
        4.  不安全的会话管理或JWT令牌处理缺陷。
        5.  用户名枚举。
    *   **建议的白盒代码审计方法/关注点**:
        1.  仔细审查 `UmsAdminServiceImpl.login` 方法中构造和执行数据库查询的逻辑，确保使用参数化查询。
        2.  检查密码存储是否使用了强哈希算法（如bcrypt, scrypt, Argon2）并加盐。
        3.  分析登录接口对异常输入（空值、特殊字符）的处理逻辑。
        4.  审查JWT令牌的生成、签名、验证过程，特别是密钥管理。
        5.  检查登录失败时返回的错误信息是否统一，以防止用户名枚举。
    *   **部署上下文与优先级**: mall-admin 是后台管理系统，直接暴露。认证模块是核心安全屏障。优先级：极高。

- [ ] CODE-REVIEW-ITEM-002: mall-portal 用户认证与授权模块代码审计

    *   **目标代码/配置区域**:
        *   `com.example.mall.portal.member.controller.UmsMemberController.java` (会员注册、登录、信息修改)
        *   `com.example.mall.portal.member.service.UmsMemberService.java`
        *   Spring Security 相关配置 (如 `com.example.mall.portal.config.SecurityConfig.java`)
        *   JWT工具类和拦截器/过滤器。
    *   **要审计的潜在风险/漏洞类型**:
        1.  不安全的直接对象引用 (IDOR) - 针对会员信息修改。
        2.  未授权访问 / 越权（如普通用户访问管理员功能）。
        3.  验证码逻辑缺陷（如果存在）。
        4.  JWT令牌伪造、重放或信息泄露。
    *   **建议的白盒代码审计方法/关注点**:
        1.  确认所有涉及敏感操作的接口都进行了充分的权限检查，特别是对当前用户ID的验证。
        2.  审查Spring Security配置中的权限表达式 (`@PreAuthorize`, `hasRole`, `permitAll`, `denyAll` 等) 是否配置正确且未遗漏。
        3.  检查OAuth2或JWT认证流程中的token验证、刷新机制，密钥是否安全管理。
    *   **部署上下文与优先级**: mall-portal 对公众开放，用户基数大。认证与授权失败可能导致账户劫持、数据泄露等严重问题。优先级：极高。

- [ ] CODE-REVIEW-ITEM-003: mall-portal 商品搜索功能代码审计

    *   **目标代码/配置区域**:
        *   `com.example.mall.portal.repository.EsProductRepository.java` (如果直接操作ES)
        *   `com.example.mall.portal.controller.PortalProductController.java` (特别是处理搜索参数的方法)
        *   搜索服务相关的 Elasticsearch 查询构建逻辑 (如果存在于此模块或相关模块)。
        *   `mall-search` 服务 (`com.example.mall.search` 包下所有与搜索查询相关的代码)。
    *   **要审计的潜在风险/漏洞类型**:
        1.  NoSQL注入 (特别是 Elasticsearch 查询注入)。
        2.  不当的搜索结果过滤导致信息泄露。
        3.  拒绝服务 (通过构造恶意搜索请求)。
        4.  敏感数据在搜索结果中的意外暴露。
    *   **建议的白盒代码审计方法/关注点**:
        1.  检查所有用户控制的输入如何被整合到 Elasticsearch 查询中，确保使用了安全的查询构建方式（如参数化查询或Elasticsearch客户端API）。
        2.  确认搜索结果是否根据用户权限和业务规则进行了恰当的过滤。
        3.  分析查询构建逻辑，是否存在允许用户注入复杂查询操作符的可能。
        4.  审查搜索接口返回数据结构，确保不返回敏感或不应公开的信息。
    *   **部署上下文与优先级**: mall-portal 是面向用户的门户，搜索是常用功能。`mall-search`服务直接暴露端口。优先级：高。

- [ ] CODE-REVIEW-ITEM-004: 通用输入验证与XSS防护审计

    *   **目标代码/配置区域**:
        *   所有接收用户输入的Controller层方法 (`@RequestBody`, `@RequestParam`, `@PathVariable` 等)。
        *   表单验证注解 (`@Valid`, `@NotNull`, `@Size` 等) 的使用。
        *   数据返回给前端时的序列化过程（如 JSON 序列化）。
        *   任何前端富文本编辑器内容的后端处理。
    *   **要审计的潜在风险/漏洞类型**:
        1.  跨站脚本 (XSS) 漏洞。
        2.  SQL注入、命令注入、LDAP注入等。
        3.  不安全的直接对象引用 (IDOR)。
        4.  参数篡改。
    *   **建议的白盒代码审计方法/关注点**:
        1.  审查所有用户输入参数的处理，确认是否进行了严格的白名单验证或编码输出。
        2.  特别关注反射型XSS，即输入在响应中原样返回而未进行编码。
        3.  关注存储型XSS，即输入被存储（如评论、商品描述）后在其他页面显示时未编码。
        4.  检查所有的数据库操作，确保使用了预编译语句或ORM框架的参数化功能。
    *   **部署上下文与优先级**: 影响整个应用安全，广泛存在。优先级：极高。

- [ ] CODE-REVIEW-ITEM-005: 敏感数据存储与传输安全审计

    *   **目标代码/配置区域**:
        *   所有数据库操作相关代码（MyBatis XML Mapper, DAO层）。
        *   涉及密码、银行卡号、身份证号等敏感信息的字段定义和操作。
        *   配置文件 (`application-prod.yml`) 中涉及数据库连接、第三方API密钥、JWT签名密钥等。
        *   任何涉及到文件存储（如MinIO）的代码。
    *   **要审计的潜在风险/漏洞类型**:
        1.  敏感信息明文存储或弱加密存储。
        2.  硬编码敏感信息。
        3.  密钥管理不当。
        4.  数据泄露。
    *   **建议的白盒代码审计方法/关注点**:
        1.  检查数据库中敏感字段的存储方式，如密码是否使用了加盐哈希，其他敏感信息是否加密或脱敏。
        2.  审查配置文件的敏感信息处理，确保没有硬编码的凭证。
        3.  确认加密算法的健壮性和密钥存储的安全性。
        4.  审查文件存储服务（MinIO）的权限配置和访问控制。
    *   **部署上下文与优先级**: 关系到用户隐私和业务核心资产。优先级：极高。

- [ ] CODE-REVIEW-ITEM-006: 业务逻辑漏洞审计 (订单、购物车、优惠券)

    *   **目标代码/配置区域**:
        *   `mall-portal` 模块中的订单创建、支付、购物车管理、优惠券使用相关业务逻辑代码。
        *   `om.example.mall.portal.order.controller.OmsPortalOrderController.java`
        *   `com.example.mall.portal.order.service.OmsPortalOrderService.java`
        *   `com.example.mall.portal.cart.controller.OmsCartItemController.java`
        *   `com.example.mall.portal.cart.service.OmsCartItemService.java`
    *   **要审计的潜在风险/漏洞类型**:
        1.  价格篡改、库存绕过。
        2.  逻辑越权（例如，修改他人订单）。
        3.  条件竞争漏洞 (Race Condition)。
        4.  优惠券重复使用或非法生成。
    *   **建议的白盒代码审计方法/关注点**:
        1.  跟踪从前端请求到后端业务逻辑的所有处理步骤，确保所有金额、数量、状态等关键业务参数在服务器端严格验证。
        2.  检查所有涉及用户ID或订单ID的业务逻辑，确保用户只能操作自己的资源。
        3.  分析并发处理代码块，查找是否存在未正确加锁导致条件竞争。
        4.  审查优惠券校验和使用逻辑，确保不可被绕过或重复利用。
    *   **部署上下文与优先级**: 核心业务流程，直接影响营收和数据完整性。优先级：极高。

- [ ] CODE-REVIEW-ITEM-007: 文件上传/下载安全性审计

    *   **目标代码/配置区域**:
        *   `mall-admin` 或 `mall-portal` 中所有涉及文件上传（如头像、商品图片）的功能代码。
        *   文件存储路径配置。
        *   文件下载接口。
    *   **要审计的潜在风险/漏洞类型**:
        1.  任意文件上传漏洞 (WebShell)。
        2.  目录遍历漏洞。
        3.  文件包含漏洞。
        4.  不安全的文件类型、大小、内容验证。
    *   **建议的白盒代码审计方法/关注点**:
        1.  检查文件上传时是否对文件名、文件类型（MIME-Type和文件头）、文件大小进行了严格的白名单验证。
        2.  确认上传文件是否存储在Web可访问目录之外，并进行了重命名，避免直接暴露原始文件名或执行恶意代码。
        3.  审查文件下载功能，确保使用了安全的路径验证，防止目录遍历。
    *   **部署上下文与优先级**: 如果存在，可能导致Webshell或敏感信息泄露。优先级：高。

- [ ] CODE-REVIEW-ITEM-008: API安全审计 (OAuth2 / JWT / RBAC)

    *   **目标代码/配置区域**:
        *   所有 `@RestController` 类中的API端点。
        *   `Spring Security` 的配置类 (`WebSecurityConfig.java` 等)。
        *   JWT令牌的生成、解析、验证和刷新逻辑。
        *   所有涉及 `@PreAuthorize` 或基于角色的访问控制代码。
    *   **要审计的潜在风险/漏洞类型**:
        1.  认证/授权机制缺陷。
        2.  APIKey硬编码或泄露。
        3.  不安全的JWT令牌（弱密钥、未校验签名、敏感信息泄露）。
        4.  不完善的CORS配置。
    *   **建议的白盒代码审计方法/关注点**:
        1.  确认每个API端点都有明确的认证和授权策略。
        2.  检查敏感API（如管理API）是否限制了访问权限和IP。
        3.  对JWT令牌生成和验证的代码进行深入分析，确保密钥强度、过期处理、签名校验等都符合最佳实践。
        4.  检查CORS配置是否过于宽松，允许任意域访问。
    *   **部署上下文与优先级**: 直接暴露给前端或第三方服务，是主要的攻击入口。优先级：极高。

- [ ] CODE-REVIEW-ITEM-009: 第三方依赖安全审计

    *   **目标代码/配置区域**:
        *   `pom.xml` 文件中所有依赖项的定义。
        *   `spring-boot-dependencies` 版本。
        *   第三方库的使用方式（如Jackson, Fastjson等）。
    *   **要审计的潜在风险/漏洞类型**:
        1.  存在已知漏洞的第三方库（CVE）。
        2.  不安全的序列化/反序列化漏洞。
        3.  组件配置错误。
    *   **建议的白盒代码审计方法/关注点**:
        1.  列出所有直接和间接依赖，对照NVD或其他漏洞库，检查是否存在已知CVE的组件。
        2.  关注常用的序列化库（如Jackson），检查其使用方式是否存在安全漏洞。
        3.  建议使用Dependency-Check等工具辅助扫描。
    *   **部署上下文与优先级**: 影响整个应用，常常被忽视。优先级：高。

- [ ] CODE-REVIEW-ITEM-010: 日志记录与错误处理审计

    *   **目标代码/配置区域**:
        *   所有 `try-catch` 块中的错误处理逻辑。
        *   日志框架（如Logback）的配置。
        *   异常处理的全局配置 (`@ControllerAdvice` 或 `HandlerExceptionResolver`)。
    *   **要审计的潜在风险/漏洞类型**:
        1.  敏感信息泄露（如堆栈跟踪、数据库连接字符串）。
        2.  日志伪造。
        3.  未捕获的异常导致应用崩溃或信息泄露。
    *   **建议的白盒代码审计方法/关注点**:
        1.  检查错误页面和异常处理机制，确保不向用户返回详细的错误信息（如堆栈跟踪）。
        2.  审查日志记录，确保不记录敏感信息（如密码、会话ID等）。
        3.  确认所有关键操作都有充分的日志记录，以便追溯。
    *   **部署上下文与优先级**: 帮助攻击者了解系统内部，可利用进行目标定位。优先级：中。

- [ ] CODE-REVIEW-ITEM-011: Dockerfile与Docker Compose安全配置审计

    *   **目标代码/配置区域**:
        *   `/data/mall_code/document/sh/Dockerfile`
        *   `/data/mall_code/document/docker/docker-compose-app.yml`
        *   `/data/mall_code/document/docker/docker-compose-env.yml`
    *   **要审计的潜在风险/漏洞类型**:
        1.  不安全的基准镜像。
        2.  不必要暴露端口。
        3.  敏感信息直接写入镜像或环境变量。
        4.  容器以root用户运行。
        5.  缺少资源限制。
    *   **建议的白盒代码审计方法/关注点**:
        1.  检查Dockerfile，确保使用了官方或受信任的基准镜像。
        2.  确认Dockerfile中没有安装不必要的包，且最终镜像尽可能小。
        3.  审查Docker Compose文件中是否有不必要的端口映射，特别是数据库等后端服务。
        4.  检查是否限制了容器的CPU、内存等资源使用。
        5.  确保容器以非root用户运行。
    *   **部署上下文与优先级**: 影响整个部署环境的安全性。优先级：高。

- [ ] CODE-REVIEW-ITEM-012: Nginx配置安全审计

    *   **目标代码/配置区域**:
        *   `/data/mall_code/document/docker/nginx.conf`
    *   **要审计的潜在风险/漏洞类型**:
        1.  未配置或配置不当的代理规则，导致后端直连。
        2.  缺少必要的安全头部（X-Frame-Options, X-Content-Type-Options, Strict-Transport-Security）。
        3.  目录遍历或文件泄露。
        4.  Webdav, autoindex 等不安全模块开启。
    *   **建议的白盒代码审计方法/关注点**:
        1.  如果Nginx作为反向代理，检查 `proxy_pass` 配置是否正确，确保没有配置错误导致敏感路径暴露。
        2.  检查是否添加了所有推荐的安全HTTP响应头。
        3.  确认没有开放不必要的服务或目录列表。
    *   **部署上下文与优先级**: 作为潜在的外部入口点，配置安全至关重要。优先级：高。

- [ ] CODE-REVIEW-ITEM-013: 跨服务通信安全审计 (RabbitMQ)

    *   **目标代码/配置区域**:
        *   `mall-portal` 或其他服务中与 `RabbitMQ` 相关的生产者/消费者代码。
        *   `application.yml` 中RabbitMQ连接配置。
    *   **要审计的潜在风险/漏洞类型**:
        1.  认证信息硬编码或弱凭证。
        2.  消息内容未加密或未签名。
        3.  不安全的消费者处理（如反序列化）。
    *   **建议的白盒代码审计方法/关注点**:
        1.  检查RabbitMQ连接凭证的获取方式和安全性。
        2.  如果传输敏感数据，确认消息是否加密或签名。
        3.  审计消息消费者代码，防止潜在的反序列化漏洞。
    *   **部署上下文与优先级**: 内部通信通道，重要性中。优先级：中。

- [ ] CODE-REVIEW-ITEM-014: Redis缓存安全审计

    *   **目标代码/配置区域**:
        *   `mall-portal` 或其他服务中与 `Redis` 相关的缓存操作代码。
        *   `application.yml` 中Redis连接配置。
    *   **要审计的潜在风险/漏洞类型**:
        1.  认证信息硬编码或弱凭证。
        2.  敏感数据明文缓存。
        3.  Redis未授权访问（如果直接暴露）。
    *   **建议的白盒代码审计方法/关注点**:
        1.  检查Redis连接凭证的获取和安全性。
        2.  审查缓存中是否存储了敏感数据，如果是，是否进行了加密或脱敏。
        3.  确认Redis服务是否只允许内部访问。
    *   **部署上下文与优先级**: 如果利用不当，可能导致敏感信息泄露。优先级：中。

- [ ] CODE-REVIEW-ITEM-015: 数据库交互安全审计 (MyBatis / JDBC)

    *   **目标代码/配置区域**:
        *   所有Spring Boot Data JPA Repository或MyBatis Mapper接口和XML文件。
        *   所有涉及手动构建SQL查询的代码。
    *   **要审计的潜在风险/漏洞类型**:
        1.  SQL注入。
        2.  不安全的数据源配置。
        3.  宽泛的数据库权限。
    *   **建议的白盒代码审计方法/关注点**:
        1.  检查所有MyBatis XML中SQL语句和Java代码中JDBC操作，确保参数化查询的使用，避免字符串拼接。
        2.  确认ORM框架的配置和使用是否安全。
        3.  审查数据源配置，确保数据库连接URL和凭证安全。
    *   **部署上下文与优先级**: 应用程序核心数据，任何漏洞都可能导致灾难性后果。优先级：极高。