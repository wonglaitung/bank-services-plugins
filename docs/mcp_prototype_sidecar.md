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

### 1.3 Token 机制

采用 **Access Token + Refresh Token** 双 Token 机制：

| Token 类型 | 有效期 | 用途 | 存储 |
|------------|--------|------|------|
| **Access Token** | 15 分钟 | 调用 MCP API | 内存（自动刷新） |
| **Refresh Token** | 7 天（可配置） | 获取新 Access Token | `.mcp.json` 配置 |

**安全优势**：
- Access Token 有效期短，即使泄露风险有限
- Refresh Token 支持吊销，泄露后可立即止损
- 本地代理自动刷新，用户无感知

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
│  │                 │      │ │ • MCP_REFRESH│ │                              │
│  │                 │      │ │   _TOKEN    │ │                              │
│  │                 │      │ └─────────────┘ │                              │
│  │                 │      │                 │                              │
│  │                 │      │ ┌─────────────┐ │                              │
│  │                 │      │ │Token 刷新   │ │                              │
│  │                 │      │ │ • Access    │ │                              │
│  │                 │      │ │   Token缓存 │ │                              │
│  │                 │      │ │ • 自动刷新  │ │                              │
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
  1. 读取环境变量 MCP_REFRESH_TOKEN（Refresh Token）
  2. 调用远端 /auth/refresh 获取 Access Token
  3. 缓存 Access Token（有效期 15 分钟）
  4. Access Token 过期时自动刷新
  5. 在 HTTP Header 中添加:
     - Authorization: Bearer <Access Token>
  6. 通过 HTTPS 转发到远端服务
  7. 记录请求日志（可选）
输出: 远端服务的响应
```

#### 远端 MCP 服务

```
输入: 来自本地代理的 HTTPS 请求
处理:
  1. 从 Authorization Header 提取加密 Token
  2. AES-256-GCM 解密 Token
  3. 验证 Token 类型（必须是 Access Token）
  4. 验证有效期（expires_at）
  5. 提取 user_id，验证格式（必须为9位数字）
  6. 将用户编号存入上下文 (ContextVar)
  7. 解析 MCP JSON-RPC 请求
  8. 执行对应的 Tool
  9. Tool 从上下文获取用户编号，调用后台 API
  10. 记录审计日志
输出: Tool 执行结果
```

**新增端点**：

| 端点 | 用途 |
|------|------|
| `/auth/refresh` | 使用 Refresh Token 获取新 Access Token |
| `/auth/revoke` | 吊销 Refresh Token |

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

**关键变更**：新增 `/auth/refresh` 和 `/auth/revoke` 端点，支持 Token 刷新和吊销。

**`prototype/mcp_remote/main.py`**（核心部分）:

```python
"""
远端 MCP 服务

提供真正的 MCP 服务，定义所有 Tools。
从加密 Token 中解密获取用户编号，用于数据查询。

Token 机制：
- Access Token: 15 分钟有效期，用于 API 调用
- Refresh Token: 7 天有效期，用于获取新 Access Token
- Access Token 无需吊销（有效期短）
- Refresh Token 支持吊销
"""

# ... 导入和配置 ...

# Token 类型
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

# Access Token 有效期
ACCESS_TOKEN_EXPIRES_MINUTES = 15

# ==================== Token 刷新端点 ====================

@app.post("/auth/refresh")
async def refresh_token(request: Request):
    """
    使用 Refresh Token 获取新的 Access Token

    请求: {"refresh_token": "xxx"}
    响应: {"access_token": "yyy", "expires_in": 900}
    """
    data = await request.json()
    refresh_token = data.get("refresh_token")

    # 验证 Refresh Token
    token_data = decrypt_token(refresh_token)

    if token_data.get("token_type") != TOKEN_TYPE_REFRESH:
        raise HTTPException(401, "需要 Refresh Token")

    # 检查吊销黑名单
    if is_token_revoked(token_data["jti"]):
        raise HTTPException(401, "Token 已被吊销")

    # 生成新的 Access Token
    access_token = generate_access_token(token_data["user_id"])

    return {"access_token": access_token, "expires_in": 900}


@app.post("/auth/revoke")
async def revoke_token(request: Request):
    """吊销 Refresh Token"""
    data = await request.json()
    jti = data.get("jti")

    # 添加到黑名单
    add_to_revoked_list(jti)

    # 更新 Token 记录状态
    update_token_status(jti, "revoked")

    return {"status": "revoked"}


# ==================== Token 解密 ====================

def decrypt_token(token_b64: str) -> dict:
    """解密 Token，返回包含 user_id, token_type, jti, expires_at 的字典"""
    # AES-GCM 解密逻辑...
    return token_data


# ==================== MCP 端点验证 ====================

async def verify_request(request: Request) -> str:
    """验证请求，必须是 Access Token"""
    token_data = decrypt_token(access_token)

    # 验证 Token 类型
    if token_data.get("token_type") != TOKEN_TYPE_ACCESS:
        raise HTTPException(401, "需要 Access Token")

    return token_data["user_id"]
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

**关键变更**：新增 `TokenRefreshManager` 类，支持 Access Token 自动刷新。

**`prototype/local_proxy/main.py`**（核心部分）:

```python
"""
MCP 协议透传代理

关键特性：
- Tools 定义在远端服务，本地代理通过 HTTP 获取
- 用户身份封装在加密 Token 中，本地代理无法查看
- 使用 Refresh Token 自动获取 Access Token
- Access Token 过期时自动刷新
"""

# ... 导入 ...

# ==================== Token 刷新管理 ====================

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

    async def get_valid_access_token(self) -> str:
        """
        获取有效的 Access Token

        如果 Access Token 即将过期（< 1分钟），自动刷新。
        """
        # 传统模式：直接返回 MCP_AUTH_TOKEN
        if self.legacy_token and not self.refresh_token:
            return self.legacy_token

        now = datetime.now(timezone.utc)

        # 检查缓存的 Access Token 是否有效
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


# ==================== MCP 服务器实现 ====================

async def run_server():
    """运行 MCP 服务器"""
    remote_url = os.environ.get("REMOTE_MCP_URL", "http://localhost:8001")

    # 创建 Token 管理器
    token_manager = TokenRefreshManager(remote_url)

    # 创建 MCP Server 实例
    server = Server("finance-proxy")

    @server.list_tools()
    async def list_tools():
        """返回远端工具列表"""
        tools = await fetch_tools_from_remote(token_manager)
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """代理工具调用"""
        # 获取有效 Access Token（自动刷新）
        access_token = await token_manager.get_valid_access_token()

        # 调用远端服务...
        result = await call_tool_on_remote(name, arguments, token_manager)
        return [TextContent(type="text", text=result)]

    # ... 运行服务器 ...
```

**关键设计点**：

| 设计 | 说明 |
|------|------|
| **TokenRefreshManager** | 管理 Refresh Token，自动获取和刷新 Access Token |
| **Access Token 缓存** | 缓存 Access Token，过期前 1 分钟自动刷新 |
| **Server 实例** | 使用 `mcp.server.Server` 创建真正的 MCP 服务器 |
| **list_tools 处理器** | 从远端获取工具列表并转换为 `Tool` 对象 |
| **call_tool 处理器** | 转发工具调用到远端，返回 `TextContent` 结果 |
| **兼容旧配置** | 支持 `MCP_AUTH_TOKEN` 环境变量（传统模式） |

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
        "MCP_REFRESH_TOKEN": "<使用 prototype/tools/generate_token.py 生成>"
      }
    }
  }
}
```

**注意**：
- `args` 中的路径必须使用**绝对路径**
- `MCP_REFRESH_TOKEN` 使用 `prototype/tools/generate_token.py` 生成
- 用户身份封装在 Refresh Token 中，无需单独配置 `MCP_USER_ID`
- 兼容旧配置：可使用 `MCP_AUTH_TOKEN`（传统模式，无自动刷新）

### 6.2 启用 MCP 服务

配置完成后，重启 Claude Code，会提示是否启用 `finance-proxy` MCP 服务：

1. 选择 **Yes** 启用服务
2. Claude Code 会自动发现远端服务定义的所有工具

### 6.3 环境变量说明

| 变量名 | 说明 | 示例 | 必需 |
|--------|------|------|------|
| `REMOTE_MCP_URL` | 远端 MCP 服务地址 | `http://localhost:8001` | ✅ |
| `MCP_REFRESH_TOKEN` | Refresh Token（推荐） | 使用 `generate_token.py` 生成 | ✅ |
| `MCP_AUTH_TOKEN` | 传统 Token（兼容旧配置） | 使用 `generate_token.py` 生成 | ⚠️ |

### 6.4 远端服务配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `BACKEND_API_URL` | 后台 API 地址 | `http://localhost:8000` |
| `TOKEN_KEY` | AES-256 加密密钥（Base64） | 测试密钥 |

### 6.5 Token 生成

使用 `prototype/tools/generate_token.py` 生成 Access Token 和 Refresh Token：

```bash
# 生成密钥（首次使用）
python prototype/tools/generate_token.py --generate-key

# 生成 Token 对（Refresh Token 有效 7 天）
python prototype/tools/generate_token.py --user-id 000000001 --refresh-expires 7
# --refresh-expires 7 表示 Refresh Token 有效期为 7 天
# Access Token 固定 15 分钟有效期
```

**参数说明**：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--generate-key` | 生成新的 AES-256 密钥 | - |
| `--show-key` | 显示当前密钥（Base64） | - |
| `--user-id` | 用户编号（9位数字） | 必需 |
| `--refresh-expires` | Refresh Token 有效期（**天**） | 7 |

**Token 记录**：

生成的 Token 会记录到 `prototype/tools/token_records.json`：

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
python prototype/tools/generate_token.py --user-id 000000001 --refresh-expires 7
# 输出: MCP_REFRESH_TOKEN=xxx（Refresh Token）
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
│     ├── Access Token:                                            │
│     │   {                                                        │
│     │     "user_id": "000000001",                                │
│     │     "token_type": "access",                                │
│     │     "jti": "xyz789",                                       │
│     │     "expires_at": "2026-05-25T10:15:00Z", // +15 分钟      │
│     │     "issued_at": "2026-05-25T10:00:00Z"                    │
│     │   }                                                        │
│     │                                                            │
│     └── Refresh Token:                                           │
│         {                                                        │
│           "user_id": "000000001",                                │
│           "token_type": "refresh",                               │
│           "jti": "abc123",                                       │
│           "expires_at": "2026-06-01T10:00:00Z", // +7 天         │
│           "issued_at": "2026-05-25T10:00:00Z"                    │
│         }                                                        │
│                                                                 │
│  3. AES-256-GCM 加密                                            │
│     ├── 生成随机 nonce (12 bytes)                               │
│     ├── 使用密钥加密 JSON → ciphertext + tag                    │
│     └── 组装: nonce + ciphertext + tag                          │
│                                                                 │
│  4. Base64 编码                                                  │
│     └── 输出: MCP_REFRESH_TOKEN=xxx                             │
│                                                                 │
│  5. 记录 Token 信息                                              │
│     └── 保存到 token_records.json                               │
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
│  6. 验证 Token 类型                                              │
│     └── if token_type != "access": raise "需要 Access Token"    │
│                                                                 │
│  7. 验证有效期                                                   │
│     ├── expires_at = token_data["expires_at"]                   │
│     └── if now > expires_at: raise "Token 已过期"               │
│                                                                 │
│  8. 返回用户身份                                                  │
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
