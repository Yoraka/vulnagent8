# Mall电商系统攻击面调查计划 (白盒代码审计)

## 引言与概述

### 计划制定基础
本攻击面调查计划基于以下核心信息制定：
- **部署架构报告关键发现**: Mall电商系统采用微服务架构，包含3个核心业务服务(mall-admin、mall-portal、mall-search)通过Docker直接端口映射对外提供服务，缺乏网关集中安全控制
- **项目技术栈**: Spring Boot 2.7.5 + MyBatis + Spring Security + JWT + Redis + MySQL + Elasticsearch + MongoDB + RabbitMQ + MinIO
- **用户关注点**: 需要对当前目录中的Mall电商系统进行全面的安全审计，重点关注代码层面的潜在安全漏洞

### 审计策略概述
基于系统的微服务架构和直接暴露的特性，本次代码审计将采用**分层分模块**的策略：
1. **优先级1**: 认证授权模块代码审计 - 系统安全的核心防线
2. **优先级2**: 用户输入处理代码审计 - Controller层和数据验证逻辑
3. **优先级3**: 数据访问层代码审计 - 数据持久化和查询安全
4. **优先级4**: 业务逻辑模块代码审计 - 核心业务流程安全
5. **优先级5**: 配置和依赖安全审计 - 系统配置和第三方组件风险

## 详细检查项

### 认证授权模块代码审计 (优先级：极高)

- [ ] CODE-REVIEW-ITEM-001: JWT认证机制代码审计
    * **目标代码/配置区域**: 
        * `com.macro.mall.security.util.JwtTokenUtil.java` - JWT工具类
        * `com.macro.mall.security.component.JwtAuthenticationTokenFilter.java` - JWT过滤器
        * `mall-admin/src/main/resources/application.yml` 中的JWT配置 (secret、expiration等)
        * `com.macro.mall.admin.service.impl.UmsAdminServiceImpl.java` 中的登录方法
    * **要审计的潜在风险/漏洞类型**: 
        1. JWT密钥硬编码或弱密钥
        2. JWT令牌过期时间设置过长
        3. JWT签名算法降级攻击 (如null算法)
        4. JWT令牌缺乏有效的撤销机制
        5. JWT载荷信息泄露敏感数据
    * **建议的白盒代码审计方法/关注点**: 
        1. 检查JWT密钥是否为硬编码的弱密钥 ("mall-admin-secret")
        2. 分析JWT令牌生成和验证的完整流程，确认签名算法固定为安全算法
        3. 审查JWT令牌的载荷内容，确保不包含敏感用户信息
        4. 检查是否存在JWT令牌黑名单或撤销机制
        5. 验证JWT过期时间设置是否合理 (当前604800秒=7天)
    * **部署上下文与优先级**: mall-admin为公开暴露的后台管理系统，JWT是其主要认证方式。优先级：极高

- [ ] CODE-REVIEW-ITEM-002: Spring Security配置代码审计  
    * **目标代码/配置区域**: 
        * `com.macro.mall.security.config.*` 包下的所有Security配置类
        * `com.macro.mall.admin.config.MallSecurityConfig.java` 等安全配置类
        * `mall-admin/src/main/resources/application.yml` 中的secure.ignored.urls配置
    * **要审计的潜在风险/漏洞类型**: 
        1. 安全配置不当导致关键接口暴露
        2. 权限控制配置错误或权限提升
        3. CORS配置过于宽松
        4. CSRF防护配置不当
        5. 会话管理配置安全问题
    * **建议的白盒代码审计方法/关注点**: 
        1. 审查忽略安全检查的URL列表，确认是否合理
        2. 分析权限配置是否存在越权访问路径
        3. 检查CORS配置是否允许任意来源请求
        4. 验证关键操作是否启用了CSRF防护
        5. 确认会话固定防护和并发会话控制配置
    * **部署上下文与优先级**: Spring Security是整个系统的安全基础，配置错误影响全局。优先级：极高

- [ ] CODE-REVIEW-ITEM-003: 动态权限控制代码审计
    * **目标代码/配置区域**: 
        * `com.macro.mall.security.component.DynamicSecurityFilter.java`
        * `com.macro.mall.security.component.DynamicAccessDecisionManager.java`
        * `com.macro.mall.security.component.DynamicSecurityMetadataSource.java`
        * `com.macro.mall.security.component.DynamicSecurityService.java`
    * **要审计的潜在风险/漏洞类型**: 
        1. 动态权限判断逻辑漏洞
        2. 权限缓存机制安全问题
        3. 权限检查绕过
        4. 竞态条件导致的权限检查失效
    * **建议的白盒代码审计方法/关注点**: 
        1. 深入分析动态权限决策算法的实现逻辑
        2. 检查权限缓存的更新和失效机制
        3. 验证是否存在权限检查的时序窗口漏洞
        4. 审查异常情况下的权限处理逻辑
    * **部署上下文与优先级**: 动态权限控制是细粒度访问控制的核心。优先级：极高

### 输入验证与数据处理代码审计 (优先级：高)

- [ ] CODE-REVIEW-ITEM-004: Controller层输入验证代码审计
    * **目标代码/配置区域**: 
        * `com.macro.mall.admin.controller.*` 包下所有Controller类
        * `com.macro.mall.portal.controller.*` 包下所有Controller类  
        * `com.macro.mall.search.controller.*` 包下所有Controller类
        * 特别关注参数绑定和验证注解使用
    * **要审计的潜在风险/漏洞类型**: 
        1. SQL注入 (通过查询参数)
        2. XSS (Cross-Site Scripting)
        3. 命令注入
        4. 路径遍历
        5. 输入验证绕过
        6. 参数污染攻击
    * **建议的白盒代码审计方法/关注点**: 
        1. 检查所有用户输入参数的验证逻辑，确认是否使用了@Valid等验证注解
        2. 审查特殊字符和SQL关键字的过滤处理
        3. 分析文件上传接口的文件类型、大小、路径验证逻辑
        4. 检查动态查询构建是否存在注入风险
        5. 验证前端传入的分页参数、排序参数是否经过验证
    * **部署上下文与优先级**: 所有Controller直接暴露给外部请求，是第一道防线。优先级：高

- [ ] CODE-REVIEW-ITEM-005: 文件上传功能代码审计
    * **目标代码/配置区域**: 
        * `com.macro.mall.admin.controller.MinioController.java`
        * `com.macro.mall.admin.service.impl.UmsAdminServiceImpl.java` 中的文件处理方法
        * MinIO相关的配置和服务类
        * `application.yml` 中的servlet.multipart配置
    * **要审计的潜在风险/漏洞类型**: 
        1. 任意文件上传漏洞
        2. 文件类型验证绕过
        3. 路径遍历导致的任意文件写入
        4. 文件大小限制绕过
        5. 上传文件的恶意内容检测缺失
    * **建议的白盒代码审计方法/关注点**: 
        1. 审查文件扩展名和MIME类型验证的完整性
        2. 检查文件存储路径的构造逻辑，确认是否存在路径遍历风险
        3. 验证文件大小限制的有效性和绕过可能
        4. 分析上传文件的重命名和权限设置
        5. 检查文件内容的安全扫描机制
    * **部署上下文与优先级**: 文件上传功能直接暴露，可能成为获取系统访问权限的入口。优先级：高

- [ ] CODE-REVIEW-ITEM-006: 搜索功能代码审计
    * **目标代码/配置区域**: 
        * `com.macro.mall.search.controller.*` 包下的搜索相关Controller
        * `com.macro.mall.search.service.*` 包下的Elasticsearch查询服务
        * `com.macro.mall.portal.controller.PortalProductController.java` 中的搜索方法
    * **要审计的潜在风险/漏洞类型**: 
        1. Elasticsearch查询注入
        2. NoSQL注入
        3. 搜索结果信息泄露
        4. 拒绝服务攻击 (通过复杂查询)
        5. 搜索日志敏感信息泄露
    * **建议的白盒代码审计方法/关注点**: 
        1. 审查Elasticsearch查询构建逻辑，确认用户输入的清理和转义
        2. 检查搜索查询的复杂度限制和超时控制
        3. 验证搜索结果的权限过滤机制
        4. 分析搜索建议和自动完成功能的安全性
        5. 检查搜索日志是否记录敏感查询参数
    * **部署上下文与优先级**: 搜索功能面向用户开放，是常见的攻击入口点。优先级：高

### 数据访问层代码审计 (优先级：高)

- [ ] CODE-REVIEW-ITEM-007: MyBatis SQL映射文件代码审计
    * **目标代码/配置区域**: 
        * `resources/dao/*.xml` 下所有SQL映射文件
        * `com/macro/mall/mbg/mapper/*.xml` 下的生成映射文件
        * 动态SQL构建的相关代码
    * **要审计的潜在风险/漏洞类型**: 
        1. SQL注入(特别是动态SQL)
        2. 权限控制缺失导致的数据泄露
        3. 批量操作的安全风险
        4. 存储过程调用安全问题
    * **建议的白盒代码审计方法/关注点**: 
        1. 重点审查使用`${}`参数替换的SQL语句，确认是否存在注入风险
        2. 检查动态SQL的构建逻辑，特别是WHERE条件的拼接
        3. 验证批量操作是否有适当的权限和数量限制
        4. 审查复杂查询是否存在性能风险或信息泄露
        5. 检查数据库函数和存储过程的调用安全性
    * **部署上下文与优先级**: 数据访问层是数据安全的最后防线，任何注入都可能导致数据泄露。优先级：高

- [ ] CODE-REVIEW-ITEM-008: 数据库配置与连接安全审计
    * **目标代码/配置区域**: 
        * `application-prod.yml` 中的数据源配置
        * `pom.xml` 中的MySQL驱动版本
        * Druid连接池配置
        * 数据库初始化脚本
    * **要审计的潜在风险/漏洞类型**: 
        1. 数据库凭据硬编码
        2. 数据库连接参数安全配置缺失
        3. 连接池配置不当导致的拒绝服务
        4. 数据库驱动版本已知漏洞
    * **建议的白盒代码审计方法/关注点**: 
        1. 检查数据库密码是否硬编码或过于简单
        2. 验证数据库连接是否启用SSL加密传输
        3. 审查连接池的最大连接数和超时配置
        4. 检查MySQL驱动版本是否存在已知安全漏洞
        5. 确认Druid监控页面的访问控制配置
    * **部署上下文与优先级**: 数据库直接暴露3306端口，配置安全至关重要。优先级：高

### 业务逻辑代码审计 (优先级：中)

- [ ] CODE-REVIEW-ITEM-009: 用户注册登录业务逻辑审计
    * **目标代码/配置区域**: 
        * `com.macro.mall.admin.service.impl.UmsAdminServiceImpl.java`
        * `com.macro.mall.portal.service.impl.UmsMemberServiceImpl.java` 
        * 用户密码处理相关的工具类
    * **要审计的潜在风险/漏洞类型**: 
        1. 用户名枚举漏洞
        2. 弱密码策略
        3. 密码存储安全问题
        4. 账户锁定策略缺失
        5. 重复注册检查缺失
    * **建议的白盒代码审计方法/关注点**: 
        1. 分析登录失败时的错误信息是否统一，避免用户名枚举
        2. 检查密码复杂度验证逻辑
        3. 审查密码加密存储方式，确认是否使用强哈希算法
        4. 验证连续登录失败的锁定机制
        5. 检查用户注册时的唯一性验证逻辑
    * **部署上下文与优先级**: 用户管理是系统的基础功能，影响账户安全。优先级：中

- [ ] CODE-REVIEW-ITEM-010: 订单支付业务逻辑审计
    * **目标代码/配置区域**: 
        * `com.macro.mall.portal.service.impl.OmsOrderServiceImpl.java`
        * 支付相关的Controller和Service类
        * 订单状态变更相关的代码
    * **要审计的潜在风险/漏洞类型**: 
        1. 订单金额篡改
        2. 重复支付漏洞
        3. 订单状态竞态条件
        4. 支付回调验签缺失
        5. 业务时序漏洞
    * **建议的白盒代码审计方法/关注点**: 
        1. 审查订单金额计算逻辑，确认是否可被前端篡改
        2. 检查支付状态的原子性更新机制
        3. 验证支付回调的签名验证逻辑
        4. 分析并发订单处理的竞态条件保护
        5. 检查订单状态变更的权限控制
    * **部署上下文与优先级**: 支付流程涉及资金安全，是重要的业务安全点。优先级：中

- [ ] CODE-REVIEW-ITEM-011: 商品库存管理代码审计
    * **目标代码/配置区域**: 
        * 商品库存相关的Service实现类
        * 库存扣减和恢复的相关方法
        * 秒杀或促销活动相关代码
    * **要审计的潜在风险/漏洞类型**: 
        1. 库存超卖漏洞
        2. 库存数值溢出
        3. 库存操作竞态条件
        4. 恶意库存占用
    * **建议的白盒代码审计方法/关注点**: 
        1. 检查库存扣减的原子性操作实现
        2. 验证库存数量的边界值检查
        3. 分析高并发场景下的库存一致性保护
        4. 审查库存预占和释放的超时机制
    * **部署上下文与优先级**: 库存管理直接影响业务准确性和用户体验。优先级：中

### 第三方集成代码审计 (优先级：中)

- [ ] CODE-REVIEW-ITEM-012: Redis缓存安全代码审计
    * **目标代码/配置区域**: 
        * Redis相关的Service和Util类
        * `application-prod.yml` 中的Redis配置
        * `com.macro.mall.security.aspect.RedisCacheAspect.java`
    * **要审计的潜在风险/漏洞类型**: 
        1. Redis连接未认证
        2. 缓存数据包含敏感信息
        3. 缓存键名冲突或预测性攻击
        4. 缓存穿透和雪崩风险
        5. 序列化安全问题
    * **建议的白盒代码审计方法/关注点**: 
        1. 检查Redis连接是否配置了密码认证
        2. 审查缓存中是否存储了密码等敏感数据
        3. 验证缓存键的命名规则和随机性
        4. 检查缓存失效的处理逻辑
        5. 分析对象序列化和反序列化的安全性
    * **部署上下文与优先级**: Redis直接暴露6379端口，存在直接访问风险。优先级：中

- [ ] CODE-REVIEW-ITEM-013: MinIO对象存储安全审计
    * **目标代码/配置区域**: 
        * MinIO相关的Service和配置类
        * `application-prod.yml` 中的MinIO配置
        * 文件访问权限设置相关代码
    * **要审计的潜在风险/漏洞类型**: 
        1. MinIO访问凭据泄露
        2. 存储桶权限配置过于宽松
        3. 文件访问控制缺失
        4. 未授权文件访问
    * **建议的白盒代码审计方法/关注点**: 
        1. 检查MinIO的AccessKey和SecretKey是否为默认值
        2. 审查存储桶的权限策略配置
        3. 验证文件上传后的访问权限设置
        4. 检查文件下载时的权限验证逻辑
    * **部署上下文与优先级**: MinIO服务直接暴露，默认凭据存在安全风险。优先级：中

- [ ] CODE-REVIEW-ITEM-014: RabbitMQ消息队列安全审计
    * **目标代码/配置区域**: 
        * RabbitMQ相关的Producer和Consumer代码
        * 消息发送和接收的相关Service类
        * `application-prod.yml` 中的RabbitMQ配置
    * **要审计的潜想风险/漏洞类型**: 
        1. 消息队列未授权访问
        2. 消息内容包含敏感信息
        3. 消息投毒攻击
        4. 消息处理逻辑漏洞
        5. 不安全的消息反序列化
    * **建议的白盒代码审计方法/关注点**: 
        1. 检查RabbitMQ连接的认证配置
        2. 审查消息内容是否包含敏感数据
        3. 验证消息消费者的输入验证逻辑
        4. 检查异常消息的处理机制
        5. 分析消息序列化和反序列化的安全性
    * **部署上下文与优先级**: RabbitMQ暴露管理端口，存在直接访问风险。优先级：中

### 配置与依赖安全审计 (优先级：低)

- [ ] CODE-REVIEW-ITEM-015: 系统配置文件安全审计
    * **目标代码/配置区域**: 
        * 所有`application*.yml`配置文件
        * `logback-spring.xml`日志配置文件
        * Docker相关配置文件
    * **要审计的潜在风险/漏洞类型**: 
        1. 敏感信息硬编码
        2. 调试信息泄露
        3. 不安全的默认配置
        4. 过度详细的错误信息暴露
    * **建议的白盒代码审计方法/关注点**: 
        1. 检查所有配置文件中的密码、密钥等敏感信息
        2. 审查日志级别和输出内容的安全性
        3. 验证错误处理和异常信息的暴露程度
        4. 检查生产环境配置的安全性设置
    * **部署上下文与优先级**: 配置安全是整体安全的基础保障。优先级：低

- [ ] CODE-REVIEW-ITEM-016: 第三方依赖安全漏洞审计
    * **目标代码/配置区域**: 
        * 根目录和各模块的`pom.xml`文件
        * 重点关注Spring Boot、Spring Security、MyBatis、JWT等核心依赖版本
    * **要审计的潜在风险/漏洞类型**: 
        1. 使用包含已知漏洞的依赖版本
        2. 依赖冲突导致的安全降级
        3. 传递依赖的安全风险
        4. 未及时更新的安全补丁
    * **建议的白盒代码审计方法/关注点**: 
        1. 对照CVE数据库检查所有依赖的版本安全性
        2. 重点关注Spring Boot 2.7.5、JWT 0.9.1等关键依赖
        3. 使用Maven security scanner等工具辅助检查
        4. 验证依赖更新的兼容性和安全性改进
    * **部署上下文与优先级**: 第三方依赖漏洞可能影响整个系统安全。优先级：低

### Elasticsearch安全专项审计

- [ ] CODE-REVIEW-ITEM-017: Elasticsearch查询安全专项审计
    * **目标代码/配置区域**: 
        * 所有与Elasticsearch交互的DAO和Service类
        * Elasticsearch查询构建的工具类
        * 搜索结果转换和处理逻辑
    * **要审计的潜在风险/漏洞类型**: 
        1. Elasticsearch脚本注入
        2. 恶意聚合查询导致的DoS
        3. 搜索结果数据泄露
        4. 权限绕过访问敏感索引
    * **建议的白盒代码审计方法/关注点**: 
        1. 审查所有Elasticsearch查询的构建过程
        2. 检查是否禁用了动态脚本执行
        3. 验证聚合查询的复杂度和资源限制
        4. 确认搜索结果的权限过滤机制
        5. 检查索引访问权限的控制逻辑
    * **部署上下文与优先级**: Elasticsearch直接暴露9200端口，存在直接查询风险。优先级：中

## 工具使用日志

### 信息收集阶段使用的工具与获取的关键信息

1. **`read_report_from_repository("DeploymentArchitectureReport.md")`**: 获取了完整的系统部署架构信息，包括：
   - 微服务架构：mall-admin、mall-portal、mall-search三个核心服务
   - 直接端口映射：所有服务通过Docker直接暴露端口，缺乏网关保护
   - 基础设施服务：MySQL、Redis、Elasticsearch、RabbitMQ、MongoDB、MinIO等都直接暴露
   - 网络拓扑：服务间通过Docker网络别名连接

2. **`read_file("/data/mall_code/pom.xml")`**: 获取了项目技术栈信息：
   - Spring Boot 2.7.5 + JDK 1.8
   - 关键依赖版本：JWT 0.9.1, MySQL Connector 8.0.29, MyBatis 3.5.10
   - 构建配置：包含Docker镜像构建配置

3. **`read_file("/data/mall_code/mall-admin/src/main/resources/application.yml")`**: 获取了核心安全配置：
   - JWT配置：secret为"mall-admin-secret"，过期时间7天
   - 文件上传：最大10MB限制
   - 安全白名单：包含多个忽略路径

4. **`read_file("/data/mall_code/mall-admin/src/main/resources/application-prod.yml")`**: 获取了生产环境配置：
   - 数据库凭据：使用reader/123456用户
   - Redis连接：无密码认证
   - MinIO配置：使用默认的minioadmin/minioadmin凭据

5. **`run_shell_command(["find", "/data/mall_code/mall-security", "-name", "*.java"])`**: 识别了安全模块结构：
   - JWT认证过滤器：JwtAuthenticationTokenFilter
   - 动态权限控制：DynamicSecurityFilter, DynamicAccessDecisionManager等
   - 安全组件：权限决策、访问控制、异常处理等

这些信息为制定代码审计计划提供了充分的技术栈、架构模式和安全配置基础，确保审计计划针对性强且覆盖全面。

## 计划执行建议

1. **执行顺序**: 建议按照检查项编号顺序执行，优先处理认证授权相关的高风险项目
2. **时间分配**: 建议将60%的时间用于前8个高优先级检查项
3. **工具辅助**: 建议结合静态代码分析工具(如SonarQube、Checkmarx)提高审计效率
4. **文档记录**: 每个检查项完成后，请在复选框中标记完成状态，并记录发现的问题和风险等级

此计划旨在为后续的深度代码审计工作提供系统性的指导，确保安全审计工作的全面性和有效性。