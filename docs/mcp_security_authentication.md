# MCP 财务数据安全认证方案

## 1. 背景

用户需要通过 MCP (Model Context Protocol) 向大模型提供公司财务数据，后端接口根据员工编号返回不同权限的数据。

**核心安全需求**：防止黑客通过遍历用户编号获取未授权数据（IDOR 攻击）。

## 2. 方案概述

采用**双层加密凭证 + 客户端密码输入**方案：

| 组件 | 职责 |
|------|------|
| 独立认证系统 | 验证用户身份，生成加密凭证 |
| 本地凭证存储 | 用户保存凭证文件到本地 |
| 自定义客户端 | 启动时输入密码解密凭证，将员工编号注入 MCP 请求 |
| MCP Server | 从请求上下文获取员工编号，用于数据查询 |

## 3. 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  【认证系统 - 独立服务】                                                      │
│                                                                             │
│   ┌─────────┐         ┌──────────────┐         ┌──────────────────┐        │
│   │  用户   │─登录───▶│  现有认证系统  │─验证───▶│ 用户设置凭证密码  │        │
│   └─────────┘         └──────────────┘         └────────┬─────────┘        │
│                                                         │                   │
│                                                         ▼                   │
│                                              ┌────────────────────┐        │
│                                              │    双层加密生成:    │        │
│                                              │ 1. RSA私钥签名      │        │
│                                              │    (员工编号+有效期) │        │
│                                              │ 2. AES密码加密      │        │
│                                              │    (整个凭证文件)    │        │
│                                              └────────┬───────────┘        │
│                                                       │                     │
│                                                       ▼                     │
│                                              credential.enc                 │
│                                              (用户下载保存到本地)            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ 用户保存到本地
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  【自定义客户端】                                                            │
│                                                                             │
│   配置文件: client_config.json                                               │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  {                                                                   │  │
│   │    "credential_path": "~/.mcp/credential.enc",                      │  │
│   │    "public_key_path": "~/.mcp/public_key.pem",                      │  │
│   │    "mcp_server_url": "http://mcp-server:8000/sse"                   │  │
│   │  }                                                                   │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   启动流程:                                                                  │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  1. 读取配置文件                                                      │  │
│   │  2. 读取凭证文件                                                      │  │
│   │  3. 终端提示: "请输入凭证密码: " (getpass，不回显)                     │  │
│   │  4. 密码解密外层 (AES-256-GCM)                                        │  │
│   │  5. 公钥验证签名 (RSA)                                                │  │
│   │  6. 验证有效期                                                        │  │
│   │  7. 提取: 员工编号 + 签名 + 有效期                                     │  │
│   │  8. 构建HTTP Header，连接 MCP Server                                  │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│                                      │                                      │
│                                      │ HTTP Header:                         │
│                                      │ - X-Employee-ID                      │
│                                      │ - X-Credential-Signature             │
│                                      │ - X-Credential-Expires               │
│                                      ▼                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       │ SSE (HTTP)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  【MCP Server】                                                              │
│                                                                             │
│   中间件验证:                                                                │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  def verify_employee_id(request):                                    │  │
│   │      employee_id = request.headers.get("X-Employee-ID")              │  │
│   │      signature = request.headers.get("X-Credential-Signature")       │  │
│   │      expires_at = request.headers.get("X-Credential-Expires")        │  │
│   │                                                                       │  │
│   │      # 1. 检查有效期                                                  │  │
│   │      if expired(expires_at):                                         │  │
│   │          raise AuthError("凭证已过期")                                 │  │
│   │                                                                       │  │
│   │      # 2. 验证签名 (RSA公钥)                                          │  │
│   │      if not verify_signature(employee_id, expires_at, signature):    │  │
│   │          raise AuthError("签名验证失败")                               │  │
│   │                                                                       │  │
│   │      return employee_id                                              │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   工具函数 (安全封装):                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  @mcp.tool()                                                         │  │
│   │  def get_my_balance() -> dict:                                       │  │
│   │      employee_id = get_current_employee_id()  # 从上下文获取          │  │
│   │      return query_db(                                                │  │
│   │          "SELECT * FROM balance WHERE emp_id = ?",                   │  │
│   │          employee_id  # 强制使用当前员工编号                           │  │
│   │      )                                                               │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 4. 凭证文件设计

### 4.1 凭证内容结构

```json
{
  "employee_id": "EMP00123",
  "username": "zhangsan",
  "department": "FINANCE",
  "roles": ["viewer", "reporter"],
  "issued_at": "2026-05-24T10:00:00Z",
  "expires_at": "2026-05-24T18:00:00Z",
  "version": 1
}
```

### 4.2 加密文件结构

```
┌─────────────────────────────────────────────────────────────────┐
│  凭证文件 (credential.enc)                                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  【外层】AES-256-GCM 加密 (用户密码)                              │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Header:                                                   │  │
│  │  - salt (16 bytes): 密钥派生盐值                           │  │
│  │  - nonce (12 bytes): GCM 随机数                            │  │
│  │  - tag (16 bytes): 认证标签                                │  │
│  │                                                            │  │
│  │  Ciphertext:                                               │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │  【内层】签名后的凭证 JSON                            │  │  │
│  │  │  ┌───────────────────────────────────────────────┐  │  │  │
│  │  │  │  {                                             │  │  │  │
│  │  │  │    "employee_id": "EMP00123",                  │  │  │  │
│  │  │  │    "username": "zhangsan",                     │  │  │  │
│  │  │  │    "department": "FINANCE",                    │  │  │  │
│  │  │  │    "roles": ["viewer", "reporter"],            │  │  │  │
│  │  │  │    "issued_at": "2026-05-24T10:00:00Z",       │  │  │  │
│  │  │  │    "expires_at": "2026-05-24T18:00:00Z",      │  │  │  │
│  │  │  │    "signature": "<RSA签名(Base64)>",           │  │  │  │
│  │  │  │    "version": 1                                │  │  │  │
│  │  │  │  }                                             │  │  │  │
│  │  │  └───────────────────────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 签名内容

签名对象为以下字段的拼接：

```
签名内容 = employee_id + ":" + expires_at

示例: "EMP00123:2026-05-24T18:00:00Z"
```

使用 RSA 私钥对签名内容进行签名，确保员工编号和有效期不可篡改。

## 5. 加密方案详解

### 5.1 外层：用户密码加密 (AES-256-GCM)

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import os

def encrypt_with_password(plaintext: bytes, password: str) -> bytes:
    """
    使用用户密码加密凭证内容

    Args:
        plaintext: 待加密的凭证 JSON
        password: 用户设置的凭证密码

    Returns:
        加密后的凭证文件内容 (salt + nonce + ciphertext + tag)
    """
    # 1. 生成随机 salt
    salt = os.urandom(16)

    # 2. 从密码派生密钥 (PBKDF2)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,  # AES-256 需要 32 字节密钥
        salt=salt,
        iterations=100000,  # 增加暴力破解难度
    )
    key = kdf.derive(password.encode('utf-8'))

    # 3. 生成随机 nonce
    nonce = os.urandom(12)  # GCM 推荐 12 字节

    # 4. AES-GCM 加密
    aesgcm = AESGCM(key)
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext, None)

    # 5. 组装: salt (16) + nonce (12) + ciphertext + tag
    return salt + nonce + ciphertext_with_tag
```

### 5.2 内层：RSA 私钥签名

```python
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization
import base64
import json

def sign_credential(credential: dict, private_key) -> bytes:
    """
    使用 RSA 私钥对凭证进行签名

    Args:
        credential: 凭证字典 (不含 signature 字段)
        private_key: RSA 私钥对象

    Returns:
        签名后的凭证 JSON
    """
    # 1. 构建签名内容
    sign_content = f"{credential['employee_id']}:{credential['expires_at']}"

    # 2. RSA 签名
    signature = private_key.sign(
        sign_content.encode('utf-8'),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )

    # 3. 添加签名到凭证
    credential_with_sig = credential.copy()
    credential_with_sig['signature'] = base64.b64encode(signature).decode('utf-8')

    # 4. 返回 JSON 字节
    return json.dumps(credential_with_sig).encode('utf-8')
```

### 5.3 凭证解密与验证

```python
def decrypt_and_verify(encrypted_data: bytes, password: str, public_key) -> dict:
    """
    解密并验证凭证

    Args:
        encrypted_data: 加密的凭证文件内容
        password: 用户输入的密码
        public_key: RSA 公钥对象

    Returns:
        解密后的凭证字典

    Raises:
        ValueError: 密码错误、签名验证失败或凭证过期
    """
    # 1. 解析加密数据
    salt = encrypted_data[:16]
    nonce = encrypted_data[16:28]
    ciphertext_with_tag = encrypted_data[28:]

    # 2. 从密码派生密钥
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = kdf.derive(password.encode('utf-8'))

    # 3. AES-GCM 解密
    try:
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
    except Exception:
        raise ValueError("密码错误或凭证文件已损坏")

    # 4. 解析 JSON
    credential = json.loads(plaintext.decode('utf-8'))

    # 5. 验证有效期
    expires_at = datetime.fromisoformat(credential['expires_at'].replace('Z', '+00:00'))
    if datetime.now(timezone.utc) > expires_at:
        raise ValueError("凭证已过期，请重新生成")

    # 6. 验证签名
    sign_content = f"{credential['employee_id']}:{credential['expires_at']}"
    signature = base64.b64decode(credential['signature'])

    try:
        public_key.verify(
            signature,
            sign_content.encode('utf-8'),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
    except Exception:
        raise ValueError("签名验证失败，凭证可能被篡改")

    return credential
```

## 6. HTTP Header 传递规范

### 6.1 客户端请求头

```
POST /sse HTTP/1.1
Host: mcp-server.example.com
Content-Type: application/json
X-Employee-ID: EMP00123
X-Credential-Signature: YWJjZGVmZ2hpamtsbW5vcA==
X-Credential-Expires: 2026-05-24T18:00:00Z
```

| Header | 说明 | 示例 |
|--------|------|------|
| X-Employee-ID | 员工编号 | EMP00123 |
| X-Credential-Signature | RSA 签名 (Base64) | YWJjZGVm... |
| X-Credential-Expires | 凭证过期时间 (ISO 8601) | 2026-05-24T18:00:00Z |

### 6.2 服务端验证逻辑

```python
from fastapi import Request, HTTPException
from datetime import datetime, timezone

async def verify_employee_headers(request: Request) -> str:
    """
    从 HTTP Header 验证员工身份

    Returns:
        验证通过的员工编号

    Raises:
        HTTPException: 验证失败
    """
    employee_id = request.headers.get("X-Employee-ID")
    signature_b64 = request.headers.get("X-Credential-Signature")
    expires_at_str = request.headers.get("X-Credential-Expires")

    # 1. 检查必要 Header
    if not all([employee_id, signature_b64, expires_at_str]):
        raise HTTPException(401, "缺少认证信息")

    # 2. 检查有效期
    try:
        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
        if datetime.now(timezone.utc) > expires_at:
            raise HTTPException(401, "凭证已过期")
    except ValueError:
        raise HTTPException(400, "无效的过期时间格式")

    # 3. 验证签名
    sign_content = f"{employee_id}:{expires_at_str}"
    try:
        signature = base64.b64decode(signature_b64)
        PUBLIC_KEY.verify(
            signature,
            sign_content.encode('utf-8'),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
    except Exception:
        raise HTTPException(401, "签名验证失败")

    return employee_id
```

## 7. MCP Server 集成

### 7.1 中间件集成

```python
from fastapi import FastAPI, Depends, Request
from contextvars import ContextVar
from mcp.server.fastmcp import FastMCP

# 当前员工上下文
current_employee_id: ContextVar[str] = ContextVar("current_employee_id")

app = FastAPI()
mcp = FastMCP("SecureFinanceService")

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """认证中间件：验证 HTTP Header 并注入上下文"""

    # 跳过非 MCP 路径 (如健康检查)
    if not request.url.path.startswith("/mcp"):
        return await call_next(request)

    try:
        employee_id = await verify_employee_headers(request)
        current_employee_id.set(employee_id)
    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"error": e.detail}
        )

    return await call_next(request)
```

### 7.2 工具函数安全封装

```python
def get_current_employee_id() -> str:
    """获取当前已认证的员工编号"""
    employee_id = current_employee_id.get(None)
    if not employee_id:
        raise RuntimeError("未找到员工身份上下文")
    return employee_id

@mcp.tool()
def get_my_balance() -> dict:
    """
    获取当前用户的账户余额

    注意：不接受任何用户标识参数，身份从上下文获取
    """
    employee_id = get_current_employee_id()

    # 数据库查询强制使用当前员工编号
    return db.query(
        "SELECT account_no, balance FROM accounts WHERE owner_id = ?",
        employee_id
    )

@mcp.tool()
def get_my_transactions(month: str, limit: int = 10) -> list:
    """
    获取当前用户的交易记录

    参数:
        month: 月份，格式 YYYY-MM
        limit: 返回记录数量限制
    """
    employee_id = get_current_employee_id()

    return db.query(
        """SELECT date, amount, type, description
           FROM transactions
           WHERE emp_id = ? AND date LIKE ?
           ORDER BY date DESC LIMIT ?""",
        employee_id, f"{month}%", limit
    )

@mcp.tool()
def get_department_summary() -> dict:
    """
    获取部门财务汇总（需要管理员权限）
    """
    employee_id = get_current_employee_id()

    # 权限检查
    user_roles = get_user_roles(employee_id)
    if "admin" not in user_roles:
        raise PermissionError("权限不足：需要管理员角色")

    # 记录审计日志
    log_audit(actor=employee_id, action="view_department_summary")

    return db.query("SELECT * FROM department_summary WHERE dept = ?",
                    get_user_department(employee_id))
```

## 8. 安全特性总结

| 安全威胁 | 防御机制 | 实现位置 |
|----------|----------|----------|
| **遍历用户编号 (IDOR)** | 员工编号从签名凭证获取，无法伪造 | 签名验证 |
| **篡改员工编号** | RSA 私钥签名，修改后签名验证失败 | 签名验证 |
| **篡改有效期** | 有效期包含在签名内容中 | 签名验证 |
| **凭证文件被盗** | AES 用户密码加密，无密码无法解密 | 外层加密 |
| **暴力破解密码** | PBKDF2 迭代 100000 次，增加破解成本 | 密钥派生 |
| **重放攻击** | 有效期控制，过期需重新生成 | 有效期验证 |
| **伪造 HTTP Header** | 签名验证确保 Header 不可伪造 | 服务端验证 |

## 9. 密钥管理

### 9.1 RSA 密钥对

```python
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# 生成 RSA 密钥对
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048
)
public_key = private_key.public_key()

# 导出私钥 (认证系统保存)
private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.BestAvailableEncryption(b'your-master-password')
)

# 导出公钥 (分发给 MCP Server 和客户端)
public_pem = public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)
```

### 9.2 密钥存储位置

| 密钥 | 存储位置 | 访问权限 |
|------|----------|----------|
| RSA 私钥 | 认证系统服务器 | 仅认证系统 |
| RSA 公钥 | MCP Server + 客户端配置 | 公开 |
| 用户密码 | 不存储 | 仅用户知晓 |

## 10. 可选增强功能

### 10.1 机器绑定

防止凭证被复制到其他机器使用：

```python
import hashlib
import platform
import uuid

def get_machine_fingerprint() -> str:
    """获取机器指纹"""
    info = f"{platform.node()}-{uuid.getnode()}"
    return hashlib.sha256(info.encode()).hexdigest()[:16]

# 凭证中添加 machine_fingerprint 字段
# 客户端启动时验证当前机器指纹是否匹配
```

### 10.2 审计日志

```python
def log_audit(actor: str, action: str, target: str = None, result: str = "success"):
    """记录审计日志"""
    import datetime
    log_entry = {
        "timestamp": datetime.datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "target": target,
        "result": result,
        "ip": get_client_ip()  # 从请求获取
    }
    # 写入审计日志系统
    audit_logger.info(log_entry)
```

### 10.3 密码重试限制

```python
from collections import defaultdict
from datetime import datetime, timedelta

# 简单的内存限速 (生产环境建议用 Redis)
retry_count = defaultdict(list)
MAX_RETRIES = 3
LOCKOUT_TIME = timedelta(minutes=5)

def check_retry_lock(identifier: str) -> bool:
    """检查是否被锁定"""
    now = datetime.now()
    attempts = retry_count[identifier]

    # 清理过期记录
    retry_count[identifier] = [t for t in attempts if now - t < LOCKOUT_TIME]

    if len(retry_count[identifier]) >= MAX_RETRIES:
        return False  # 被锁定
    return True

def record_retry(identifier: str):
    """记录重试"""
    retry_count[identifier].append(datetime.now())
```

## 11. 部署架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              企业内网                                        │
│                                                                             │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────────────────────┐   │
│  │ 认证系统     │     │ MCP Server  │     │       数据库                 │   │
│  │ (持有私钥)   │     │ (持有公钥)  │     │  - 财务数据                  │   │
│  │             │     │             │     │  - 权限配置                  │   │
│  └──────┬──────┘     └──────┬──────┘     └──────────────┬──────────────┘   │
│         │                   │                           │                   │
│         │                   │    查询数据 (带员工ID)      │                   │
│         │                   │◀──────────────────────────│                   │
│         │                   │                           │                   │
│         │    HTTPS          │                           │                   │
│         │    (内网)         │                           │                   │
│         │                   │                           │                   │
└─────────┼───────────────────┼───────────────────────────┼───────────────────┘
          │                   │
          │                   │
          ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户终端                                        │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  自定义客户端                                                         │   │
│  │  - credential.enc (本地存储)                                         │   │
│  │  - public_key.pem (本地存储)                                         │   │
│  │  - 启动时输入密码解密                                                 │   │
│  │  - 通过 SSE 连接 MCP Server                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 12. 配置参数建议

| 参数 | 建议值 | 说明 |
|------|--------|------|
| 凭证有效期 | 4-8 小时 | 平衡安全与便利 |
| AES 密钥长度 | 256 bit | AES-256 |
| RSA 密钥长度 | 2048 bit | 标准 RSA 强度 |
| PBKDF2 迭代次数 | 100,000 | 增加暴力破解成本 |
| 密码最小长度 | 8 字符 | 包含字母和数字 |
| 密码重试限制 | 3 次 | 超过后锁定 5 分钟 |

## 13. 完整代码示例

### 13.1 认证系统 - 凭证生成

```python
# auth_service/credential_generator.py

import json
import os
import base64
from datetime import datetime, timezone, timedelta
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class CredentialGenerator:
    """凭证生成器"""

    def __init__(self, private_key_pem: bytes, private_key_password: bytes = None):
        """
        初始化凭证生成器

        Args:
            private_key_pem: RSA 私钥 PEM 格式
            private_key_password: 私钥密码 (可选)
        """
        self.private_key = serialization.load_pem_private_key(
            private_key_pem,
            password=private_key_password
        )

    def generate(
        self,
        employee_id: str,
        username: str,
        department: str,
        roles: list,
        password: str,
        expires_hours: int = 8
    ) -> bytes:
        """
        生成加密凭证

        Args:
            employee_id: 员工编号
            username: 用户名
            department: 部门
            roles: 角色列表
            password: 用户设置的凭证密码
            expires_hours: 有效期 (小时)

        Returns:
            加密后的凭证文件内容
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=expires_hours)

        # 1. 构建凭证
        credential = {
            "employee_id": employee_id,
            "username": username,
            "department": department,
            "roles": roles,
            "issued_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "version": 1
        }

        # 2. 签名
        sign_content = f"{employee_id}:{credential['expires_at']}"
        signature = self.private_key.sign(
            sign_content.encode('utf-8'),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        credential['signature'] = base64.b64encode(signature).decode('utf-8')

        # 3. 序列化
        plaintext = json.dumps(credential).encode('utf-8')

        # 4. AES 密码加密
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = kdf.derive(password.encode('utf-8'))
        nonce = os.urandom(12)

        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        # 5. 组装
        return salt + nonce + ciphertext


# 使用示例
if __name__ == "__main__":
    # 加载私钥
    with open("private_key.pem", "rb") as f:
        private_key_pem = f.read()

    generator = CredentialGenerator(private_key_pem, b"master-password")

    # 生成凭证
    credential_data = generator.generate(
        employee_id="EMP00123",
        username="zhangsan",
        department="FINANCE",
        roles=["viewer", "reporter"],
        password="user-password-123",
        expires_hours=8
    )

    # 保存到文件
    with open("credential.enc", "wb") as f:
        f.write(credential_data)

    print("凭证已生成: credential.enc")
```

### 13.2 客户端 - 凭证加载

```python
# client/auth/credential_loader.py

import json
import base64
import getpass
from datetime import datetime, timezone
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class CredentialLoader:
    """凭证加载器"""

    def __init__(self, public_key_pem: bytes):
        """
        初始化凭证加载器

        Args:
            public_key_pem: RSA 公钥 PEM 格式
        """
        self.public_key = serialization.load_pem_public_key(public_key_pem)

    def load(self, credential_path: str, password: str) -> dict:
        """
        加载并解密凭证

        Args:
            credential_path: 凭证文件路径
            password: 用户密码

        Returns:
            解密后的凭证字典
        """
        # 1. 读取凭证文件
        with open(credential_path, "rb") as f:
            encrypted_data = f.read()

        # 2. 解析加密数据
        salt = encrypted_data[:16]
        nonce = encrypted_data[16:28]
        ciphertext = encrypted_data[28:]

        # 3. 派生密钥
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = kdf.derive(password.encode('utf-8'))

        # 4. 解密
        try:
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        except Exception:
            raise ValueError("密码错误或凭证文件已损坏")

        # 5. 解析 JSON
        credential = json.loads(plaintext.decode('utf-8'))

        # 6. 验证有效期
        expires_at = datetime.fromisoformat(
            credential['expires_at'].replace('Z', '+00:00')
        )
        if datetime.now(timezone.utc) > expires_at:
            raise ValueError("凭证已过期")

        # 7. 验证签名
        sign_content = f"{credential['employee_id']}:{credential['expires_at']}"
        signature = base64.b64decode(credential['signature'])

        try:
            self.public_key.verify(
                signature,
                sign_content.encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
        except Exception:
            raise ValueError("签名验证失败")

        return credential


# 使用示例
if __name__ == "__main__":
    # 加载公钥
    with open("public_key.pem", "rb") as f:
        public_key_pem = f.read()

    loader = CredentialLoader(public_key_pem)

    # 输入密码
    password = getpass.getpass("请输入凭证密码: ")

    # 加载凭证
    try:
        credential = loader.load("credential.enc", password)
        print(f"员工编号: {credential['employee_id']}")
        print(f"有效期至: {credential['expires_at']}")
    except ValueError as e:
        print(f"错误: {e}")
```

### 13.3 MCP Server - 中间件

```python
# mcp_server/auth/middleware.py

import base64
from datetime import datetime, timezone
from contextvars import ContextVar
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# 当前员工上下文
current_employee_id: ContextVar[str] = ContextVar("current_employee_id")


class AuthMiddleware:
    """认证中间件"""

    def __init__(self, public_key_pem: bytes):
        self.public_key = serialization.load_pem_public_key(public_key_pem)

    async def __call__(self, request: Request, call_next):
        """处理请求"""

        # 跳过非 MCP 路径
        if not request.url.path.startswith("/mcp"):
            return await call_next(request)

        # 验证 Header
        try:
            employee_id = self._verify_headers(request)
            current_employee_id.set(employee_id)
        except HTTPException as e:
            return JSONResponse(
                status_code=e.status_code,
                content={"error": e.detail}
            )

        return await call_next(request)

    def _verify_headers(self, request: Request) -> str:
        """验证 HTTP Header"""
        employee_id = request.headers.get("X-Employee-ID")
        signature_b64 = request.headers.get("X-Credential-Signature")
        expires_at_str = request.headers.get("X-Credential-Expires")

        # 检查必要字段
        if not all([employee_id, signature_b64, expires_at_str]):
            raise HTTPException(401, "缺少认证信息")

        # 检查有效期
        try:
            expires_at = datetime.fromisoformat(
                expires_at_str.replace('Z', '+00:00')
            )
            if datetime.now(timezone.utc) > expires_at:
                raise HTTPException(401, "凭证已过期")
        except ValueError:
            raise HTTPException(400, "无效的时间格式")

        # 验证签名
        sign_content = f"{employee_id}:{expires_at_str}"
        try:
            signature = base64.b64decode(signature_b64)
            self.public_key.verify(
                signature,
                sign_content.encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
        except Exception:
            raise HTTPException(401, "签名验证失败")

        return employee_id


def get_current_employee_id() -> str:
    """获取当前员工编号"""
    employee_id = current_employee_id.get(None)
    if not employee_id:
        raise RuntimeError("未找到员工身份上下文")
    return employee_id
```

## 14. 参考资料

- [MCP (Model Context Protocol) 官方文档](https://modelcontextprotocol.io/)
- [cryptography 库文档](https://cryptography.io/)
- [OWASP IDOR 防护指南](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/05-Authorization_Testing/04-Testing_for_Insecure_Direct_Object_References)
