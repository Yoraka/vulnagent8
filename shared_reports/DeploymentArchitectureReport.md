# Mall电商系统部署架构报告

## 0. 当前工作目录与项目概览

**当前工作目录(CWD)：** `/app`

**项目概览：** 
基于项目README.md分析，这是一个名为"mall"的电商系统项目，采用现阶段主流技术实现，包括前台商城系统及后台管理系统。项目基于Spring Boot 2.7.5 + MyBatis实现，明确采用**Docker容器化部署**。项目包含前台商城系统（首页门户、商品推荐、商品搜索等）和后台管理系统（商品管理、订单管理、会员管理等）。

## I. 项目结构与关键配置文件识别

### 项目模块结构
```
mall/
├── mall-admin        -- 后台商城管理系统接口
├── mall-portal       -- 前台商城系统接口  
├── mall-search       -- 基于Elasticsearch的商品搜索系统
├── mall-common       -- 工具类及通用代码
├── mall-security     -- SpringSecurity封装公用模块
├── mall-mbg          -- MyBatisGenerator生成的数据库操作代码
├── mall-demo         -- 框架搭建时的测试代码
└── document/         -- 文档目录
    ├── docker/       -- Docker配置目录
    │   ├── docker-compose-env.yml    -- 基础环境服务容器编排
    │   ├── docker-compose-app.yml    -- 应用服务容器编排
    │   └── nginx.conf                -- Nginx配置文件
    ├── elk/
    │   └── logstash.conf             -- Logstash配置文件
    └── sh/
        └── Dockerfile                -- 示例Dockerfile
```

### 核心技术栈
- **Spring Boot:** 2.7.5 + JDK 8
- **容器化：** Docker + Docker Compose
- **反向代理：** Nginx 1.22
- **数据库：** MySQL 5.7
- **缓存：** Redis 7.0
- **搜索：** Elasticsearch 7.17.3
- **消息队列：** RabbitMQ 3.9.11
- **文档数据库：** MongoDB 4.0
- **对象存储：** MinIO
- **日志收集：** ELK Stack (Elasticsearch + Logstash + Kibana)

## II. 容器化分析

### A. 基础环境服务 (docker-compose-env.yml)

该配置文件定义了系统所需的基础设施服务：

| 服务名 | 镜像 | 容器名 | 主机端口映射 | 内部端口 |
|--------|------|--------|-------------|----------|
| mysql | mysql:5.7 | mysql | 3306:3306 | 3306 |
| redis | redis:7 | redis | 6379:6379 | 6379 |
| nginx | nginx:1.22 | nginx | 80:80 | 80 |
| rabbitmq | rabbitmq:3.9.11-management | rabbitmq | 5672:5672, 15672:15672 | 5672, 15672 |
| elasticsearch | elasticsearch:7.17.3 | elasticsearch | 9200:9200, 9300:9300 | 9200, 9300 |
| logstash | logstash:7.17.3 | logstash | 4560:4560, 4561:4561, 4562:4562, 4563:4563 | 4560-4563 |
| kibana | kibana:7.17.3 | kibana | 5601:5601 | 5601 |
| mongo | mongo:4 | mongo | 27017:27017 | 27017 |
| minio | minio/minio | minio | 9090:9000, 9001:9001 | 9000, 9001 |

**重要配置特征：**
- MySQL配置了root密码为"root"，使用utf8mb4字符集
- Redis启用了AOF持久化（appendonly yes）
- Elasticsearch运行在单节点模式（discovery.type=single-node），JVM配置为512MB-1024MB
- Kibana通过links连接到elasticsearch（别名"es"）
- Logstash通过links连接到elasticsearch，配置4个TCP端口用于不同类型日志收集
- MinIO配置了默认的管理员账户（minioadmin/minioadmin）

### B. 应用服务 (docker-compose-app.yml)

| 服务名 | 镜像 | 容器名 | 主机端口映射 | 外部链接 |
|--------|------|--------|-------------|----------|
| mall-admin | mall/mall-admin:1.0-SNAPSHOT | mall-admin | 8080:8080 | mysql:db |
| mall-search | mall/mall-search:1.0-SNAPSHOT | mall-search | 8081:8081 | elasticsearch:es, mysql:db |
| mall-portal | mall/mall-portal:1.0-SNAPSHOT | mall-portal | 8085:8085 | redis:redis, mongo:mongo, mysql:db, rabbitmq:rabbit |

**服务间依赖关系：**
- mall-admin：依赖MySQL数据库（链接别名：db）
- mall-search：依赖Elasticsearch搜索引擎（链接别名：es）和MySQL数据库（链接别名：db）
- mall-portal：依赖Redis缓存（链接别名：redis）、MongoDB（链接别名：mongo）、MySQL数据库（链接别名：db）、RabbitMQ消息队列（链接别名：rabbit）

## III. 反向代理/API网关分析

### Nginx配置分析

基于`document/docker/nginx.conf`文件分析，Nginx配置相对基础：

```nginx
server {
    listen       80;
    server_name  localhost;
    
    location / {
        root   /usr/share/nginx/html;
        index  index.html index.htm;
    }
    
    error_page   500 502 503 504  /50x.html;
    location = /50x.html {
        root   /usr/share/nginx/html;
    }
}
```

**配置特征：**
- 监听端口：80
- 服务器名：localhost
- 处理静态文件：根目录为/usr/share/nginx/html
- 默认首页：index.html, index.htm
- 标准错误页面处理

**注意：** 当前Nginx配置主要用于静态资源服务，未发现反向代理到应用服务的配置。这表明在当前配置下，应用服务（mall-admin、mall-search、mall-portal）直接通过各自的端口对外提供服务。

## IV. 网络暴露与内部拓扑分析

### A. 公开暴露的服务入口点

基于Docker端口映射配置，以下服务可从外部访问：

| 组件 | 公开IP | 公开端口 | 内部服务 | 服务类型 |
|------|--------|----------|----------|----------|
| nginx | 0.0.0.0 | 80 | Nginx容器:80 | 静态资源服务 |
| mysql | 0.0.0.0 | 3306 | MySQL容器:3306 | 数据库服务 |
| redis | 0.0.0.0 | 6379 | Redis容器:6379 | 缓存服务 |
| rabbitmq | 0.0.0.0 | 5672, 15672 | RabbitMQ容器:5672, 15672 | 消息队列&管理界面 |
| elasticsearch | 0.0.0.0 | 9200, 9300 | ES容器:9200, 9300 | 搜索服务&集群通信 |
| logstash | 0.0.0.0 | 4560-4563 | Logstash容器:4560-4563 | 日志收集 |
| kibana | 0.0.0.0 | 5601 | Kibana容器:5601 | 日志可视化 |
| mongo | 0.0.0.0 | 27017 | MongoDB容器:27017 | 文档数据库 |
| minio | 0.0.0.0 | 9090, 9001 | MinIO容器:9000, 9001 | 对象存储&管理控制台 |
| **mall-admin** | **0.0.0.0** | **8080** | **mall-admin容器:8080** | **后台管理API** |
| **mall-search** | **0.0.0.0** | **8081** | **mall-search容器:8081** | **商品搜索API** |
| **mall-portal** | **0.0.0.0** | **8085** | **mall-portal容器:8085** | **前台商城API** |

### B. 内部服务连接

基于应用配置文件分析的内部连接关系：

#### mall-admin服务内部连接（生产环境配置）
- **数据库连接：** `jdbc:mysql://db:3306/mall` (用户: reader/123456)
- **Redis连接：** `redis:6379`
- **MinIO连接：** `http://192.168.3.101:9090` (外部IP地址)
- **日志收集：** `logstash`主机

#### mall-portal服务内部连接（生产环境配置）  
- **数据库连接：** `jdbc:mysql://db:3306/mall` (用户: reader/123456)
- **Redis连接：** `redis:6379`
- **MongoDB连接：** `mongo:27017` (数据库: mall-port)
- **RabbitMQ连接：** `rabbit:5672` (虚拟主机: /mall, 用户: mall/mall)
- **日志收集：** `logstash`主机

#### mall-search服务内部连接（生产环境配置）
- **数据库连接：** `jdbc:mysql://db:3306/mall` (用户: reader/123456)  
- **Elasticsearch连接：** `es:9200`
- **日志收集：** `logstash`主机

### C. 网络暴露原则判断

**原则遵循声明：** 基于配置文件分析，所有列出的公开暴露服务都是基于Docker Compose中明确的端口映射配置（ports字段）。应用服务（mall-admin、mall-search、mall-portal）通过direct Docker主机端口映射直接暴露，而非通过Nginx网关路由。标准防火墙实践假设（除80/443/22等端口外，其他端口在服务器上通常默认被防火墙阻拦，除非明确配置开放）被考虑，因此仅报告明确配置的公开通路。

### D. 数据存储连接分析

| 应用服务 | 数据库类型 | 连接配置 | 连接类型 |
|----------|------------|----------|----------|
| mall-admin | MySQL | db:3306/mall | 内部网络名称 |
| mall-admin | Redis | redis:6379 | 内部网络名称 |
| mall-portal | MySQL | db:3306/mall | 内部网络名称 |
| mall-portal | Redis | redis:6379 | 内部网络名称 |
| mall-portal | MongoDB | mongo:27017/mall-port | 内部网络名称 |
| mall-portal | RabbitMQ | rabbit:5672/mall | 内部网络名称 |
| mall-search | MySQL | db:3306/mall | 内部网络名称 |  
| mall-search | Elasticsearch | es:9200 | 内部网络名称 |

**数据存储连接特征：**
- 所有应用服务都通过Docker网络别名进行内部连接
- 生产环境使用专门的数据库用户（reader）而非root用户
- MongoDB使用专门的数据库（mall-port）
- RabbitMQ使用专门的虚拟主机（/mall）和用户（mall）

## V. 日志与监控架构

### ELK Stack配置

**Logstash配置分析** (`document/elk/logstash.conf`)：

- **输入端口配置：**
  - 4560端口：debug类型日志（TCP JSON格式）
  - 4561端口：error类型日志（TCP JSON格式）  
  - 4562端口：business类型日志（TCP JSON格式）
  - 4563端口：record类型日志（TCP JSON格式）

- **输出配置：**
  - 目标Elasticsearch：`localhost:9200`
  - 索引模式：`mall-{type}-{YYYY.MM.dd}` (按日志类型和日期分索引)

- **过滤器：**
  - 对record类型日志进行JSON解析和字段清理

**日志流向：** 应用服务 → Logstash (TCP 4560-4563) → Elasticsearch → Kibana可视化

## VI. 工具使用日志

1. **`run_shell_command("pwd")`**: 确认当前工作目录为 `/app`
2. **`list_files()`**: 列出项目根目录，发现mall电商项目结构
3. **`read_file("README.md")`**: 确认项目为电商系统，基于Spring Boot + Docker容器化部署
4. **`run_shell_command(["find", "/data/mall_code", ...])`**: 查找Docker和配置文件，发现关键配置文件路径
5. **`read_file("document/docker/docker-compose-env.yml")`**: 分析基础环境服务配置，包含MySQL、Redis、Nginx、RabbitMQ、ES、Logstash、Kibana、MongoDB、MinIO等9个服务
6. **`read_file("document/docker/docker-compose-app.yml")`**: 分析应用服务配置，包含mall-admin、mall-search、mall-portal三个核心业务服务
7. **`read_file("document/docker/nginx.conf")`**: 分析Nginx配置，发现为基础静态资源服务配置，无反向代理到应用服务
8. **`read_file("mall-admin/src/main/resources/application*.yml")`**: 分析mall-admin应用配置，确认数据库、Redis、MinIO连接配置
9. **`read_file("mall-portal/src/main/resources/application*.yml")`**: 分析mall-portal应用配置，确认数据库、Redis、MongoDB、RabbitMQ连接配置
10. **`read_file("mall-search/src/main/resources/application-prod.yml")`**: 分析mall-search应用配置，确认数据库、Elasticsearch连接配置
11. **`read_file("document/elk/logstash.conf")`**: 分析日志收集配置，确认ELK Stack日志处理流程
12. **`read_file("document/sh/Dockerfile")`**: 分析Docker镜像构建配置示例
13. **`read_file("pom.xml")`**: 分析项目构建配置，确认Spring Boot版本、模块结构和Docker构建配置

## 总结

Mall电商系统采用微服务架构，通过Docker容器化部署。系统分为三个核心业务服务（后台管理、前台商城、商品搜索）和完善的基础设施服务（数据库、缓存、搜索、消息队列、对象存储、日志监控）。当前配置下，所有服务都通过直接端口映射对外暴露，Nginx主要承担静态资源服务角色。系统具备完整的ELK日志监控体系，支持多类型日志的收集、存储和可视化分析。