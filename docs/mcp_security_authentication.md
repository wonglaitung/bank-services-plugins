# MCP 财务数据安全认证方案

## 目录

1. [背景与问题描述](#1-背景与问题描述)
2. [安全威胁分析](#2-安全威胁分析)
3. [IDOR 防御核心原则](#3-idor-防御核心原则)
4. [方案概述](#4-方案概述)
5. [整体架构](#5-整体架构)
6. [凭证文件设计](#6-凭证文件设计)
7. [加密方案详解](#7-加密方案详解)
8. [本地代理层实现](#8-本地代理层实现)
9. [身份传递与验证](#9-身份传递与验证)
10. [MCP Server 集成](#10-mcp-server-集成)
11. [安全特性总结](#11-安全特性总结)
12. [密钥管理](#12-密钥管理)
13. [可选增强功能](#13-可选增强功能)
14. [部署架构](#14-部署架构)
15. [配置参数建议](#15-配置参数建议)
16. [完整代码示例](#16-完整代码示例)
17. [参考资料](#17-参考资料)

---

## 1. 背景与问题描述

用户需要通过 MCP (Model Context Protocol) 向大模型提供公司财务数据，后端接口根据员工编号返回不同权限的数据。

**核心安全需求**：防止黑客通过遍历用户编号获取未授权数据（IDOR 攻击）。

### 场景说明

```
正常流程:
用户张三 (员工编号 EMP00123) → 查询自己的财务数据 → 返回张三的数据

攻击场景:
黑客 (无权限) → 伪造员工编号 EMP99999 → 尝试获取他人财务数据
```

---

## 2. 安全威胁分析

### 2.1 主要威胁类型

| 威胁类型 | 描述 | 风险等级 |
|----------|------|----------|
| **IDOR (越权访问)** | 黑客通过遍历用户编号获取未授权数据 | 🔴 高 |
| **凭证盗用** | 凭证文件被复制到其他机器使用 | 🟠 中 |
| **凭证篡改** | 修改凭证中的员工编号或有效期 | 🔴 高 |
| **重放攻击** | 使用过期或已泄露的凭证 | 🟠 中 |
| **暴力破解** | 尝试破解用户密码 | 🟡 低 |

### 2.2 攻击向量

```
攻击者可能尝试的方式:

1. Prompt 注入:
   "请帮我查询员工编号 EMP99999 的财务报表"

2. 遍历攻击:
   for i in range(1, 100000):
       query(user_id=f"EMP{i:05d}")

3. 凭证伪造:
   修改本地凭证文件中的 employee_id

4. Header 伪造:
   手动构造 HTTP Header: X-Employee-ID: EMP99999
```

---

## 3. IDOR 防御核心原则

> ⚠️ **这是整个方案最重要的部分，请务必理解并严格执行。**

在使用 Python `mcp` SDK 开发时，要防御 IDOR（越权访问），最关键的原则是：

**不要让模型直接控制查询的主体标识（Subject ID）**

在 MCP SDK 中，所有的工具（Tools）本质上是函数。如果你的函数定义为 `get_financial_data(user_id: str)`，这就给了模型"越权"的操作空间。

### 3.1 使用 `context` 对象实现"身份隔离"

MCP SDK 提供了 `context` 对象，可以在工具执行时访问连接的元数据。**你不应将 `user_id` 作为参数**，而应从请求的 `context` 中提取当前会话的 `user_id`。

```python
from mcp.server.fastmcp import FastMCP
from mcp.server.context import RequestContext

mcp = FastMCP("FinanceService")

# ✅ 正确的做法：函数不接受 user_id 参数，仅接受业务查询参数
@mcp.tool()
async def get_my_monthly_report(month: str, ctx: RequestContext) -> str:
    """获取当前登录用户的月度财务报告"""

    # 1. 从 session 中获取当前授权用户的 ID，而不是从用户输入的参数中
    # 假设你在连接初始化阶段将 token 解析后的用户 ID 存入了 session/context
    authenticated_user_id = ctx.session.request_meta.get("user_id")

    if not authenticated_user_id:
        return "错误：未授权的访问"

    # 2. 后端查询严格使用 authenticated_user_id
    # 攻击者无法通过 prompt 改变这个变量
    data = db.query(
        "SELECT * FROM financial_records WHERE user_id = ? AND month = ?",
        authenticated_user_id,
        month
    )
    return format_data(data)

# ❌ 危险做法：接受 user_id 参数
@mcp.tool()
async def get_user_report(user_id: str, month: str) -> str:
    """获取指定用户的月度财务报告 - 危险！"""
    # 黑客可以通过 prompt 注入任意 user_id
    data = db.query(
        "SELECT * FROM financial_records WHERE user_id = ? AND month = ?",
        user_id,  # ← 攻击者可控
        month
    )
    return format_data(data)
```

### 3.2 通过"白名单"工具设计规避风险

如果必须查询财务数据，请明确区分工具的用途，杜绝模型在同一接口上"尝试"不同 ID。

| 设计方式 | 工具定义 | 风险 |
|----------|----------|------|
| ❌ **危险** | `get_user_info(user_id)` | 模型会尝试填入任意数字 |
| ✅ **安全** | `get_my_balance()` | 身份从上下文获取 |
| ✅ **安全** | `get_my_transactions(limit=10)` | 身份从上下文获取 |
| ✅ **安全** | `list_my_accounts()` | 身份从上下文获取 |

**关键原则**：通过命名和定义，将"用户身份"与"查询接口"完全解耦。所有工具函数名以 `my_` 开头，明确表示只能查询当前用户的数据。

### 3.3 在连接层进行强制鉴权 (Auth Middleware)

MCP SDK 运行在 `mcp-server` 之上，你可以在连接握手或消息传输拦截阶段进行鉴权。如果传入的 Token 无效或用户 ID 与请求头不符，直接中断连接，而不触发后续的工具函数。

```python
# 在初始化 MCP 服务器时，配置认证检查
async def validate_connection(headers):
    token = headers.get("Authorization")
    user_id = verify_jwt(token)  # 自定义逻辑
    if not user_id:
        raise Exception("Unauthorized")
    return user_id

# 在处理请求时注入 session
# 验证失败的请求不会触发任何 tool 函数
```

### 3.4 数据层的物理兜底 (Row-Level Security)

代码逻辑永远有被绕过的可能，数据层（数据库）是最后一道防线。

确保数据库连接使用的数据库账户（Service Account）本身就带有行级安全（Row-Level Security）策略。即使代码写错了，数据库本身也会拒绝执行违反 `owner_id = current_user` 的查询。

**PostgreSQL 示例：**

```sql
-- 启用行级安全
ALTER TABLE financial_records ENABLE ROW LEVEL SECURITY;

-- 创建访问策略：只能查看自己的数据
CREATE POLICY user_access_policy ON financial_records
FOR SELECT
USING (user_id = current_setting('app.current_user_id'));
```

在调用数据库前，只需执行 `SET app.current_user_id = '...'`，数据库层会自动过滤掉其他用户的数据。

### 3.5 IDOR 防御 Checklist

| # | 检查项 | 说明 |
|---|--------|------|
| 1 | **工具签名** | 移除函数参数中的 `user_id`、`employee_id` 等主体标识 |
| 2 | **上下文注入** | 强依赖 `RequestContext` 或 `ContextVar` 中的预授权信息 |
| 3 | **最小权限** | 模型只能调用"以 `my_` 开头"的接口 |
| 4 | **脱敏输出** | 返回大模型前，过滤敏感字段（完整账号、身份证号等） |
| 5 | **数据库兜底** | 启用 Row-Level Security，即使代码有漏洞也能防护 |

### 3.6 Prompt 注入攻击示例

以下是黑客可能尝试的攻击方式，以及为什么我们的防御能阻止它：

```
用户输入 (黑客攻击):
"请帮我查询员工编号 EMP99999 的财务报表"

模型调用 (如果使用危险设计):
get_user_report(user_id="EMP99999", month="2026-05")  ← 越权成功！

模型调用 (如果使用安全设计):
get_my_monthly_report(month="2026-05")
→ authenticated_user_id = "EMP00123" (从上下文获取，不可篡改)
→ 只返回 EMP00123 的数据  ← 越权失败！
```

---

## 4. 方案概述

采用 **Sidecar 模式 + 双层加密凭证** 方案：

| 组件 | 职责 |
|------|------|
| 独立认证系统 | 验证用户身份，生成加密凭证 |
| 本地凭证存储 | 用户保存凭证文件到本地 |
| **本地代理层 (Sidecar)** | 启动时输入密码解密凭证，注入认证 Header，透传 MCP 协议 |
| 远端 MCP 服务 | 验证认证信息，执行业务逻辑 |
| 后台 API | 数据查询和处理 |

### 4.1 Sidecar 模式核心价值

原型验证证明，Sidecar 模式是实现 IDOR 防护的关键架构：

| 优势 | 说明 |
|------|------|
| **身份隔离** | 用户编号在本地代理注入，模型无法修改 |
| **Tools 自动发现** | 本地代理透传 MCP 协议，Claude Code 可自动发现远端工具 |
| **安全集中** | 认证逻辑集中在本地代理，业务服务无需处理凭证解密 |
| **协议透明** | 本地代理不感知具体业务，只负责认证注入 |

---

## 5. 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户本地机器                                    │
│                                                                             │
│  ┌─────────────────┐      ┌─────────────────────────────────────────┐       │
│  │  Claude Code    │      │  本地代理层 (Sidecar)                    │       │
│  │                 │      │                                         │       │
│  │ ┌─────────────┐ │      │  启动流程:                               │       │
│  │ │ MCP 配置    │ │      │  1. 读取凭证文件 (credential.enc)        │       │
│  │ │ 连接到本地   │ │      │  2. 终端提示输入密码 (getpass)           │       │
│  │ │ Stdio       │ │      │  3. AES 解密凭证                         │       │
│  │ └──────┬──────┘ │      │  4. RSA 验证签名                         │       │
│  │        │        │      │  5. 验证有效期                           │       │
│  │        │ Stdio  │      │                                         │       │
│  │        │ (本地) │      │  运行时职责:                             │       │
│  │        ├────────▶│      │  • 透传 MCP JSON-RPC 协议               │       │
│  │                 │      │  • 自动注入 HTTP Header                  │       │
│  │                 │      │  • 记录调用日志                          │       │
│  │                 │      │                                         │       │
│  │                 │      │        │                                │       │
│  └─────────────────┘      │        │ HTTPS                          │       │
│                           │        │ + 认证 Header                   │       │
│                           │        ▼                                │       │
│                           └─────────────────────────────────────────┘       │
│                                      │                                      │
└──────────────────────────────────────┼──────────────────────────────────────┘
                                       │
                                       │ HTTPS (加密通信)
                                       │ Authorization: Bearer <Token>
                                       │ X-Employee-ID: <员工编号>
                                       │ X-Credential-Signature: <签名>
                                       │ X-Credential-Expires: <过期时间>
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              公司服务器                                      │
│                                                                             │
│  ┌─────────────────┐      ┌─────────────────┐                              │
│  │  远端 MCP 服务   │      │  后台 API       │                              │
│  │                 │      │  (业务逻辑)     │                              │
│  │  • 验证签名     │      │                 │                              │
│  │  • 检查有效期   │◀────▶│  • 用户查询     │                              │
│  │  • 执行 Tools   │      │  • 数据库访问   │                              │
│  │  • 审计日志     │      │                 │                              │
│  │                 │      │                 │                              │
│  └─────────────────┘      └─────────────────┘                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.1 认证系统架构

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
```
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

---

## 6. 凭证文件设计

### 6.1 凭证内容结构

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

### 6.2 加密文件结构

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

### 6.3 签名内容

签名对象为以下字段的拼接：

```
签名内容 = employee_id + ":" + expires_at

示例: "EMP00123:2026-05-24T18:00:00Z"
```

使用 RSA 私钥对签名内容进行签名，确保员工编号和有效期不可篡改。

---

## 7. 加密方案详解

### 7.1 外层：用户密码加密 (AES-256-GCM)

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

### 7.2 内层：RSA 私钥签名

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

### 7.3 凭证解密与验证

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

---

## 8. 本地代理层实现

本地代理层（Sidecar）是 Sidecar 模式的核心组件，原型验证了以下关键实现。

### 8.1 本地代理职责

| 职责 | 说明 |
|------|------|
| **凭证解密** | 启动时从用户输入密码解密凭证文件 |
| **身份注入** | 在每个 HTTP 请求中自动注入认证 Header |
| **协议透传** | 透传 MCP JSON-RPC 协议，不定义任何工具 |
| **调用日志** | 记录所有 MCP 调用用于审计 |

### 8.2 MCP 协议透传原理

```
Claude Code ◀──Stdio──▶ 本地代理 ◀──HTTPS──▶ 远端 MCP 服务
    │                        │                      │
    │    MCP 协议 (JSON-RPC)  │     HTTP + Token    │
    │                        │                      │
    │  tools/list ──────────────────────────────────▶ 定义在远端
    │  tools/call ──────────────────────────────────▶ 执行在远端
    │                        │                      │
    │                        │  自动注入:           │
    │                        │  • Authorization     │
    │                        │    (Bearer Token)    │
```

**关键点**：
- 本地代理使用 `mcp.server.Server` 类实现真正的 MCP 服务器
- 所有工具定义在远端服务，本地代理动态获取并注册
- Claude Code 通过本地代理自动发现远端工具
- 用户身份封装在加密 Token 中，本地代理无法查看或修改

### 8.3 Token 刷新管理

本地代理使用 `TokenRefreshManager` 类管理 Access Token 自动刷新：

```python
class TokenRefreshManager:
    """
    管理 Refresh Token，自动获取 Access Token

    流程：
    1. 从环境变量读取 MCP_REFRESH_TOKEN
    2. 调用远端 /auth/refresh 获取 Access Token
    3. Access Token 过期时自动刷新
    """

    def __init__(self, remote_url: str):
        self.remote_url = remote_url
        self.refresh_token = os.environ.get("MCP_REFRESH_TOKEN")
        self.access_token = None
        self.access_token_expires_at = None

        # 兼容旧配置：如果设置了 MCP_AUTH_TOKEN，使用它
        self.legacy_token = os.environ.get("MCP_AUTH_TOKEN")

        if not self.refresh_token and not self.legacy_token:
            raise ValueError("未配置认证令牌，请设置环境变量 MCP_REFRESH_TOKEN")

    async def get_valid_access_token(self) -> str:
        """
        获取有效的 Access Token

        如果 Access Token 即将过期（< 1分钟），自动刷新。
        """
        # 传统模式：直接返回 MCP_AUTH_TOKEN
        if self.legacy_token and not self.refresh_token:
            return self.legacy_token

        now = datetime.now(timezone.utc)

        # 检查缓存的 Access Token 是否有效（预留 1 分钟）
        if self.access_token and self.access_token_expires_at:
            if now < self.access_token_expires_at - timedelta(minutes=1):
                return self.access_token

        # 需要刷新
        logger.info("Access Token 即将过期，正在刷新...")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.remote_url}/auth/refresh",
                json={"refresh_token": self.refresh_token}
            )

            data = response.json()
            self.access_token = data.get("access_token")
            self.access_token_expires_at = now + timedelta(seconds=data["expires_in"])

            logger.info(f"Access Token 刷新成功，有效期 {data['expires_in']} 秒")
            return self.access_token
```

**关键设计点**：

| 设计 | 说明 |
|------|------|
| **Access Token 缓存** | 缓存 Access Token，过期前 1 分钟自动刷新 |
| **兼容旧配置** | 支持 `MCP_AUTH_TOKEN` 环境变量（传统模式，无自动刷新） |
| **错误处理** | 刷新失败时抛出异常，由调用方处理 |

### 8.4 本地代理实现代码

> **重要提示**：本地代理使用 `mcp.server.Server` 类实现真正的 MCP 服务器，通过 stdio 与 Claude Code 通信，动态获取远端工具列表。

```python
"""
MCP 协议透传代理

本地代理作为 MCP Server 实现：
- 接收 Claude Code 的 MCP 请求 (Stdio)
- 使用 Server 实例处理 MCP 协议握手
- 在每个请求中自动注入加密 Token
- 通过 HTTPS 转发到远端 MCP 服务
- 返回远端服务的响应

关键特性：
- Tools 定义在远端服务，本地代理通过 HTTP 获取
- 用户身份封装在加密 Token 中，本地代理无法查看
- Token 从环境变量读取，模型无法修改

安全设计：
- 本地代理只知道 Token，不知道用户身份
- 用户身份由远端服务从 Token 解密获取
- 有效期由 Token 内部控制，无法绕过
"""

import os
import sys
import json
import logging
import httpx

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr  # 日志输出到 stderr，不影响 stdio 通信
)
logger = logging.getLogger(__name__)


def get_config() -> dict:
    """
    获取配置

    Returns:
        包含 token 和 remote_url 的字典

    Raises:
        ValueError: 配置缺失
    """
    token = os.environ.get("MCP_AUTH_TOKEN")
    remote_url = os.environ.get("REMOTE_MCP_URL", "http://localhost:8001")

    if not token:
        raise ValueError("未配置认证令牌，请设置环境变量 MCP_AUTH_TOKEN")

    return {
        "token": token,
        "remote_url": remote_url
    }


# ==================== 远端通信 ====================

async def fetch_tools_from_remote(ctx: dict) -> list[Tool]:
    """
    从远端获取工具列表并转换为 Tool 对象

    Args:
        ctx: 配置上下文

    Returns:
        Tool 对象列表
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{ctx['remote_url']}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list"
                },
                headers={
                    "Authorization": f"Bearer {ctx['token']}",
                    "Content-Type": "application/json"
                }
            )

            if response.status_code != 200:
                logger.error(f"获取工具列表失败: HTTP {response.status_code}")
                return []

            data = response.json()
            if "error" in data:
                logger.error(f"远端返回错误: {data['error']}")
                return []

            tools_data = data.get("result", {}).get("tools", [])
            logger.info(f"从远端获取 {len(tools_data)} 个工具")

            # 转换为 Tool 对象
            tools = []
            for t in tools_data:
                try:
                    tool_dict = {
                        "name": t.get("name"),
                        "description": t.get("description"),
                        "inputSchema": t.get("inputSchema", {"type": "object", "properties": {}})
                    }
                    tools.append(Tool(**tool_dict))
                except Exception as e:
                    logger.warning(f"转换工具失败: {t.get('name')}, {e}")

            return tools

    except Exception as e:
        logger.error(f"获取工具列表异常: {e}")
        return []


async def call_tool_on_remote(name: str, arguments: dict, ctx: dict) -> str:
    """
    在远端调用工具

    Args:
        name: 工具名称
        arguments: 工具参数
        ctx: 配置上下文

    Returns:
        工具执行结果（字符串）
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ctx['remote_url']}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": name,
                        "arguments": arguments
                    }
                },
                headers={
                    "Authorization": f"Bearer {ctx['token']}",
                    "Content-Type": "application/json"
                }
            )

            if response.status_code != 200:
                return f"远端服务错误: HTTP {response.status_code}"

            data = response.json()

            if "error" in data:
                error_msg = data["error"].get("message", "未知错误")
                return f"工具执行失败: {error_msg}"

            # 提取结果
            result = data.get("result", {})
            content = result.get("content", [])
            if content and isinstance(content, list) and len(content) > 0:
                text_content = content[0]
                if isinstance(text_content, dict):
                    return text_content.get("text", str(result))
                elif isinstance(text_content, str):
                    return text_content
                else:
                    return str(text_content)

            return str(result)

    except httpx.ConnectError as e:
        logger.error(f"无法连接远端服务: {e}")
        return "无法连接远端服务"
    except Exception as e:
        logger.error(f"调用工具异常: {e}")
        return f"调用失败: {str(e)}"


# ==================== MCP 服务器实现 ====================

async def run_server():
    """运行 MCP 服务器"""
    # 获取配置
    ctx = get_config()

    logger.info(f"MCP 代理启动，目标: {ctx['remote_url']}")

    # 预加载工具列表
    remote_tools = await fetch_tools_from_remote(ctx)
    logger.info(f"已加载 {len(remote_tools)} 个工具")

    # 创建 MCP Server 实例
    server = Server("finance-proxy")

    # 注册 list_tools 处理器
    @server.list_tools()
    async def list_tools():
        """返回远端工具列表"""
        tools = await fetch_tools_from_remote(ctx)
        return tools

    # 注册 call_tool 处理器
    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """代理工具调用"""
        logger.info(f"调用工具: {name}, 参数: {arguments}")
        result = await call_tool_on_remote(name, arguments, ctx)
        return [TextContent(type="text", text=result)]

    # 使用 stdio_server 创建传输层
    async with stdio_server() as (read_stream, write_stream):
        logger.info("MCP 服务器已启动，等待连接...")

        # 获取初始化选项
        init_options = server.create_initialization_options()

        # 运行服务器
        await server.run(read_stream, write_stream, init_options)


def main():
    """主入口"""
    import anyio
    try:
        anyio.run(run_server)
    except ValueError as e:
        logger.error(f"配置错误: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

**关键设计点**（原型验证）：

| 设计 | 说明 |
|------|------|
| **Server 实例** | 使用 `mcp.server.Server` 创建真正的 MCP 服务器 |
| **list_tools 处理器** | 从远端获取工具列表并转换为 `Tool` 对象 |
| **call_tool 处理器** | 转发工具调用到远端，返回 `TextContent` 结果 |
| **initialization_options** | 使用 `server.create_initialization_options()` 获取默认初始化选项 |
| **工具自动注册** | Claude Code 通过 MCP 协议自动发现并注册工具 |

### 8.5 Claude Code 配置

MCP 配置文件位置：

| 位置 | 说明 | 优先级 |
|------|------|--------|
| 项目目录 `.mcp.json` | 项目级别配置，与团队共享 | 高 |
| 用户目录 `~/.claude/mcp.json` | 用户级别配置，仅本机有效 | 中 |

**推荐使用项目级配置**，在项目根目录创建 `.mcp.json` 文件：

```json
{
  "mcpServers": {
    "finance-proxy": {
      "command": "python",
      "args": ["/absolute/path/to/prototype/local_proxy/main.py"],
      "env": {
        "REMOTE_MCP_URL": "http://localhost:8001",
        "MCP_REFRESH_TOKEN": "<使用 generate_token.py 生成>"
      }
    }
  }
}
```

**环境变量说明**：

| 变量名 | 说明 | 必需 |
|--------|------|------|
| `REMOTE_MCP_URL` | 远端 MCP 服务地址 | ✅ |
| `MCP_REFRESH_TOKEN` | Refresh Token（推荐，支持自动刷新） | ✅ |
| `MCP_AUTH_TOKEN` | 传统 Token（兼容旧配置，无自动刷新） | ⚠️ |

**注意**：
- `args` 中的路径必须使用**绝对路径**
- `MCP_AUTH_TOKEN` 使用 Token 生成工具生成
- 用户身份封装在 Token 中，无需单独配置员工编号
- 本地代理依赖：`mcp>=1.0.0`, `httpx>=0.25.0`, `anyio>=3.0.0`

---

## 9. 身份传递与验证

> **原型验证说明**：原型验证了使用加密 Token 的认证方式，用户身份封装在 Token 中，本地代理无法查看。以下是基于原型验证的设计。

### 9.1 Token 机制概述

原型验证了 **Access Token + Refresh Token** 双 Token 机制：

| Token 类型 | 有效期 | 用途 | 存储 |
|------------|--------|------|------|
| **Access Token** | 15 分钟 | 调用 MCP API | 内存（自动刷新） |
| **Refresh Token** | 7 天（可配置） | 获取新 Access Token | `.mcp.json` 配置 |

**安全优势**：
- Access Token 有效期短，即使泄露风险有限
- Refresh Token 支持吊销，泄露后可立即止损
- 本地代理自动刷新，用户无感知

### 9.2 客户端请求格式

原型验证了使用单一 Bearer Token 的认证方式：

```
POST /mcp HTTP/1.1
Host: mcp-server.example.com
Content-Type: application/json
Authorization: Bearer <Access Token>
```

**Access Token 内容（加密后）**：
```json
{
  "user_id": "000000001",
  "token_type": "access",
  "jti": "xyz789",
  "expires_at": "2026-05-25T10:15:00Z",
  "issued_at": "2026-05-25T10:00:00Z"
}
```

**Refresh Token 内容（加密后）**：
```json
{
  "user_id": "000000001",
  "token_type": "refresh",
  "jti": "abc123",
  "expires_at": "2026-06-01T10:00:00Z",
  "issued_at": "2026-05-25T10:00:00Z"
}
```

| 字段 | 说明 | 示例 |
|------|------|------|
| user_id | 用户编号（9位数字） | 000000001 |
| token_type | Token 类型 | access / refresh |
| jti | Token 唯一标识（用于吊销） | abc123 |
| expires_at | Token 过期时间 (ISO 8601) | 2026-05-25T18:00:00Z |
| issued_at | Token 签发时间 | 2026-05-25T10:00:00Z |

### 9.2 Token 生成（认证系统）

Token 分为两种类型，都在服务器端生成：

```python
import os
import json
import base64
import secrets
from datetime import datetime, timezone, timedelta
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Token 类型
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

# Access Token 固定 15 分钟有效期
ACCESS_TOKEN_EXPIRES_MINUTES = 15


def generate_token(user_id: str, token_type: str, expires_at: datetime, key: bytes) -> tuple:
    """
    生成加密 Token

    Args:
        user_id: 用户编号（9位数字）
        token_type: Token 类型 (access/refresh)
        expires_at: 过期时间
        key: AES-256 密钥（32 bytes）

    Returns:
        (Base64 编码的加密 Token, jti)
    """
    now = datetime.now(timezone.utc)
    jti = secrets.token_urlsafe(16)  # Token 唯一标识

    token_data = {
        "user_id": user_id,
        "token_type": token_type,
        "jti": jti,
        "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "issued_at": now.strftime("%Y-%m-%dT%H:%M:%SZ")
    }

    # AES-GCM 加密
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    plaintext = json.dumps(token_data).encode('utf-8')
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    # 组装并 Base64 编码
    encrypted = nonce + ciphertext
    return base64.b64encode(encrypted).decode('utf-8'), jti


def generate_token_pair(user_id: str, refresh_expires_days: int, key: bytes) -> dict:
    """
    生成 Access Token + Refresh Token 对

    Args:
        user_id: 用户编号（9位数字）
        refresh_expires_days: Refresh Token 有效期（天）
        key: AES-256 密钥（32 bytes）

    Returns:
        包含 refresh_token 和 refresh_jti 的字典
    """
    now = datetime.now(timezone.utc)

    # Access Token（15 分钟有效）
    access_expires = now + timedelta(minutes=ACCESS_TOKEN_EXPIRES_MINUTES)
    access_token, access_jti = generate_token(user_id, TOKEN_TYPE_ACCESS, access_expires, key)

    # Refresh Token（可配置天数）
    refresh_expires = now + timedelta(days=refresh_expires_days)
    refresh_token, refresh_jti = generate_token(user_id, TOKEN_TYPE_REFRESH, refresh_expires, key)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "refresh_jti": refresh_jti,
        "refresh_expires_at": refresh_expires
    }
```

**使用示例**：

```bash
# 生成 Token 对（Refresh Token 有效 7 天）
python prototype/tools/generate_token.py --user-id 000000001 --refresh-expires 7
```

#### 9.3.1 Token 解密与验证（远端服务）

```python
import base64
import json
from datetime import datetime, timezone
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Request, HTTPException

def decrypt_token(token_b64: str, key: bytes) -> dict:
    """
    解密 Token 获取用户身份

    Args:
        token_b64: Base64 编码的加密 Token
        key: AES-256 密钥（32 bytes）

    Returns:
        包含 user_id, token_type, jti, expires_at 的字典

    Raises:
        ValueError: Token 无效或过期
    """
    try:
        # 1. Base64 解码
        encrypted = base64.b64decode(token_b64)

        # 2. 解析 nonce 和 ciphertext
        if len(encrypted) < 12:
            raise ValueError("Token 格式错误")
        nonce = encrypted[:12]
        ciphertext_with_tag = encrypted[12:]

        # 3. AES-GCM 解密
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext_with_tag, None)

        # 4. 解析 JSON
        token_data = json.loads(plaintext.decode('utf-8'))

        # 5. 验证必要字段
        if 'user_id' not in token_data or 'expires_at' not in token_data:
            raise ValueError("Token 缺少必要字段")

        # 6. 验证有效期
        expires_at_str = token_data['expires_at']
        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
        if datetime.now(timezone.utc) > expires_at:
            raise ValueError("Token 已过期")

        return token_data

    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Token 解密失败: {str(e)}")


async def verify_request(request: Request, token_key: bytes) -> str:
    """
    验证请求并返回用户编号

    Returns:
        验证通过的用户编号

    Raises:
        HTTPException: 认证失败
    """
    # 提取 Token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token_b64 = auth_header[7:]
    else:
        token_b64 = auth_header

    if not token_b64:
        raise HTTPException(401, "缺少认证 Token")

    try:
        # 解密 Token
        token_data = decrypt_token(token_b64, token_key)
        user_id = token_data["user_id"]

        # 验证用户编号格式（必须为9位数字）
        if not user_id.isdigit() or len(user_id) != 9:
            raise HTTPException(400, "用户编号格式错误")

        return user_id

    except ValueError as e:
        raise HTTPException(401, str(e))
```

### 9.4 Token 刷新与吊销

#### 9.4.1 Token 刷新流程

当 Access Token 过期时，本地代理自动调用 `/auth/refresh` 端点获取新 Token：

```
┌─────────────────────────────────────────────────────────────────┐
│                     Token 刷新流程                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 本地代理检测 Access Token 即将过期（< 1 分钟）               │
│     └── 或 Access Token 已过期                                  │
│                                                                 │
│  2. 调用 /auth/refresh 端点                                      │
│     POST /auth/refresh                                          │
│     { "refresh_token": "<Refresh Token>" }                      │
│                                                                 │
│  3. 远端服务验证 Refresh Token                                   │
│     ├── 解密 Token                                              │
│     ├── 验证 token_type == "refresh"                            │
│     ├── 检查吊销黑名单                                          │
│     └── 验证有效期                                              │
│                                                                 │
│  4. 生成新的 Access Token                                       │
│     └── 有效期 15 分钟                                          │
│                                                                 │
│  5. 返回新 Access Token                                         │
│     { "access_token": "<new token>", "expires_in": 900 }        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### 9.4.2 Token 刷新端点实现

```python
# Token 类型
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"
ACCESS_TOKEN_EXPIRES_MINUTES = 15

# 吊销黑名单文件
REVOKED_TOKENS_FILE = "prototype/tools/revoked_tokens.json"


def load_revoked_tokens() -> set:
    """加载吊销的 Token JTI 黑名单"""
    if os.path.exists(REVOKED_TOKENS_FILE):
        with open(REVOKED_TOKENS_FILE, 'r') as f:
            return set(json.load(f))
    return set()


def is_token_revoked(jti: str) -> bool:
    """检查 Token 是否被吊销"""
    return jti in load_revoked_tokens()


@app.post("/auth/refresh")
async def refresh_token(request: Request):
    """
    使用 Refresh Token 获取新的 Access Token

    请求: {"refresh_token": "xxx"}
    响应: {"access_token": "yyy", "expires_in": 900}
    """
    data = await request.json()
    refresh_token = data.get("refresh_token")

    if not refresh_token:
        raise HTTPException(400, "缺少 refresh_token")

    # 验证 Refresh Token
    token_data = decrypt_token(refresh_token, TOKEN_KEY)

    if token_data.get("token_type") != TOKEN_TYPE_REFRESH:
        raise HTTPException(401, "需要 Refresh Token")

    # 检查吊销黑名单
    jti = token_data.get("jti")
    if is_token_revoked(jti):
        raise HTTPException(401, "Token 已被吊销")

    user_id = token_data["user_id"]

    # 生成新的 Access Token
    access_token = generate_access_token(user_id)

    return {
        "access_token": access_token,
        "expires_in": ACCESS_TOKEN_EXPIRES_MINUTES * 60  # 秒
    }
```

#### 9.4.3 Token 吊销机制

当 Refresh Token 泄露或需要禁用时，管理员可调用 `/auth/revoke` 端点吊销：

```python
def add_to_revoked_list(jti: str):
    """添加到吊销黑名单"""
    revoked = load_revoked_tokens()
    revoked.add(jti)
    with open(REVOKED_TOKENS_FILE, 'w') as f:
        json.dump(list(revoked), f, indent=2)


@app.post("/auth/revoke")
async def revoke_token(request: Request):
    """
    吊销 Refresh Token

    请求: {"jti": "abc123"}
    响应: {"status": "revoked"}
    """
    data = await request.json()
    jti = data.get("jti")

    if not jti:
        raise HTTPException(400, "缺少 jti")

    # 添加到黑名单
    add_to_revoked_list(jti)

    return {"status": "revoked"}
```

**吊销流程**：

```bash
# 1. 查看 Token 清单找到 jti
cat prototype/tools/token_records.json

# 2. 调用吊销接口
curl -X POST http://localhost:8001/auth/revoke \
  -H "Content-Type: application/json" \
  -d '{"jti": "abc123"}'
```

**说明**：
- Access Token 有效期短（15 分钟），无需吊销检查
- Refresh Token 需要检查吊销黑名单
- 吊销黑名单存储在 `prototype/tools/revoked_tokens.json`

#### 9.4.4 Token 清单记录

所有生成的 Token 记录在 `prototype/tools/token_records.json`：

```json
[
  {
    "user_id": "000000001",
    "refresh_jti": "abc123",
    "refresh_expires_at": "2026-06-01T10:00:00Z",
    "issued_at": "2026-05-25T10:00:00Z",
    "status": "active"
  }
]
```

### 9.5 安全机制说明

**为什么使用加密 Token 而不是多 Header 方式？**

| 对比项 | 多 Header 方式 | 加密 Token 方式（原型验证） |
|--------|----------------|---------------------------|
| 实现复杂度 | 需要签名和验证 | 仅需加密解密 |
| 身份隔离 | 本地代理知道员工编号 | 本地代理不知道员工编号 |
| 传输开销 | 3 个 Header | 1 个 Header |
| 修改难度 | 修改 Header 即可 | 需要解密才能修改 |

**原型验证结论**：加密 Token 方式更安全，本地代理无法查看用户身份，有效防止 IDOR 攻击。

### 9.6 攻击防御分析

```
攻击场景: 黑客尝试伪造身份

1. 黑客尝试修改 Token:
   Token = "伪造的Token"

2. 解密失败:
   - Token 使用 AES-256-GCM 加密
   - 没有密钥无法解密
   - 解密失败返回 401

3. 黑客尝试重放过期 Token:
   - Token 包含 expires_at
   - 服务端验证有效期
   - 过期 Token 返回 401

4. 结论: 无法伪造或重放
```

---

## 10. MCP Server 集成

> **原型验证说明**：原型验证了远端 MCP 服务的完整实现，包括 Token 解密、MCP 协议处理、notification 处理等。

### 10.1 服务架构

MCP Server 使用 FastAPI 作为 HTTP 层，FastMCP 作为 MCP 协议处理层：

```
HTTP 请求 → FastAPI 中间件（认证） → MCP JSON-RPC 处理 → Tool 执行
```

### 10.2 完整服务实现（原型验证）

```python
import os
import sys
import json
import base64
import logging
from datetime import datetime, timezone
from contextvars import ContextVar
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import httpx
from mcp.server.fastmcp import FastMCP

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    print("错误: 需要安装 cryptography 库")
    sys.exit(1)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 当前用户上下文（每个请求独立）
current_user_id: ContextVar[str] = ContextVar("current_user_id")

# 创建 MCP 服务
mcp = FastMCP("FinanceService")

# FastAPI 应用
app = FastAPI(title="MCP 远端服务")

# 配置
BACKEND_API_URL = os.environ.get("BACKEND_API_URL", "http://localhost:8000")

# Token 加密密钥（从环境变量读取）
_TOKEN_KEY_B64 = os.environ.get("TOKEN_KEY")
if _TOKEN_KEY_B64:
    TOKEN_KEY = base64.b64decode(_TOKEN_KEY_B64)
else:
    # 原型测试时使用固定密钥（生产环境必须从环境变量读取）
    TOKEN_KEY = b'prototype-test-key-32-bytes-!!!!'  # 32 bytes
    logger.warning("使用测试密钥，生产环境请设置 TOKEN_KEY 环境变量")


# ==================== Token 解密 ====================

def decrypt_token(token_b64: str) -> dict:
    """解密 Token 获取用户身份"""
    try:
        encrypted = base64.b64decode(token_b64)
        if len(encrypted) < 12:
            raise ValueError("Token 格式错误")
        nonce = encrypted[:12]
        ciphertext_with_tag = encrypted[12:]
        aesgcm = AESGCM(TOKEN_KEY)
        plaintext = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
        token_data = json.loads(plaintext.decode('utf-8'))
        if 'user_id' not in token_data or 'expires_at' not in token_data:
            raise ValueError("Token 缺少必要字段")
        expires_at_str = token_data['expires_at']
        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
        if datetime.now(timezone.utc) > expires_at:
            raise ValueError("Token 已过期")
        return token_data
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Token 解密失败: {str(e)}")


# ==================== 认证中间件 ====================

async def verify_request(request: Request) -> str:
    """验证请求并返回用户编号"""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token_b64 = auth_header[7:]
    else:
        token_b64 = auth_header

    if not token_b64:
        raise HTTPException(401, "缺少认证 Token")

    try:
        token_data = decrypt_token(token_b64)
        user_id = token_data["user_id"]

        # 验证 Token 类型（必须是 Access Token）
        token_type = token_data.get("token_type", "access")
        if token_type != "access":
            raise HTTPException(401, "需要 Access Token")

        if not user_id.isdigit() or len(user_id) != 9:
            raise HTTPException(400, "用户编号格式错误")
        logger.info(f"用户认证成功: {user_id}")
        return user_id
    except ValueError as e:
        raise HTTPException(401, str(e))


# ==================== MCP Tools 定义 ====================

@mcp.tool()
async def get_my_info() -> dict:
    """获取当前用户的信息"""
    user_id = current_user_id.get()
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BACKEND_API_URL}/api/user/{user_id}")
        if response.status_code == 404:
            return {"error": "用户不存在"}
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def get_my_balance() -> dict:
    """获取当前用户的账户余额"""
    user_id = current_user_id.get()
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BACKEND_API_URL}/api/user/{user_id}")
        if response.status_code == 404:
            return {"error": "用户不存在"}
        response.raise_for_status()
        user_data = response.json()
        return {
            "user_id": user_id,
            "name": user_data.get("name"),
            "balance": user_data.get("balance", 0)
        }


# ==================== MCP 请求端点 ====================

@app.post("/mcp")
async def handle_mcp_request(request: Request):
    """处理 MCP JSON-RPC 请求"""
    try:
        user_id = await verify_request(request)
        current_user_id.set(user_id)

        mcp_request = await request.json()
        method = mcp_request.get("method", "")
        request_id = mcp_request.get("id")

        logger.info(f"MCP 请求: method={method}, user={user_id}")

        if method == "tools/list":
            tools = await mcp.list_tools()
            return {
                "jsonrpc": "2.0",
                "result": {"tools": tools},
                "id": request_id
            }

        elif method == "tools/call":
            params = mcp_request.get("params", {})
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            result = await mcp.call_tool(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "result": {"content": [{"type": "text", "text": str(result)}]},
                "id": request_id
            }

        elif method == "initialize":
            return {
                "jsonrpc": "2.0",
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "FinanceService", "version": "1.0.0"}
                },
                "id": request_id
            }

        elif method == "notifications/initialized":
            # notification 不需要响应
            logger.info(f"客户端初始化完成: user={user_id}")
            return None

        elif method == "ping":
            return {
                "jsonrpc": "2.0",
                "result": {},
                "id": request_id
            }

        else:
            # 未知方法：notification 不返回错误，request 返回错误
            if request_id is None:
                logger.warning(f"忽略未知 notification: {method}")
                return None
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method not found: {method}"},
                "id": request_id
            }

    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"error": e.detail}
        )
    except Exception as e:
        logger.error(f"处理 MCP 请求失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"内部服务器错误: {str(e)}"}
        )


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
```

### 10.3 关键实现要点

| 要点 | 说明 |
|------|------|
| **FastMCP API** | 使用 `mcp.list_tools()` 和 `mcp.call_tool()` 处理 JSON-RPC |
| **ContextVar** | 确保每个请求的用户身份独立，不跨请求共享 |
| **JSON-RPC 2.0** | 响应必须包含 `jsonrpc`、`result`/`error`、`id` 字段 |
| **认证前置** | 在调用 MCP 方法前完成认证，失败直接返回 401 |
| **工具签名** | 工具函数不接受 `user_id` 参数，从上下文获取 |
| **Notification 处理** | `notifications/initialized` 返回 None，不发送响应 |
| **协议版本** | 使用 `2024-11-05` MCP 协议版本 |

### 10.4 MCP Notification 处理说明

**原型验证发现**：MCP 协议中有两种消息类型：

| 类型 | 特点 | 处理方式 |
|------|------|----------|
| **Request** | 有 `id` 字段，需要响应 | 必须返回响应 |
| **Notification** | 没有 `id` 字段，不需要响应 | 返回 `None` |

**关键代码**：
```python
elif method == "notifications/initialized":
    # notification 不需要响应
    logger.info(f"客户端初始化完成: user={user_id}")
    return None  # 不返回响应

# 未知方法处理
else:
    if request_id is None:
        # notification 类型，不返回错误
        logger.warning(f"忽略未知 notification: {method}")
        return None
    # request 类型，返回错误
    return {
        "jsonrpc": "2.0",
        "error": {"code": -32601, "message": f"Method not found: {method}"},
        "id": request_id
    }
```

### 10.5 工具函数设计原则

遵循 IDOR 防御核心原则：

| 设计方式 | 工具定义 | 风险 |
|----------|----------|------|
| ❌ **危险** | `get_user_info(user_id)` | 模型会尝试填入任意数字 |
| ✅ **安全** | `get_my_balance()` | 身份从上下文获取 |
| ✅ **安全** | `get_my_transactions(limit=10)` | 身份从上下文获取 |
| ✅ **安全** | `check_my_permission()` | 身份从上下文获取 |

**关键原则**：工具函数名以 `my_` 开头，不接受 `user_id` 参数，从 `ContextVar` 获取当前用户身份。

---

## 11. 安全特性总结

### 11.1 Token 安全机制

| 安全威胁 | 防御机制 | 实现位置 |
|----------|----------|----------|
| **Token 盗用** | Access Token 15 分钟有效期，风险窗口小 | Token 有效期 |
| **Token 泄露** | Refresh Token 支持吊销，可立即止损 | 吊销黑名单 |
| **Token 重放** | Token 包含有效期，过期自动失效 | 有效期验证 |
| **Token 伪造** | AES-256-GCM 加密，无密钥无法伪造 | Token 加密 |

### 11.2 IDOR 防御机制

| 安全威胁 | 防御机制 | 实现位置 |
|----------|----------|----------|
| **遍历用户编号 (IDOR)** | 员工编号从签名凭证获取，无法伪造 | 签名验证 |
| **篡改员工编号** | RSA 私钥签名，修改后签名验证失败 | 签名验证 |
| **篡改有效期** | 有效期包含在签名内容中 | 签名验证 |
| **凭证文件被盗** | AES 用户密码加密，无密码无法解密 | 外层加密 |
| **暴力破解密码** | PBKDF2 迭代 100000 次，增加破解成本 | 密钥派生 |
| **重放攻击** | 有效期控制，过期需重新生成 | 有效期验证 |
| **伪造 HTTP Header** | 签名验证确保 Header 不可伪造 | 服务端验证 |

### 11.3 安全改进对比

| 对比项 | 原方案 | 新方案（双 Token） |
|--------|--------|-------------------|
| Token 有效期 | 8 小时 | 15 分钟（Access）/ 7 天（Refresh） |
| 盗用风险窗口 | 8 小时 | 15 分钟 |
| Token 吊销 | 不支持 | ✅ 支持（Refresh Token 黑名单） |
| 自动刷新 | 不支持 | ✅ 支持 |
| Token 清单 | 无 | ✅ 服务器记录 |

---

## 12. 密钥管理

### 12.1 RSA 密钥对

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

### 12.2 密钥存储位置

| 密钥 | 存储位置 | 访问权限 |
|------|----------|----------|
| RSA 私钥 | 认证系统服务器 | 仅认证系统 |
| RSA 公钥 | MCP Server + 客户端配置 | 公开 |
| 用户密码 | 不存储 | 仅用户知晓 |

---

## 13. 可选增强功能

### 12.1 机器绑定

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

### 12.2 审计日志

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

### 12.3 密码重试限制

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

---

## 14. 部署架构

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

---

## 15. 配置参数建议

| 参数 | 建议值 | 说明 |
|------|--------|------|
| 凭证有效期 | 4-8 小时 | 平衡安全与便利 |
| AES 密钥长度 | 256 bit | AES-256 |
| RSA 密钥长度 | 2048 bit | 标准 RSA 强度 |
| PBKDF2 迭代次数 | 100,000 | 增加暴力破解成本 |
| 密码最小长度 | 8 字符 | 包含字母和数字 |
| 密码重试限制 | 3 次 | 超过后锁定 5 分钟 |

---

## 16. 完整代码示例

### 15.1 认证系统 - 凭证生成

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

### 15.2 客户端 - 凭证加载

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

### 15.3 MCP Server - 中间件

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

---

## 17. 参考资料

- [MCP (Model Context Protocol) 官方文档](https://modelcontextprotocol.io/)
- [cryptography 库文档](https://cryptography.io/)
- [OWASP IDOR 防护指南](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/05-Authorization_Testing/04-Testing_for_Insecure_Direct_Object_References)
