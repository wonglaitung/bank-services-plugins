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
    │    MCP 协议 (JSON-RPC)  │     HTTP + Header    │
    │                        │                      │
    │  tools/list ──────────────────────────────────▶ 定义在远端
    │  tools/call ──────────────────────────────────▶ 执行在远端
    │                        │                      │
    │                        │  自动注入:           │
    │                        │  • X-Employee-ID     │
    │                        │  • X-Credential-Sig  │
    │                        │  • X-Credential-Exp  │
```

**关键点**：
- 本地代理不定义任何工具，所有工具定义在远端服务
- Claude Code 通过本地代理自动发现远端工具
- 用户编号和签名在本地代理注入，模型无法修改

### 8.3 本地代理实现代码

> **重要提示**：MCP SDK v1.27+ 中 `FastMCP` 没有 `hook` 方法。本地代理需要使用 `anyio` 直接处理 stdin/stdout 流实现 JSON-RPC 消息透传。

```python
"""
本地 MCP 代理 (Sidecar)

职责：
1. 从环境变量或凭证文件获取用户身份
2. 透传 MCP JSON-RPC 协议
3. 在每个请求中自动注入认证 Header

关键技术点：
- 使用 anyio 处理 stdin/stdout 异步 I/O
- JSON-RPC 消息透传，不依赖 FastMCP
- 环境变量在启动时读取，运行时不可修改
"""

import os
import sys
import json
import logging
import httpx
import anyio

from mcp.shared.message import SessionMessage
import mcp.types as types

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr  # 日志输出到 stderr，不影响 stdio 通信
)
logger = logging.getLogger(__name__)


def get_user_context() -> dict:
    """
    获取用户上下文

    从凭证文件解密后获取员工编号和签名信息。
    环境变量在启动时一次性读取，运行时不可修改。

    Returns:
        包含 employee_id、signature、expires_at 的字典
    """
    employee_id = os.environ.get("MCP_EMPLOYEE_ID")
    signature = os.environ.get("MCP_CREDENTIAL_SIGNATURE")
    expires_at = os.environ.get("MCP_CREDENTIAL_EXPIRES")
    remote_url = os.environ.get("REMOTE_MCP_URL", "http://localhost:8001")

    if not employee_id:
        raise ValueError("未配置员工编号，请设置环境变量 MCP_EMPLOYEE_ID")
    if not signature:
        raise ValueError("未配置凭证签名，请设置环境变量 MCP_CREDENTIAL_SIGNATURE")

    return {
        "employee_id": employee_id,
        "signature": signature,
        "expires_at": expires_at,
        "remote_url": remote_url
    }


async def forward_request(
    request: types.JSONRPCMessage,
    ctx: dict
) -> types.JSONRPCMessage:
    """
    转发 MCP 请求到远端服务

    Args:
        request: MCP JSON-RPC 请求
        ctx: 用户上下文

    Returns:
        远端服务的响应
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{ctx['remote_url']}/mcp",
            json=request.root.model_dump(by_alias=True, exclude_none=True),
            headers={
                "X-Employee-ID": ctx["employee_id"],
                "X-Credential-Signature": ctx["signature"],
                "X-Credential-Expires": ctx["expires_at"],
                "Content-Type": "application/json"
            }
        )

        if response.status_code != 200:
            logger.error(f"远端服务错误: status={response.status_code}")
            error_response = {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": f"远端服务错误: {response.status_code}"},
                "id": request.root.id
            }
            return types.JSONRPCMessage.model_validate(error_response)

        return types.JSONRPCMessage.model_validate(response.json())


async def run_proxy():
    """运行代理主循环"""
    ctx = get_user_context()
    logger.info(f"MCP 代理启动，目标: {ctx['remote_url']}")

    # 使用 anyio 进行异步 I/O
    async with anyio.create_task_group() as tg:
        async with await anyio.open_file(sys.stdin.fileno(), "r") as stdin:
            async with await anyio.open_file(sys.stdout.fileno(), "w") as stdout:
                async for line in stdin:
                    try:
                        # 解析 JSON-RPC 消息
                        message = types.JSONRPCMessage.model_validate_json(line)

                        # 记录请求日志
                        method = getattr(message.root, "method", "unknown")
                        request_id = getattr(message.root, "id", "?")
                        logger.info(f"转发 MCP 请求: method={method}, id={request_id}")

                        # 转发请求
                        response = await forward_request(message, ctx)

                        # 发送响应
                        json_str = response.root.model_dump_json(by_alias=True, exclude_none=True)
                        await stdout.write(json_str + "\n")
                        await stdout.flush()

                    except httpx.ConnectError as e:
                        logger.error(f"无法连接远端服务: {e}")
                        error_response = {
                            "jsonrpc": "2.0",
                            "error": {"code": -32603, "message": "无法连接远端服务"},
                            "id": None
                        }
                        await stdout.write(json.dumps(error_response) + "\n")
                        await stdout.flush()

                    except Exception as e:
                        logger.error(f"处理请求失败: {e}")
                        error_response = {
                            "jsonrpc": "2.0",
                            "error": {"code": -32603, "message": f"内部错误: {str(e)}"},
                            "id": None
                        }
                        await stdout.write(json.dumps(error_response) + "\n")
                        await stdout.flush()


def main():
    """主入口"""
    try:
        anyio.run(run_proxy)
    except ValueError as e:
        logger.error(f"配置错误: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

### 8.4 Claude Code 配置

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
      "args": ["prototype/local_proxy/main.py"],
      "env": {
        "REMOTE_MCP_URL": "http://localhost:8001",
        "MCP_EMPLOYEE_ID": "EMP00123",
        "MCP_CREDENTIAL_SIGNATURE": "<签名>",
        "MCP_CREDENTIAL_EXPIRES": "2026-05-24T18:00:00Z"
      }
    }
  }
}
```

**注意**：
- `args` 中的路径必须使用**绝对路径**
- 生产环境中的签名和过期时间从凭证文件解密获取
- 本地代理依赖：`mcp>=1.0.0`, `httpx>=0.25.0`, `anyio>=3.0.0`

---

## 9. 身份传递与验证

### 9.1 客户端请求头

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

### 9.2 服务端验证逻辑

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

### 9.3 签名防伪造原理

```
攻击场景: 黑客尝试伪造 HTTP Header

1. 黑客构造请求:
   X-Employee-ID: EMP99999 (目标员工)
   X-Credential-Signature: ??? (需要签名)
   X-Credential-Expires: 2026-05-24T18:00:00Z

2. 签名验证内容:
   sign_content = "EMP99999:2026-05-24T18:00:00Z"

3. 验证失败原因:
   - 签名需要用 RSA 私钥生成
   - 黑客没有私钥，无法生成有效签名
   - 使用其他凭证的签名会导致验证失败

4. 结论: 无法伪造
```

---

## 10. MCP Server 集成

### 9.1 服务架构

MCP Server 使用 FastAPI 作为 HTTP 层，FastMCP 作为 MCP 协议处理层：

```
HTTP 请求 → FastAPI 中间件（认证） → MCP JSON-RPC 处理 → Tool 执行
```

### 9.2 完整服务实现

```python
import os
import logging
from contextvars import ContextVar
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import httpx
from mcp.server.fastmcp import FastMCP

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 当前员工上下文（每个请求独立）
current_employee_id: ContextVar[str] = ContextVar("current_employee_id")

# 创建 MCP 服务
mcp = FastMCP("SecureFinanceService")

# FastAPI 应用
app = FastAPI(title="MCP 安全认证服务")

# RSA 公钥（用于验证签名）
PUBLIC_KEY = load_public_key()  # 从配置加载


# ==================== 认证验证 ====================

async def verify_employee_headers(request: Request) -> str:
    """
    验证 HTTP Header 中的员工身份

    Returns:
        验证通过的员工编号

    Raises:
        HTTPException: 认证失败
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

    logger.info(f"员工认证成功: {employee_id}")
    return employee_id


# ==================== MCP Tools 定义 ====================

@mcp.tool()
async def get_my_balance() -> dict:
    """
    获取当前用户的账户余额

    注意：不接受任何用户标识参数，身份从上下文获取
    """
    employee_id = current_employee_id.get()

    # 数据库查询强制使用当前员工编号
    return db.query(
        "SELECT account_no, balance FROM accounts WHERE owner_id = ?",
        employee_id
    )


@mcp.tool()
async def get_my_transactions(month: str, limit: int = 10) -> list:
    """
    获取当前用户的交易记录

    参数:
        month: 月份，格式 YYYY-MM
        limit: 返回记录数量限制
    """
    employee_id = current_employee_id.get()

    return db.query(
        """SELECT date, amount, type, description
           FROM transactions
           WHERE emp_id = ? AND date LIKE ?
           ORDER BY date DESC LIMIT ?""",
        employee_id, f"{month}%", limit
    )


@mcp.tool()
async def get_department_summary() -> dict:
    """
    获取部门财务汇总（需要管理员权限）
    """
    employee_id = current_employee_id.get()

    # 权限检查
    user_roles = get_user_roles(employee_id)
    if "admin" not in user_roles:
        raise PermissionError("权限不足：需要管理员角色")

    # 记录审计日志
    log_audit(actor=employee_id, action="view_department_summary")

    return db.query(
        "SELECT * FROM department_summary WHERE dept = ?",
        get_user_department(employee_id)
    )


# ==================== MCP 请求端点 ====================

@app.post("/mcp")
async def handle_mcp_request(request: Request):
    """
    处理 MCP JSON-RPC 请求

    1. 验证认证信息
    2. 注入员工上下文
    3. 根据 method 调用对应的 MCP 方法
    """
    try:
        # 验证认证
        employee_id = await verify_employee_headers(request)

        # 注入员工上下文
        current_employee_id.set(employee_id)

        # 获取 MCP 请求体
        mcp_request = await request.json()
        method = mcp_request.get("method", "")
        request_id = mcp_request.get("id")

        # 记录审计日志
        logger.info(f"MCP 请求: method={method}, employee={employee_id}")

        # 根据 method 处理请求
        if method == "tools/list":
            # 返回工具列表
            tools = await mcp.list_tools()
            return {
                "jsonrpc": "2.0",
                "result": {"tools": tools},
                "id": request_id
            }

        elif method == "tools/call":
            # 调用工具
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
            # 初始化响应
            return {
                "jsonrpc": "2.0",
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "SecureFinanceService", "version": "1.0.0"}
                },
                "id": request_id
            }

        else:
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

### 9.3 关键实现要点

| 要点 | 说明 |
|------|------|
| **FastMCP API** | 使用 `mcp.list_tools()` 和 `mcp.call_tool()` 处理 JSON-RPC |
| **ContextVar** | 确保每个请求的用户身份独立，不跨请求共享 |
| **JSON-RPC 2.0** | 响应必须包含 `jsonrpc`、`result`/`error`、`id` 字段 |
| **认证前置** | 在调用 MCP 方法前完成认证，失败直接返回 401 |
| **工具签名** | 工具函数不接受 `user_id` 参数，从上下文获取 |

### 9.4 工具函数设计原则
```

---

## 11. 安全特性总结

| 安全威胁 | 防御机制 | 实现位置 |
|----------|----------|----------|
| **遍历用户编号 (IDOR)** | 员工编号从签名凭证获取，无法伪造 | 签名验证 |
| **篡改员工编号** | RSA 私钥签名，修改后签名验证失败 | 签名验证 |
| **篡改有效期** | 有效期包含在签名内容中 | 签名验证 |
| **凭证文件被盗** | AES 用户密码加密，无密码无法解密 | 外层加密 |
| **暴力破解密码** | PBKDF2 迭代 100000 次，增加破解成本 | 密钥派生 |
| **重放攻击** | 有效期控制，过期需重新生成 | 有效期验证 |
| **伪造 HTTP Header** | 签名验证确保 Header 不可伪造 | 服务端验证 |

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
