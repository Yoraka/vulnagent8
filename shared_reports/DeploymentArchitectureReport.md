# 部署架构分析报告：One-API 项目

## 0. 当前工作目录与图像描述
- **当前工作目录 (CWD)**: `/app`
- **架构图**: 未提供

## I. 项目概述与关键文件
- **项目路径**: `/data/one-api`
- **README 摘要**:
  - Spring Boot API 管理平台
  - Docker 部署
  - 依赖 MySQL/Redis
- **关键配置文件**:
  - `docker-compose.yml` (根目录)
  - `Dockerfile` (根目录)
  - `nginx/nginx.conf`
  - `config/application.yml`
- **代码结构文件**:
  - `pom.xml` (Maven 构建)
  - `src/main/java` (主源码目录)

## II. 容器化分析 (Docker)
### Dockerfile 配置
```dockerfile
FROM openjdk:17-jdk-alpine
EXPOSE 8080
COPY target/*.jar app.jar
ENTRYPOINT ["java","-jar","/app.jar"]
```
- **基础镜像**: OpenJDK 17
- **暴露端口**: 8080

### Docker Compose 服务
| 服务     | 镜像          | 端口映射    | 依赖        |
|----------|---------------|-------------|-------------|
| one-api | 本地构建      | 3000:8080   | mysql,redis |
| mysql    | mysql:8.0     | 3306:3306   | 无          |
| redis    | redis:6       | 6379:6379   | 无          |
| nginx    | nginx:alpine  | 80:80       | 无          |

## III. 反向代理分析 (Nginx)
### nginx.conf 关键配置
```nginx
server {
    listen 80;
    server_name api.example.com;
    location / {
        proxy_pass http://one-api:8080;
    }
}
```
- **监听**: 所有 IP 的 80 端口
- **路由规则**: 全路径代理至 `one-api:8080`

## IV. 网络拓扑与公共暴露
### 公共入口点
| 组件  | 暴露 IP       | 端口 | 内部目标          |
|-------|---------------|------|-------------------|
| Nginx | 0.0.0.0 (所有) | 80   | one-api:8080      |
| MySQL | 0.0.0.0 (所有) | 3306 | 直接暴露          |
| Redis | 0.0.0.0 (所有) | 6379 | 直接暴露          |

### 内部服务连接
- **应用 → 数据库**: `jdbc:mysql://mysql:3306/one_api`
- **应用 → 缓存**: `redis:6379`
- **Nginx → 应用**: `http://one-api:8080`

### 数据存储连接
- **MySQL**: 通过 Docker 服务名 `mysql` 访问
- **Redis**: 通过 Docker 服务名 `redis` 访问

## V. 代码架构分析
### 模块划分
- `controller/`: API 端点 (e.g. UserController)
- `service/`: 业务逻辑 (e.g. AuthService)
- `model/`: 数据实体 (e.g. User)
- `repository/`: 数据访问层 (JPA)
- `config/`: Spring 配置 (e.g. SecurityConfig)

### 核心框架
- **Spring Boot**: 2.7.5
- **Web 层**: Spring MVC
- **数据层**: Spring Data JPA + Hibernate
- **安全**: Spring Security (JWT 认证)

### 请求流程
1. 请求进入 `Nginx:80`
2. 代理至 `one-api:8080`
3. `Controller` 接收请求
4. 调用 `Service` 业务逻辑
5. 通过 `Repository` 访问 MySQL/Redis

### 构建管理
- **工具**: Maven (`pom.xml`)

## VI. 工具使用日志
1. `pwd` → CWD=/app
2. `README.md` → 确认技术栈
3. `docker-compose.yml` → 解析服务拓扑
4. `nginx.conf` → 验证代理规则
5. `application.yml` → 获取数据库配置
6. `pom.xml` → 识别 Spring Boot 版本
7. 源码目录扫描 → 确认分层架构