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
│  │                 │      │ │ • MCP_USER_ID│ │                              │
│  │                 │      │ │ • MCP_TOKEN  │ │                              │
│  │                 │      │ └─────────────┘ │                              │
│  │                 │      │                 │                              │
│  │                 │      │  职责:          │                              │
│  │  MCP 请求       │      │  • 透传协议     │                              │
│  │  (Stdio)        │      │  • 注入认证     │                              │
│  │  ───────────────────────▶ • 记录日志     │                              │
│  │                 │      │                 │                              │
│  │                 │      │        │        │                              │
│  │                 │      │        │ HTTPS  │                              │
│  │                 │      │        │ +Auth  │                              │
│  │                 │      │        ▼        │                              │
│  └─────────────────┘      └─────────┬───────┘                              │
│                                     │                                       │
└─────────────────────────────────────┼───────────────────────────────────────┘
                                      │
                                      │ HTTPS (加密通信)
                                      │ Authorization: Bearer <Token>
                                      │ X-User-ID: <用户编号>
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              公司服务器                                      │
│                                                                             │
│  ┌─────────────────┐      ┌─────────────────┐                              │
│  │  MCP 远端服务   │      │  后台 API       │                              │
│  │                 │      │                 │                              │
│  │  职责:          │      │  职责:          │                              │
│  │  • 定义 Tools   │      │  • 业务逻辑     │                              │
│  │  • 验证 Token   │      │  • 数据查询     │                              │
│  │  • 权限检查     │◀────▶│  • 数据库访问   │                              │
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
    │                        │  • X-User-ID         │
```

**关键设计**：
- 本地代理**透传** MCP JSON-RPC 协议，不解析业务内容
- Tools 定义在远端服务，Claude Code 可自动发现
- 本地代理在每个请求中自动注入 Token 和用户编号
- 修改/添加工具只需改远端服务，**无需改本地代理**

---

## 3. 组件职责

### 3.1 职责划分表

| 组件 | 职责 | 添加 Tools 时是否需要修改 |
|------|------|---------------------------|
| **本地代理** | • 从环境变量读取用户编号和 Token<br>• 透传 MCP JSON-RPC 协议<br>• 在每个请求中自动注入认证 Header<br>• 记录本地调用日志 | ❌ **无需修改** |
| **远端 MCP 服务** | • 定义所有 Tools<br>• 验证 Token 和用户编号格式<br>• 从 Header 获取用户编号用于查询<br>• 调用后台 API<br>• 记录审计日志 | ✅ **需要修改** |
| **后台 API** | • 提供业务数据查询接口<br>• 不感知用户身份（由远端服务控制） | 视业务需求 |

### 3.2 各组件详细职责

#### 本地代理层 (Local Proxy)

```
输入: Claude Code 的 MCP JSON-RPC 请求 (Stdio)
处理:
  1. 读取环境变量 MCP_USER_ID 和 MCP_AUTH_TOKEN
  2. 保持原始 MCP 请求不变
  3. 在 HTTP Header 中添加:
     - Authorization: Bearer <Token>
     - X-User-ID: <用户编号>
  4. 通过 HTTPS 转发到远端服务
  5. 记录请求日志（可选）
输出: 远端服务的响应
```

#### 远端 MCP 服务

```
输入: 来自本地代理的 HTTPS 请求
处理:
  1. 验证 Authorization Header 中的 Token
  2. 验证 X-User-ID 格式（必须为9位数字）
  3. 将用户编号存入上下文 (ContextVar)
  4. 解析 MCP JSON-RPC 请求
  5. 执行对应的 Tool
  6. Tool 从上下文获取用户编号，调用后台 API
  7. 记录审计日志
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
   │  - MCP_USER_ID = "000000001"
   │  - MCP_AUTH_TOKEN = "prototype-token"
   │
   │  构造 HTTP 请求:
   │  POST /mcp
   │  Headers:
   │    Authorization: Bearer prototype-token
   │    X-User-ID: 000000001
   │    Content-Type: application/json
   │  Body: (原始 MCP 请求)
   │
   ▼
3. 远端 MCP 服务接收 (HTTPS)
   │
   │  验证:
   │  - Token == "prototype-token" ✓
   │  - User-ID 是9位数字 ✓
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
从 HTTP Header 获取用户编号，用于数据查询。

关键安全原则：
- Tools 不接受 user_id 参数
- 用户编号从 Header 获取，由本地代理注入
- 所有数据查询强制使用当前用户编号
"""

import os
import logging
from datetime import datetime, timezone
from contextvars import ContextVar
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import httpx
from mcp.server.fastmcp import FastMCP

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
EXPECTED_TOKEN = os.environ.get("EXPECTED_TOKEN", "prototype-token")


# ==================== 认证中间件 ====================

async def verify_request(request: Request) -> str:
    """
    验证请求并返回用户编号
    
    从 HTTP Header 提取 Token 和用户编号，验证合法性。
    
    Returns:
        验证通过的用户编号
        
    Raises:
        HTTPException: 认证失败
    """
    # 提取 Header
    auth_header = request.headers.get("Authorization", "")
    user_id = request.headers.get("X-User-ID", "")
    
    # 验证 Token
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else auth_header
    if token != EXPECTED_TOKEN:
        logger.warning(f"Token 验证失败: {token[:10]}...")
        raise HTTPException(401, "Token 无效")
    
    # 验证用户编号格式（必须为9位数字）
    if not user_id or not user_id.isdigit() or len(user_id) != 9:
        logger.warning(f"用户编号格式错误: {user_id}")
        raise HTTPException(400, "用户编号必须为9位数字")
    
    logger.info(f"用户认证成功: {user_id}")
    return user_id


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
            "role": role,
            "permissions": {
                "can_view": True,
                "can_edit": role == "admin",
                "can_delete": role == "admin"
            }
        }


# ==================== MCP 请求端点 ====================

@app.post("/mcp")
async def handle_mcp_request(request: Request):
    """
    处理 MCP JSON-RPC 请求

    1. 验证认证信息
    2. 注入用户上下文
    3. 根据 method 调用对应的 MCP 方法
    """
    try:
        # 验证认证
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
                    "serverInfo": {"name": "FinanceService", "version": "1.0.0"}
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

**`prototype/mcp_remote/config.py`**:

```python
"""配置"""

import os

# 后台 API 地址
BACKEND_API_URL = os.environ.get("BACKEND_API_URL", "http://localhost:8000")

# 预期的 Token
EXPECTED_TOKEN = os.environ.get("EXPECTED_TOKEN", "prototype-token")

# 服务端口
PORT = int(os.environ.get("PORT", "8001"))
```

**`prototype/mcp_remote/requirements.txt`**:

```
fastapi>=0.100.0
uvicorn>=0.23.0
httpx>=0.25.0
mcp>=1.0.0
```

### 5.4 本地代理代码

**`prototype/local_proxy/main.py`**:

```python
"""
MCP 协议透传代理

本地代理作为 MCP JSON-RPC 协议的透明转发层：
- 接收 Claude Code 的 MCP 请求 (Stdio)
- 在每个请求中自动注入 Token 和用户编号
- 通过 HTTPS 转发到远端 MCP 服务
- 返回远端服务的响应

关键特性：
- Tools 定义在远端服务，本地代理不定义任何工具
- 添加/修改工具只需改远端服务，无需改本地代理
- 用户编号和 Token 从环境变量读取，模型无法修改
"""

import os
import sys
import json
import logging
import httpx
from mcp.server.fastmcp import FastMCP

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr  # 日志输出到 stderr，不影响 stdio 通信
)
logger = logging.getLogger(__name__)


def get_user_context() -> dict:
    """
    从环境变量获取用户上下文
    
    Returns:
        包含 user_id 和 token 的字典
        
    Raises:
        ValueError: 配置缺失
    """
    user_id = os.environ.get("MCP_USER_ID")
    token = os.environ.get("MCP_AUTH_TOKEN")
    remote_url = os.environ.get("REMOTE_MCP_URL", "http://localhost:8001")
    
    if not user_id:
        raise ValueError("未配置用户编号，请设置环境变量 MCP_USER_ID")
    if not token:
        raise ValueError("未配置认证令牌，请设置环境变量 MCP_AUTH_TOKEN")
    
    return {
        "user_id": user_id,
        "token": token,
        "remote_url": remote_url
    }


def validate_user_context(ctx: dict):
    """验证用户上下文格式"""
    user_id = ctx["user_id"]
    if not user_id.isdigit() or len(user_id) != 9:
        raise ValueError(f"用户编号格式错误，必须为9位数字: {user_id}")
    
    logger.info(f"用户上下文已加载: user_id={user_id}")


# 创建代理（不定义任何工具，纯转发）
mcp = FastMCP("MCPProxy")


# 注册请求处理钩子
@mcp.hook("before_request")
async def inject_and_forward(request: dict) -> dict:
    """
    拦截 MCP 请求，注入认证信息后转发到远端服务
    
    Args:
        request: MCP JSON-RPC 请求
        
    Returns:
        远端服务的响应
    """
    try:
        # 获取用户上下文
        ctx = get_user_context()
        
        # 记录请求日志
        method = request.get("method", "unknown")
        request_id = request.get("id", "?")
        logger.info(f"转发 MCP 请求: method={method}, id={request_id}")
        
        # 转发请求到远端，注入认证 Header
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ctx['remote_url']}/mcp",
                json=request,  # 透传原始 MCP 请求
                headers={
                    "Authorization": f"Bearer {ctx['token']}",
                    "X-User-ID": ctx["user_id"],
                    "Content-Type": "application/json"
                }
            )
            
            # 检查响应状态
            if response.status_code != 200:
                logger.error(f"远端服务错误: status={response.status_code}")
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": f"远端服务错误: {response.status_code}"},
                    "id": request_id
                }
            
            return response.json()
            
    except httpx.ConnectError as e:
        logger.error(f"无法连接远端服务: {e}")
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": "无法连接远端服务"},
            "id": request.get("id")
        }
    except Exception as e:
        logger.error(f"转发请求失败: {e}")
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": f"内部错误: {str(e)}"},
            "id": request.get("id")
        }


def main():
    """主入口"""
    try:
        # 验证配置
        ctx = get_user_context()
        validate_user_context(ctx)
        
        logger.info(f"MCP 代理启动，目标: {ctx['remote_url']}")
        
        # 使用 Stdio 协议运行
        mcp.run(transport="stdio")
        
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

# 用户编号（9位数字）
MCP_USER_ID = os.environ.get("MCP_USER_ID")

# 认证令牌
MCP_AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN")
```

**`prototype/local_proxy/requirements.txt`**:

```
mcp>=1.0.0
httpx>=0.25.0
```

---

## 6. 配置说明

### 6.1 Claude Code 配置

在 Claude Code 的 MCP 配置文件中添加：

```json
{
  "mcpServers": {
    "finance-proxy": {
      "command": "python",
      "args": ["/path/to/prototype/local_proxy/main.py"],
      "env": {
        "REMOTE_MCP_URL": "http://your-server:8001",
        "MCP_USER_ID": "000000001",
        "MCP_AUTH_TOKEN": "prototype-token"
      }
    }
  }
}
```

### 6.2 环境变量说明

| 变量名 | 说明 | 示例 | 必需 |
|--------|------|------|------|
| `REMOTE_MCP_URL` | 远端 MCP 服务地址 | `http://localhost:8001` | ✅ |
| `MCP_USER_ID` | 用户编号（9位数字） | `000000001` | ✅ |
| `MCP_AUTH_TOKEN` | 认证令牌 | `prototype-token` | ✅ |

### 6.3 远端服务配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `BACKEND_API_URL` | 后台 API 地址 | `http://localhost:8000` |
| `EXPECTED_TOKEN` | 预期的认证令牌 | `prototype-token` |
| `PORT` | 服务端口 | `8001` |

---

## 7. 验证步骤

### 7.1 启动服务

```bash
# 1. 启动后台 API (端口 8000)
cd prototype/backend_api
pip install -r requirements.txt
python main.py

# 2. 启动远端 MCP 服务 (端口 8001)
cd prototype/mcp_remote
pip install -r requirements.txt
python main.py

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
| Token 自动注入 | 查看本地代理日志 | 日志显示转发请求带有 Authorization Header |
| 远端 Token 验证 | 修改配置中的 Token 为错误值 | 返回 401 错误 |
| 用户编号格式验证 | 修改 MCP_USER_ID 为非9位数字 | 本地代理启动失败 |
| Tools 自动发现 | 在 Claude Code 中查看可用工具 | 显示远端服务定义的所有工具 |

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
curl -s -X POST http://localhost:8001/mcp \
  -H "Authorization: Bearer prototype-token" \
  -H "X-User-ID: 000000001" \
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
  -H "Authorization: Bearer prototype-token" \
  -H "X-User-ID: 000000001" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "get_my_info", "arguments": {}}, "id": 2}' | python3 -m json.tool

# 测试 get_my_balance（不同用户）
curl -s -X POST http://localhost:8001/mcp \
  -H "Authorization: Bearer prototype-token" \
  -H "X-User-ID: 000000002" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "get_my_balance", "arguments": {}}, "id": 3}' | python3 -m json.tool
```

#### 9.3.3 测试认证失败

```bash
# 测试错误 Token（应返回认证失败）
curl -s -X POST http://localhost:8001/mcp \
  -H "Authorization: Bearer wrong-token" \
  -H "X-User-ID: 000000001" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 4}'
# 预期返回: {"error": "Token 无效"}

# 测试格式错误的用户编号（应返回错误）
curl -s -X POST http://localhost:8001/mcp \
  -H "Authorization: Bearer prototype-token" \
  -H "X-User-ID: 123" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 5}'
# 预期返回: {"error": "用户编号必须为9位数字"}
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
NC='\033[0m' # No Color

pass_count=0
fail_count=0

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
    local user_id="$3"
    local method="$4"
    local expected="$5"

    response=$(curl -s -X POST http://localhost:8001/mcp \
        -H "Authorization: Bearer $token" \
        -H "X-User-ID: $user_id" \
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
test_mcp "工具列表" "prototype-token" "000000001" "tools/list" "get_my_info"
test_mcp "调用工具" "prototype-token" "000000001" "tools/call" "张三"
test_mcp "错误Token" "wrong-token" "000000001" "tools/list" "Token 无效"

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
