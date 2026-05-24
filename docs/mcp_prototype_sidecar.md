# MCP 安全认证原型 - Sidecar 模式

## 目录

1. [概述](#1-概述)
2. [架构设计](#2-架构设计)
3. [组件职责](#3-组件职责)
4. [数据流](#4-数据流)
5. [实现细节](#5-实现细节)
6. [配置说明](#6-配置说明)
7. [验证步骤](#7-验证步骤)
8. [扩展指南](#8-扩展指南)

---

## 1. 概述

### 1.1 背景

本原型用于验证 MCP 安全认证方案的核心流程，采用 **侧车（Sidecar）模式** 或 **本地网关（Local Gateway）模式**。

这种架构在金融行业处理高敏感数据时是最佳实践，将 MCP 服务器拆分为两个部分，有效隔离"业务逻辑"与"安全校验"。

### 1.2 为什么需要 Sidecar 模式？

传统 MCP 架构存在以下问题：

| 问题 | 说明 |
|------|------|
| **Token 存储风险** | Token 硬编码在配置文件中，容易泄露 |
| **用户编号可控** | 如果工具接受 `user_id` 参数，模型可能被诱导查询他人数据 |
| **无法分层审计** | 模型调用和实际数据查询混在一起 |
| **扩展不灵活** | 每次修改工具都需要重新部署整个服务 |

Sidecar 模式解决了这些问题：

| 优势 | 说明 |
|------|------|
| **Tools 自动发现** | Claude Code 可以自动发现远端服务的所有工具 |
| **安全隔离** | 用户编号和 Token 在本地代理注入，模型无法修改 |
| **灵活扩展** | 添加/修改工具只需改远端服务，无需改本地代理 |
| **透明转发** | 本地代理不感知具体业务，只负责认证注入 |
| **分层审计** | 本地代理记录请求日志，远端记录业务日志 |

---

## 2. 架构设计

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户本地机器                                    │
│                                                                             │
│  ┌─────────────────┐      ┌─────────────────┐                              │
│  │  Claude Code    │      │  本地代理层      │                              │
│  │                 │      │  (Local Proxy)  │                              │
│  │                 │      │                 │                              │
│  │                 │      │ ┌─────────────┐ │                              │
│  │                 │      │ │ 环境变量读取 │ │                              │
│  │                 │      │ │ • MCP_AUTH_  │ │                              │
│  │                 │      │ │   TOKEN      │ │                              │
│  │                 │      │ └─────────────┘ │                              │
│  │                 │      │                 │                              │
│  │                 │      │  职责:          │                              │
│  │  MCP 请求       │      │  • 透传协议     │                              │
│  │  (Stdio)        │      │  • 转发 Token   │                              │
│  │  ───────────────────────▶ • 记录日志     │                              │
│  │                 │      │                 │                              │
│  │                 │      │        │        │                              │
│  │                 │      │        │ HTTPS  │                              │
│  │                 │      │        │ +Token │                              │
│  │                 │      │        ▼        │                              │
│  └─────────────────┘      └─────────┬───────┘                              │
│                                     │                                       │
└─────────────────────────────────────┼───────────────────────────────────────┘
                                      │
                                      │ HTTPS (加密通信)
                                      │ Authorization: Bearer <加密Token>
                                      │ （Token内含 user_id + expires_at）
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              公司服务器                                      │
│                                                                             │
│  ┌─────────────────┐      ┌─────────────────┐                              │
│  │  MCP 远端服务   │      │  后台 API       │                              │
│  │                 │      │                 │                              │
│  │  职责:          │      │  职责:          │                              │
│  │  • 定义 Tools   │      │  • 业务逻辑     │                              │
│  │  • 解密 Token   │      │  • 数据查询     │                              │
│  │  • 验证有效期   │◀────▶│  • 数据库访问   │                              │
│  │  • 审计日志     │      │                 │                              │
│  │                 │      │                 │                              │
│  └─────────────────┘      └─────────────────┘                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 MCP 协议透传模式

本地代理作为 MCP 协议的透明转发层：

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
    │                        │    (加密Token)       │
```

**关键设计**：
- 本地代理**透传** MCP JSON-RPC 协议，不解析业务内容
- 用户身份封装在**加密 Token** 中，本地代理无法查看
- 远端服务解密 Token 获取 `user_id` 和 `expires_at`
- 修改/添加工具只需改远端服务，**无需改本地代理**

---

## 3. 组件职责

### 3.1 职责划分表

| 组件 | 职责 | 添加 Tools 时是否需要修改 |
|------|------|---------------------------|
| **本地代理** | • 从环境变量读取加密 Token<br>• 透传 MCP JSON-RPC 协议<br>• 在每个请求中自动注入 Authorization Header<br>• 记录本地调用日志 | ❌ **无需修改** |
| **远端 MCP 服务** | • 定义所有 Tools<br>• 解密 Token 获取用户编号和有效期<br>• 验证有效期<br>• 调用后台 API<br>• 记录审计日志 | ✅ **需要修改** |
| **后台 API** | • 提供业务数据查询接口<br>• 不感知用户身份（由远端服务控制） | 视业务需求 |

### 3.2 各组件详细职责

#### 本地代理层 (Local Proxy)

```
输入: Claude Code 的 MCP JSON-RPC 请求 (Stdio)
处理:
  1. 读取环境变量 MCP_AUTH_TOKEN（加密 Token）
  2. 保持原始 MCP 请求不变
  3. 在 HTTP Header 中添加:
     - Authorization: Bearer <加密Token>
  4. 通过 HTTPS 转发到远端服务
  5. 记录请求日志（可选）
输出: 远端服务的响应
```

#### 远端 MCP 服务

```
输入: 来自本地代理的 HTTPS 请求
处理:
  1. 从 Authorization Header 提取加密 Token
  2. AES-256-GCM 解密 Token
  3. 验证有效期（expires_at）
  4. 提取 user_id，验证格式（必须为9位数字）
  5. 将用户编号存入上下文 (ContextVar)
  6. 解析 MCP JSON-RPC 请求
  7. 执行对应的 Tool
  8. Tool 从上下文获取用户编号，调用后台 API
  9. 记录审计日志
输出: Tool 执行结果
```

#### 后台 API

```
输入: HTTP 请求 (用户编号在 URL 中)
处理:
  1. 验证用户编号格式
  2. 查询数据
  3. 返回结果
输出: 用户信息 JSON
```

---

## 4. 数据流

### 4.1 完整请求流程

```
1. Claude Code 发起请求
   │
   │  MCP JSON-RPC:
   │  {
   │    "jsonrpc": "2.0",
   │    "method": "tools/call",
   │    "params": {"name": "get_my_info", "arguments": {}},
   │    "id": 1
   │  }
   │
   ▼
2. 本地代理接收 (Stdio)
   │
   │  读取环境变量:
   │  - MCP_AUTH_TOKEN = "TOJvJYpY..." (加密Token)
   │
   │  构造 HTTP 请求:
   │  POST /mcp
   │  Headers:
   │    Authorization: Bearer TOJvJYpY...
   │    Content-Type: application/json
   │  Body: (原始 MCP 请求)
   │
   ▼
3. 远端 MCP 服务接收 (HTTPS)
   │
   │  解密 Token:
   │  - AES-256-GCM 解密
   │  - 提取: user_id = "000000001"
   │  - 提取: expires_at = "2026-05-25T18:00:00Z"
   │  - 验证有效期 ✓
   │  - 验证 user_id 格式 ✓
   │
   │  注入上下文: current_user_id = "000000001"
   │
   │  执行 Tool: get_my_info()
   │
   ▼
4. Tool 执行
   │
   │  user_id = current_user_id.get()  // "000000001"
   │  调用后台 API: GET http://localhost:8000/api/user/000000001
   │
   ▼
5. 后台 API 返回
   │
   │  {
   │    "user_id": "000000001",
   │    "name": "张三",
   │    "department": "财务部",
   │    "role": "viewer"
   │  }
   │
   ▼
6. 远端服务返回给本地代理
   │
   │  MCP 响应:
   │  {
   │    "jsonrpc": "2.0",
   │    "result": {"user_id": "000000001", ...},
   │    "id": 1
   │  }
   │
   ▼
7. 本地代理返回给 Claude Code (Stdio)
   │
   │  透传响应
   │
   ▼
8. Claude Code 显示结果
```

**安全关键点**：
- 用户身份封装在加密 Token 中，本地代理无法查看或修改
- 有效期由 Token 内部控制，无法绕过
- 本地代理只负责转发，不知道当前用户是谁

### 4.2 添加新工具的流程

只需要修改**远端 MCP 服务**：

```python
# mcp_remote/main.py - 添加新工具

@mcp.tool()
async def get_my_balance() -> dict:
    """
    获取当前用户的余额
    
    用户编号从上下文获取，不接受任何用户标识参数。
    """
    user_id = current_user_id.get()  # 从 Header 注入的上下文获取
    
    # 调用后台 API
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"http://localhost:8000/api/user/{user_id}"
        )
        user_data = response.json()
        return {"balance": user_data.get("balance", 0)}
```

本地代理**无需任何修改**，Claude Code 会自动发现新工具。

---

## 5. 实现细节

### 5.1 目录结构

```
prototype/
├── README.md                    # 使用说明
├── start_all.sh                 # 启动脚本（启动后台API + 远端服务）
│
├── backend_api/                 # 模拟后台 API
│   ├── main.py                  # FastAPI 后台服务 (端口 8000)
│   ├── users.json               # 模拟用户数据
│   └── requirements.txt         # 依赖: fastapi, uvicorn
│
├── mcp_remote/                  # MCP 远端服务
│   ├── main.py                  # MCP Server (HTTPS, 端口 8001)
│   ├── config.py                # 配置（后台 API 地址等）
│   └── requirements.txt         # 依赖: fastapi, uvicorn, mcp, httpx
│
└── local_proxy/                 # 本地代理层
    ├── main.py                  # 本地 MCP 代理 (Stdio)
    ├── config.py                # 配置（远端 MCP 地址等）
    └── requirements.txt         # 依赖: mcp, httpx
```

### 5.2 后台 API 代码

**`prototype/backend_api/main.py`**:

```python
"""
模拟后台 API

提供用户查询接口，不感知用户身份认证。
用户编号由调用方（远端 MCP 服务）控制。
"""

from fastapi import FastAPI, HTTPException
import json
import os

app = FastAPI(title="模拟后台 API")

# 加载模拟用户数据
DATA_FILE = os.path.join(os.path.dirname(__file__), "users.json")
with open(DATA_FILE, encoding="utf-8") as f:
    USERS = json.load(f)


@app.get("/api/user/{user_id}")
async def get_user(user_id: str):
    """
    查询用户信息
    
    Args:
        user_id: 9位数字用户编号
        
    Returns:
        用户信息字典
        
    Raises:
        400: 用户编号格式错误
        404: 用户不存在
    """
    # 验证用户编号格式
    if not user_id.isdigit() or len(user_id) != 9:
        raise HTTPException(400, "用户编号必须为9位数字")
    
    # 查询用户
    user = USERS.get(user_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    
    return user


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**`prototype/backend_api/users.json`**:

```json
{
  "000000001": {
    "user_id": "000000001",
    "name": "张三",
    "department": "财务部",
    "role": "viewer"
  },
  "000000002": {
    "user_id": "000000002",
    "name": "李四",
    "department": "财务部",
    "role": "admin"
  },
  "000000003": {
    "user_id": "000000003",
    "name": "王五",
    "department": "技术部",
    "role": "viewer"
  }
}
```

**`prototype/backend_api/requirements.txt`**:

```
fastapi>=0.100.0
uvicorn>=0.23.0
```

### 5.3 远端 MCP 服务代码

**`prototype/mcp_remote/main.py`**:

```python
"""
远端 MCP 服务

提供真正的 MCP 服务，定义所有 Tools。
从加密 Token 解密获取用户编号，用于数据查询。

关键安全原则：
- Tools 不接受 user_id 参数
- 用户编号从加密 Token 解密获取
- 所有数据查询强制使用当前用户编号
"""

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
    # 原型测试时使用固定密钥
    TOKEN_KEY = b'prototype-test-key-32-bytes-!!!!'
    logger.warning("使用测试密钥，生产环境请设置 TOKEN_KEY 环境变量")


# ==================== Token 解密 ====================

def decrypt_token(token_b64: str) -> dict:
    """
    解密 Token 获取用户身份

    Args:
        token_b64: Base64 编码的加密 Token

    Returns:
        包含 user_id, expires_at 的字典

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
        aesgcm = AESGCM(TOKEN_KEY)
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

    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Token 解密失败: {str(e)}")


# ==================== 认证中间件 ====================

async def verify_request(request: Request) -> str:
    """
    验证请求并返回用户编号

    从 Authorization Header 提取加密 Token，解密获取用户编号。

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
        logger.warning("缺少认证 Token")
        raise HTTPException(401, "缺少认证 Token")

    try:
        # 解密 Token
        token_data = decrypt_token(token_b64)
        user_id = token_data["user_id"]

        # 验证用户编号格式（必须为9位数字）
        if not user_id.isdigit() or len(user_id) != 9:
            logger.warning(f"用户编号格式错误: {user_id}")
            raise HTTPException(400, "用户编号格式错误")

        logger.info(f"用户认证成功: {user_id}")
        return user_id

    except ValueError as e:
        logger.warning(f"Token 验证失败: {e}")
        raise HTTPException(401, str(e))


# ==================== MCP Tools 定义 ====================

@mcp.tool()
async def get_my_info() -> dict:
    """
    获取当前用户的信息

    返回当前登录用户的详细信息，包括姓名、部门、角色等。
    不接受任何用户标识参数，身份从认证上下文获取。
    """
    user_id = current_user_id.get()

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BACKEND_API_URL}/api/user/{user_id}")
        if response.status_code == 404:
            return {"error": "用户不存在"}
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def get_my_department() -> dict:
    """
    获取当前用户所在部门的信息

    返回当前用户所属部门的基本信息。
    """
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
            "department": user_data.get("department")
        }


@mcp.tool()
async def get_my_balance() -> dict:
    """
    获取当前用户的账户余额

    返回当前用户的财务余额信息。
    """
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


@mcp.tool()
async def check_my_permission() -> dict:
    """
    检查当前用户的权限

    返回当前用户的角色和基本权限信息。
    """
    user_id = current_user_id.get()

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BACKEND_API_URL}/api/user/{user_id}")
        if response.status_code == 404:
            return {"error": "用户不存在"}
        response.raise_for_status()
        user_data = response.json()
        role = user_data.get("role", "unknown")

        return {
            "user_id": user_id,
            "name": user_data.get("name"),
            "role": role,
            "permissions": {
                "can_view": True,
                "can_edit": role == "admin",
                "can_delete": role == "admin",
                "can_approve": role == "admin"
            }
        }


# ==================== MCP 请求端点 ====================

@app.post("/mcp")
async def handle_mcp_request(request: Request):
    """
    处理 MCP JSON-RPC 请求

    1. 验证认证信息（解密 Token）
    2. 注入用户上下文
    3. 根据 method 调用对应的 MCP 方法
    """
    try:
        # 验证认证（解密 Token 获取 user_id）
        user_id = await verify_request(request)

        # 注入用户上下文
        current_user_id.set(user_id)

        # 获取 MCP 请求体
        mcp_request = await request.json()
        method = mcp_request.get("method", "")
        request_id = mcp_request.get("id")

        # 记录审计日志
        logger.info(f"MCP 请求: method={method}, user={user_id}")

        # 根据 method 处理请求
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
            # initialized notification 不需要响应
            logger.info(f"客户端初始化完成: user={user_id}")
            return None

        elif method == "ping":
            # ping 请求
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

**`prototype/mcp_remote/requirements.txt`**:

```
fastapi>=0.100.0
uvicorn>=0.23.0
httpx>=0.25.0
mcp>=1.0.0
cryptography>=41.0.0
```

### 5.4 本地代理代码

**`prototype/local_proxy/main.py`**:

```python
"""
MCP 协议透传代理

本地代理作为 MCP JSON-RPC 协议的透明转发层：
- 接收 Claude Code 的 MCP 请求 (Stdio)
- 在每个请求中自动注入加密 Token
- 通过 HTTPS 转发到远端 MCP 服务
- 返回远端服务的响应

关键特性：
- Tools 定义在远端服务，本地代理不定义任何工具
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

import mcp.types as types
from mcp.server.stdio import stdio_server

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

    只读取 Token，不解密。用户身份由远端服务解密获取。

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


async def forward_request(
    request: types.JSONRPCMessage,
    ctx: dict
) -> types.JSONRPCMessage | None:
    """
    转发 MCP 请求到远端服务

    Args:
        request: MCP JSON-RPC 请求
        ctx: 用户上下文

    Returns:
        远端服务的响应，notification 返回 None
    """
    # 获取请求数据
    request_data = request.root.model_dump(by_alias=True, exclude_none=True)

    # notification 类型消息（没有 id）不需要响应
    if "id" not in request_data or request_data["id"] is None:
        # 但仍需转发到远端
        method = request_data.get("method", "unknown")
        logger.info(f"转发 MCP notification: method={method}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{ctx['remote_url']}/mcp",
            json=request_data,
            headers={
                "Authorization": f"Bearer {ctx['token']}",
                "Content-Type": "application/json"
            }
        )

        if response.status_code != 200:
            logger.error(f"远端服务错误: status={response.status_code}")
            error_response = {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": f"远端服务错误: {response.status_code}"},
                "id": request_data.get("id")
            }
            return types.JSONRPCMessage.model_validate(error_response)

        response_data = response.json()

        # notification 不需要响应
        if "id" not in request_data or request_data["id"] is None:
            return None

        return types.JSONRPCMessage.model_validate(response_data)


async def run_proxy():
    """运行代理主循环"""
    # 获取配置
    ctx = get_user_context()

    logger.info(f"MCP 代理启动，目标: {ctx['remote_url']}")

    # 使用 MCP SDK 的 stdio_server
    async with stdio_server() as (read_stream, write_stream):
        async for session_message in read_stream:
            try:
                message = session_message.message

                # 记录请求日志
                request_data = message.root.model_dump(by_alias=True, exclude_none=True)
                method = request_data.get("method", "unknown")
                msg_id = request_data.get("id")
                logger.info(f"转发 MCP 请求: method={method}, id={msg_id}")

                # 转发请求
                response = await forward_request(message, ctx)

                # notification 不需要发送响应
                if response is None:
                    continue

                # 发送响应
                from mcp.shared.message import SessionMessage
                await write_stream.send(SessionMessage(response))

            except httpx.ConnectError as e:
                logger.error(f"无法连接远端服务: {e}")
                error_response = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": "无法连接远端服务"},
                    "id": None
                }
                await write_stream.send(SessionMessage(types.JSONRPCMessage.model_validate(error_response)))

            except Exception as e:
                logger.error(f"处理请求失败: {e}")
                error_response = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": f"内部错误: {str(e)}"},
                    "id": None
                }
                await write_stream.send(SessionMessage(types.JSONRPCMessage.model_validate(error_response)))


def main():
    """主入口"""
    import anyio
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

**`prototype/local_proxy/config.py`**:

```python
"""配置"""

import os

# 远端 MCP 服务地址
REMOTE_MCP_URL = os.environ.get("REMOTE_MCP_URL", "http://localhost:8001")

# 认证令牌（加密后的 Token）
MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN")
```

**`prototype/local_proxy/requirements.txt`**:

```
mcp>=1.0.0
httpx>=0.25.0
anyio>=3.0.0
```

**注意**：
- 本地代理只读取 `MCP_AUTH_TOKEN`，不读取 `MCP_USER_ID`
- 用户身份由远端服务从加密 Token 解密获取
- Token 内部包含 `user_id` 和 `expires_at`

---

## 6. 配置说明

### 6.1 Claude Code 配置

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
      "args": ["/data/bank-services-plugins/prototype/local_proxy/main.py"],
      "env": {
        "REMOTE_MCP_URL": "http://localhost:8001",
        "MCP_AUTH_TOKEN": "<使用 prototype/tools/generate_token.py 生成>"
      }
    }
  }
}
```

**注意**：
- `args` 中的路径必须使用**绝对路径**
- `MCP_AUTH_TOKEN` 使用 `prototype/tools/generate_token.py` 生成
- 用户身份封装在 Token 中，无需单独配置 `MCP_USER_ID`

### 6.2 启用 MCP 服务

配置完成后，重启 Claude Code，会提示是否启用 `finance-proxy` MCP 服务：

1. 选择 **Yes** 启用服务
2. Claude Code 会自动发现远端服务定义的所有工具

### 6.3 环境变量说明

| 变量名 | 说明 | 示例 | 必需 |
|--------|------|------|------|
| `REMOTE_MCP_URL` | 远端 MCP 服务地址 | `http://localhost:8001` | ✅ |
| `MCP_AUTH_TOKEN` | 加密认证令牌 | 使用 `generate_token.py` 生成 | ✅ |

### 6.4 远端服务配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `BACKEND_API_URL` | 后台 API 地址 | `http://localhost:8000` |
| `TOKEN_KEY` | AES-256 加密密钥（Base64） | 测试密钥 |

### 6.5 Token 生成

使用 `prototype/tools/generate_token.py` 生成加密 Token：

```bash
# 生成密钥（首次使用）
python prototype/tools/generate_token.py --generate-key

# 生成 Token（有效期单位：小时）
python prototype/tools/generate_token.py --user-id 000000001 --expires 8
# --expires 8 表示 Token 有效期为 8 小时
```

**参数说明**：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--generate-key` | 生成新的 AES-256 密钥 | - |
| `--show-key` | 显示当前密钥（Base64） | - |
| `--user-id` | 用户编号（9位数字） | 必需 |
| `--expires` | Token 有效期（**小时**） | 8 |

---

## 7. 验证步骤

### 7.1 启动服务

**方式一：使用启动脚本（推荐）**

```bash
# 一键启动所有服务
cd prototype
./start_all.sh
```

启动脚本会自动：
- 安装依赖
- 读取密钥文件（`tools/.token_key`）
- 启动后台 API 和远端 MCP 服务

**方式二：手动启动**

```bash
# 0. 生成密钥（首次使用）
python prototype/tools/generate_token.py --generate-key

# 1. 启动后台 API (端口 8000)
cd prototype/backend_api
pip install -r requirements.txt
python main.py

# 2. 启动远端 MCP 服务 (端口 8001)
cd prototype/mcp_remote
pip install -r requirements.txt

# 读取密钥并启动
TOKEN_KEY=$(base64 -w 0 ../tools/.token_key) TOKEN_KEY=$TOKEN_KEY python main.py

# 3. 配置 Claude Code
# 添加本地代理到 MCP 配置

# 4. 重启 Claude Code
# 本地代理会自动启动
```

### 7.2 测试调用

在 Claude Code 中：

```
请帮我查询我的用户信息
```

Claude Code 会调用 `get_my_info()` 工具，返回：

```json
{
  "user_id": "000000001",
  "name": "张三",
  "department": "财务部",
  "role": "viewer"
}
```

### 7.3 验证安全机制

| 验证项 | 测试方法 | 预期结果 |
|--------|----------|----------|
| Token 解密验证 | 使用正确密钥启动远端服务 | Token 正确解密，返回用户信息 |
| Token 过期验证 | 使用过期 Token | 返回 401 "Token 已过期" |
| Token 格式验证 | 使用无效 Base64 Token | 返回 401 "Token 格式错误" |
| 缺少 Token | 不传 Authorization Header | 返回 401 "缺少认证 Token" |
| Tools 自动发现 | 在 Claude Code 中查看可用工具 | 显示远端服务定义的所有工具 |

### 7.4 密钥管理

#### 7.4.1 密钥文件位置

密钥存储在：`prototype/tools/.token_key`

```bash
# 查看密钥
python prototype/tools/generate_token.py --show-key
# 输出: TOKEN_KEY=6Hd+908eMNP0T/4CmFKxdpkHI3HaMrINtej6VCcpx7Y=
```

#### 7.4.2 密钥生成流程

首次使用时，需要生成密钥：

```bash
# 步骤 1: 生成密钥
python prototype/tools/generate_token.py --generate-key
# 输出: 密钥已保存到 .token_key

# 步骤 2: 查看生成的密钥
python prototype/tools/generate_token.py --show-key
# 输出: TOKEN_KEY=xxx（Base64 编码的 32 字节密钥）

# 步骤 3: 使用密钥生成 Token
python prototype/tools/generate_token.py --user-id 000000001 --expires 8
# 输出: MCP_AUTH_TOKEN=xxx（加密后的 Token）
```

#### 7.4.3 Token 生成完整流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     Token 生成流程                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 读取密钥文件 .token_key                                      │
│     └── 若不存在，使用 --generate-key 生成                       │
│                                                                 │
│  2. 构造 Token 数据                                              │
│     {                                                           │
│       "user_id": "000000001",                                   │
│       "expires_at": "2026-05-25T18:00:00Z",  // 当前时间 + N小时 │
│       "issued_at": "2026-05-25T10:00:00Z"    // 当前时间         │
│     }                                                           │
│                                                                 │
│  3. AES-256-GCM 加密                                            │
│     ├── 生成随机 nonce (12 bytes)                               │
│     ├── 使用密钥加密 JSON → ciphertext + tag                    │
│     └── 组装: nonce + ciphertext + tag                          │
│                                                                 │
│  4. Base64 编码                                                  │
│     └── 输出: MCP_AUTH_TOKEN=xxx                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### 7.4.4 Token 解密流程（远端服务）

```
┌─────────────────────────────────────────────────────────────────┐
│                     Token 解密流程                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 提取 Authorization Header                                   │
│     └── token = header.replace("Bearer ", "")                  │
│                                                                 │
│  2. Base64 解码                                                  │
│     └── encrypted = base64.b64decode(token)                     │
│                                                                 │
│  3. 解析 nonce 和 ciphertext                                     │
│     ├── nonce = encrypted[:12]                                  │
│     └── ciphertext_with_tag = encrypted[12:]                    │
│                                                                 │
│  4. AES-256-GCM 解密                                             │
│     ├── 使用 TOKEN_KEY 解密                                      │
│     └── plaintext = AESGCM.decrypt(nonce, ciphertext, None)     │
│                                                                 │
│  5. 解析 JSON                                                    │
│     └── token_data = json.loads(plaintext)                      │
│                                                                 │
│  6. 验证有效期                                                   │
│     ├── expires_at = token_data["expires_at"]                   │
│     └── if now > expires_at: raise "Token 已过期"               │
│                                                                 │
│  7. 返回用户身份                                                  │
│     └── user_id = token_data["user_id"]                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### 7.4.5 密钥配置对照表

| 组件 | 是否需要密钥 | 配置方式 |
|------|--------------|----------|
| `generate_token.py` | ✅ 需要 | 自动读取 `.token_key` 文件 |
| 本地代理 | ❌ 不需要 | 只转发 Token，不解密 |
| 远端服务 | ✅ 需要 | 设置 `TOKEN_KEY` 环境变量 |

```bash
# 启动远端服务时设置密钥
TOKEN_KEY=6Hd+908eMNP0T/4CmFKxdpkHI3HaMrINtej6VCcpx7Y= python prototype/mcp_remote/main.py
```

#### 7.4.6 密钥安全注意事项

| 注意事项 | 说明 |
|----------|------|
| **密钥文件权限** | `.token_key` 应设置为 600（仅所有者可读写） |
| **密钥不要提交** | 添加到 `.gitignore`，避免泄露 |
| **生产环境** | 从安全配置中心或环境变量读取，不使用文件 |
| **密钥轮换** | 定期更换密钥，重新生成所有 Token |

### 7.4 验证添加工具无需修改代理

1. 在远端服务中添加新工具
2. 重启远端服务
3. 在 Claude Code 中查看工具列表
4. 新工具自动出现，无需修改本地代理

---

## 8. 扩展指南

### 8.1 添加新工具

只需在远端服务中添加：

```python
# mcp_remote/main.py

@mcp.tool()
async def new_tool_name(param1: str, param2: int = 10) -> dict:
    """
    工具描述（会显示给 Claude）
    
    参数:
        param1: 参数1说明
        param2: 参数2说明
    """
    user_id = current_user_id.get()  # 从上下文获取用户编号
    
    # 业务逻辑...
    
    return {"result": "..."}
```

### 8.2 后续安全增强

本原型验证通过后，可扩展：

1. **签名验证机制**
   - 参考 `docs/mcp_security_authentication.md`
   - 实现凭证签名和验证

2. **凭证文件和密码保护**
   - 用户启动时输入密码
   - 密码解密本地凭证文件

3. **有效期验证**
   - 凭证包含过期时间
   - 过期后需重新认证

4. **系统密钥库集成**
   - macOS Keychain
   - Windows Credential Manager
   - Linux Secret Service

5. **数据脱敏**
   - 在本地代理层实现
   - 敏感字段自动脱敏

### 8.3 生产环境部署

生产环境需要：

1. **HTTPS 加密通信**
   - 配置 SSL 证书
   - 强制 HTTPS

2. **IP 白名单**
   - 远端服务只接受特定 IP

3. **Token 动态管理**
   - 使用 JWT
   - 支持刷新和撤销

4. **审计日志持久化**
   - 存储到数据库或日志系统
   - 支持查询和分析

5. **监控告警**
   - 异常请求检测
   - 自动告警

---

## 9. 测试方法与经验

### 9.1 服务健康检查

```bash
# 测试后台 API 健康检查
curl -s http://localhost:8000/health
# 预期返回: {"status":"ok"}

# 测试远端 MCP 服务健康检查
curl -s http://localhost:8001/health
# 预期返回: {"status":"ok"}
```

### 9.2 后台 API 用户查询测试

```bash
# 测试查询存在的用户
curl -s http://localhost:8000/api/user/000000001 | python3 -m json.tool
# 预期返回:
# {
#     "user_id": "000000001",
#     "name": "张三",
#     "department": "财务部",
#     "role": "viewer",
#     "balance": 125000.0
# }

# 测试查询不存在的用户
curl -s http://localhost:8000/api/user/999999999 | python3 -m json.tool
# 预期返回: {"detail": "用户不存在"}

# 测试格式错误的用户编号
curl -s http://localhost:8000/api/user/123 | python3 -m json.tool
# 预期返回: {"detail": "用户编号必须为9位数字"}
```

### 9.3 远端 MCP 服务测试

#### 9.3.1 测试 tools/list（工具列表）

```bash
# 使用加密 Token
TOKEN="TOJvJYpY6XWz2NHZB1Nv60/py1Hdez4PEzt10FveHqzoVdKOPFCmYmfycPlY5CRrLwZvfiJ50WNsNQ7qhh5tjeMi6DxKnf7rD4hjtUBI6pxYVGfw2cyiibG2gsA0OfH8XIDLV5NIOgX4iw/sbh8zgbNruNFZy2osc9GZxfvyAg=="

curl -s -X POST http://localhost:8001/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}' | python3 -m json.tool
```

预期返回 4 个工具：
- `get_my_info`
- `get_my_department`
- `get_my_balance`
- `check_my_permission`

#### 9.3.2 测试 tools/call（工具调用）

```bash
# 测试 get_my_info
curl -s -X POST http://localhost:8001/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "get_my_info", "arguments": {}}, "id": 2}'
```

#### 9.3.3 测试认证失败

```bash
# 测试无效 Token（应返回认证失败）
curl -s -X POST http://localhost:8001/mcp \
  -H "Authorization: Bearer invalid-token" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 4}'
# 预期返回: {"error": "Token 格式错误"}

# 测试缺少 Token（应返回错误）
curl -s -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 5}'
# 预期返回: {"error": "缺少认证 Token"}
```

### 9.4 完整测试脚本

创建测试脚本 `prototype/test_services.sh`：

```bash
#!/bin/bash

echo "=========================================="
echo "MCP 服务测试"
echo "=========================================="

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

pass_count=0
fail_count=0

# 测试 Token（使用 generate_token.py 生成）
TOKEN="$MCP_AUTH_TOKEN"

# 测试函数
test_api() {
    local name="$1"
    local url="$2"
    local expected="$3"

    response=$(curl -s "$url" 2>&1)
    if echo "$response" | grep -q "$expected"; then
        echo -e "${GREEN}[PASS]${NC} $name"
        ((pass_count++))
    else
        echo -e "${RED}[FAIL]${NC} $name"
        echo "  响应: $response"
        ((fail_count++))
    fi
}

test_mcp() {
    local name="$1"
    local token="$2"
    local method="$3"
    local expected="$4"

    response=$(curl -s -X POST http://localhost:8001/mcp \
        -H "Authorization: Bearer $token" \
        -H "Content-Type: application/json" \
        -d "{\"jsonrpc\": \"2.0\", \"method\": \"$method\", \"id\": 1}" 2>&1)

    if echo "$response" | grep -q "$expected"; then
        echo -e "${GREEN}[PASS]${NC} $name"
        ((pass_count++))
    else
        echo -e "${RED}[FAIL]${NC} $name"
        echo "  响应: $response"
        ((fail_count++))
    fi
}

echo ""
echo "[后台 API 测试]"
test_api "健康检查" "http://localhost:8000/health" "ok"
test_api "用户查询 000000001" "http://localhost:8000/api/user/000000001" "张三"
test_api "用户查询 000000002" "http://localhost:8000/api/user/000000002" "李四"
test_api "不存在用户" "http://localhost:8000/api/user/999999999" "不存在"

echo ""
echo "[远端 MCP 服务测试]"
test_api "健康检查" "http://localhost:8001/health" "ok"
test_mcp "工具列表" "$TOKEN" "tools/list" "get_my_info"
test_mcp "调用工具" "$TOKEN" "tools/call" "张三"
test_mcp "无效Token" "invalid-token" "tools/list" "Token 格式错误"
test_mcp "缺少Token" "" "tools/list" "缺少认证 Token"

echo ""
echo "=========================================="
echo "结果: ${pass_count} 通过, ${fail_count} 失败"
echo "=========================================="

if [ $fail_count -eq 0 ]; then
    exit 0
else
    exit 1
fi
```

### 9.5 测试结果示例

```
==========================================
MCP 服务测试
==========================================

[后台 API 测试]
[PASS] 健康检查
[PASS] 用户查询 000000001
[PASS] 用户查询 000000002
[PASS] 不存在用户

[远端 MCP 服务测试]
[PASS] 健康检查
[PASS] 工具列表
[PASS] 调用工具
[PASS] 错误Token

==========================================
结果: 8 通过, 0 失败
==========================================
```

---

## 10. 参考文档

- [MCP 安全认证方案](mcp_security_authentication.md) - 完整的安全设计方案
- [MCP 官方文档](https://modelcontextprotocol.io/) - MCP 协议规范
- [Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk) - SDK 使用指南
