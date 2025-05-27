# JStachio 项目部署架构分析报告

## 0. 当前工作目录和项目概述

**当前工作目录 (CWD)**: /app

**项目路径**: /data/jstachio

**项目目标**: JStachio 是一个编译时类型安全的Java Mustache模板引擎项目，将模板编译为可读的Java源代码，并对值绑定进行静态检查。

## I. 项目结构概览

### 项目根目录结构
```
/data/jstachio/
├── LICENSE                   # BSD 3-Clause许可证
├── README.md                 # 项目说明文档
├── pom.xml                   # Maven多模块父项目配置文件
├── version.properties        # 版本信息文件 (version=1.0.0)
├── mvnw/mvnw.cmd            # Maven Wrapper脚本
├── .github/                  # GitHub配置目录
│   ├── dependabot.yml       # Dependabot自动依赖更新配置
│   └── workflows/           # CI/CD工作流配置
│       ├── maven.yml        # Maven构建工作流
│       ├── apidoc.yml       # API文档生成工作流
│       └── test-report.yml  # 测试报告工作流
├── api/                     # API模块父项目
├── compiler/                # 编译器模块父项目
├── test/                    # 测试模块父项目
├── opt/                     # 可选扩展模块父项目
├── spec/                    # 规范相关模块
├── doc/                     # 文档生成模块
├── bin/                     # 构建和工具脚本
└── etc/                     # 其他配置和资源文件
```

### 核心模块架构

**1. API模块 (api/)**
- `annotation/` - 注解定义模块
- `jstachio/` - 核心API模块

**2. 编译器模块 (compiler/)**
- `apt/` - 注解处理器模块
- `jstachio-prisms/` - 编译器辅助工具

**3. 可选扩展模块 (opt/)**
- `jstachio-jmustache` - JMustache后备渲染支持
- `jstachio-spring` - Spring框架集成
- `jstachio-spring-webmvc` - Spring WebMVC集成
- `jstachio-spring-webflux` - Spring WebFlux集成  
- `jstachio-spring-example` - Spring WebMVC示例应用
- `jstachio-spring-webflux-example` - Spring WebFlux示例应用

**4. 测试模块 (test/)**
- `examples/` - 示例代码和测试
- `jstachio-test-stache/` - 测试工具模块

## II. 部署环境和运行时要求

### Java环境
- **最低Java版本**: Java 17
- **编译目标版本**: Java 17
- **字符编码**: UTF-8

### Maven配置
- **Maven版本要求**: 3.9.2
- **构建工具**: Maven 3.x with Maven Wrapper
- **打包类型**: JAR (library项目)

### 运行时依赖（核心）
- **零运行时依赖**: 项目支持完全零依赖运行（生成的代码不需要JStachio运行时）
- **可选运行时依赖**: 
  - JMustache 1.15（后备渲染）
  - Spring Framework 6.0.9（Spring集成时）

## III. 服务/应用组件及交互关系

### 核心组件架构

**1. 编译时组件**
```
源代码 -> JStachio注解处理器(APT) -> 生成的Java渲染器代码 -> 编译后的字节码
```

**2. 运行时组件架构**
```
应用代码 -> JStachio API -> 生成的渲染器 -> 输出内容
                ↓
        可选:JMustache后备渲染器（开发模式）
```

**3. Spring集成组件**
```
Spring应用 -> JStachio Spring自动配置 -> JStachio渲染器 -> 模板响应
     ↓
Spring WebMVC/WebFlux -> JStachioViewResolver -> 视图渲染
```

### 示例应用组件

**Spring WebMVC示例应用**
- **应用入口**: `io.jstach.opt.spring.example.App`
- **端口**: 默认Spring Boot端口 (未明确配置，默认8080)
- **配置文件**: `application.properties`
- **配置profile**: dev, production

**Spring WebFlux示例应用**  
- **应用入口**: `io.jstach.opt.spring.webflux.example.App`
- **端口**: 默认Spring Boot WebFlux端口 (未明确配置，默认8080)
- **配置文件**: `application.properties`
- **配置profile**: dev, production

### 开发/生产环境差异配置
```properties
# 开发环境 (dev profile)
jstachio.jmustache.disable=false   # 启用JMustache后备渲染

# 生产环境 (production profile)  
jstachio.jmustache.disable=true    # 禁用JMustache后备渲染，使用编译时生成代码
```

## IV. 网络拓扑及端口使用情况

### 确定的公共暴露点
**Details not found in configuration.** 

根据配置文件分析，该项目主要是一个库项目，不包含具体的网络服务配置。示例应用使用Spring Boot默认配置：

**Spring WebMVC示例应用**
- **公共端口**: 8080 (Spring Boot默认，未在配置中明确指定)
- **协议**: HTTP
- **暴露接口**: Spring Boot Web应用默认暴露所有网络接口 (0.0.0.0:8080)

**Spring WebFlux示例应用**  
- **公共端口**: 8080 (Spring Boot默认，未在配置中明确指定)
- **协议**: HTTP (响应式)
- **暴露接口**: Spring Boot WebFlux应用默认暴露所有网络接口 (0.0.0.0:8080)

### 内部服务连接性
- **编译时处理**: 注解处理器在编译阶段运行，无网络通信
- **运行时渲染**: 内存中直接调用生成的渲染器代码，无网络通信
- **Spring集成**: 通过Spring的依赖注入和自动配置机制进行组件连接

### 指导原则遵循声明
根据配置分析，该项目的公共暴露主要通过Spring Boot示例应用实现。这些应用使用Spring Boot的默认配置在8080端口提供HTTP服务。由于没有发现Nginx、Docker或其他网关配置文件，网络暴露仅限于Spring Boot应用的直接端口映射。標准防火墙实践假设除80/443/22等标准端口外的其他端口默认被防火墙阻止，除非在基础设施或云安全组中明确开放（此处不可见）。

### 数据存储连接性
**Details not found in configuration.** 

在application.properties文件中未发现数据库连接配置（如spring.datasource.url, spring.data.redis.host等），表明示例应用可能使用内存存储或在代码中配置数据源。

## V. CI/CD和构建流程

### GitHub Actions工作流

**1. Maven构建工作流 (maven.yml)**
- **触发条件**: main分支推送、PR、手动触发
- **运行环境**: ubuntu-latest
- **Java版本**: JDK 17 (Temurin发行版)
- **构建命令**: `./mvnw clean verify`
- **缓存**: Maven依赖缓存
- **构件**: 测试结果上传到artifacts

**2. API文档工作流 (apidoc.yml)**
- **目标**: 生成和发布API文档

**3. 测试报告工作流 (test-report.yml)**  
- **目标**: 处理和发布测试报告

### 本地构建脚本
- **rebuild.sh**: 本地重新构建脚本
  ```bash
  bin/vh set pom && mvn clean package -Ddeploy=release -DskipTests -Dmaven.javadoc.skip -Dgpg.skip
  ```
- **reformat.sh**: 代码格式化脚本

### 发布配置
- **Maven Central发布**: 通过Sonatype OSSRH配置
- **快照仓库**: https://s01.oss.sonatype.org/content/repositories/snapshots
- **正式仓库**: https://s01.oss.sonatype.org/service/local/staging/deploy/maven2/
- **GPG签名**: 配置用于发布验证

## VI. 依赖清单及版本管理

### 核心框架版本
- **JStachio版本**: 1.1.0-SNAPSHOT
- **Java版本**: 17
- **Maven版本**: 3.9.2
- **Spring Framework**: 6.0.9
- **Spring Boot**: 3.1.0

### 主要运行时依赖
- **JMustache**: 1.15 (可选，后备渲染)
- **Jackson BOM**: 2.15.0 (JSON处理)
- **Jakarta Servlet API**: 6.0.0 (Web应用)

### 测试依赖
- **JUnit**: 4.13.2
- **ArchUnit**: 1.0.1 (架构测试)

### 编译时依赖
- **Eclipse JDT Annotations**: 2.2.700 (空值检查注解)
- **MetaInf Services**: 1.9 (服务提供者生成)

### 安全和质量工具
- **Maven Enforcer**: 确保Maven和JDK版本一致性
- **Spring Java Format**: 代码格式化
- **Dependabot**: 自动依赖更新

## VII. 工具使用日志

- `run_shell_command("pwd")`: 报告当前工作目录为 /app
- `list_files()`: 列出项目根目录文件结构，发现Maven多模块项目结构
- `read_file("README.md")`: 读取项目说明，确认为Java Mustache模板引擎
- `read_file("pom.xml")`: 分析主项目配置，确认Java 17和Spring 6.0.9依赖
- `run_shell_command("find ... -name "Dockerfile"...")`: 搜索Docker配置文件，未发现容器化配置
- `run_shell_command("ls -la /data/jstachio/api")`: 探索API模块结构
- `run_shell_command("ls -la /data/jstachio/opt")`: 探索可选模块，发现Spring集成组件
- `read_file("opt/jstachio-spring-example/src/main/resources/application.properties")`: 分析Spring应用配置
- `read_file("opt/jstachio-spring-example/pom.xml")`: 确认Spring Boot集成配置
- `read_file("version.properties")`: 确认项目版本为1.0.0
- `read_file(".github/workflows/maven.yml")`: 分析CI/CD配置，确认基于GitHub Actions的构建流程
- `read_file("opt/pom.xml")`: 分析可选模块依赖管理，确认Spring Boot 3.1.0版本

**分析总结**: 该项目是一个Maven多模块的Java模板引擎库项目，主要组件为编译时代码生成器，包含Spring框架集成扩展和示例应用，使用GitHub Actions进行CI/CD，支持发布到Maven Central。没有发现传统的容器化部署或反向代理配置。