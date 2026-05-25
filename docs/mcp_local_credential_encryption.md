# 本地 Refresh Token 加密方案

## 背景

当前 `MCP_REFRESH_TOKEN` 以明文形式存储在 `.mcp.json` 配置文件中，存在以下风险：
- 配置文件泄露后 Token 可直接使用
- 无法防止未授权人员使用已配置的 MCP 服务

**需求**：对本地存储的 Refresh Token 进行加密保护，只有知道密码的用户才能使用。

---

## 方案设计

### 核心思路

1. **用户自己设置密码** - 用户运行加密工具时设置密码
2. **密码不存储在任何文件中** - 每次启动前手动设置环境变量
3. **环境变量提供密码** - `MCP_CREDENTIAL_PASSWORD`

### 整体流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                          服务器端                                    │
│                                                                     │
│  1. 生成 Refresh Token                                              │
│     python generate_token.py --user-id 000000001                    │
│     输出: MCP_REFRESH_TOKEN=xxx                                     │
│                                                                     │
│  2. 手工分发 Refresh Token 给用户                                    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          用户本地                                    │
│                                                                     │
│  步骤 1: 用户创建加密凭证文件                                        │
│  $ python prototype/tools/encrypt_credential.py                     │
│  请输入 Refresh Token: <粘贴 Token>                                 │
│  请设置凭证密码: ****                                                │
│  请确认密码: ****                                                    │
│  凭证文件已保存到: ~/.mcp/credential.enc                             │
│                                                                     │
│  步骤 2: 配置 .mcp.json                                             │
│  {                                                                  │
│    "mcpServers": {                                                  │
│      "finance-proxy": {                                             │
│        "env": {                                                     │
│          "MCP_CREDENTIAL_FILE": "~/.mcp/credential.enc"             │
│        }                                                            │
│      }                                                              │
│    }                                                                │
│  }                                                                  │
│                                                                     │
│  步骤 3: 每次启动前设置密码环境变量                                  │
│  $ export MCP_CREDENTIAL_PASSWORD="用户设置的密码"                   │
│  $ claude                                                           │
│                                                                     │
│  步骤 4: 本地代理启动                                                │
│  1. 检测到 MCP_CREDENTIAL_FILE 环境变量                             │
│  2. 检测到 MCP_CREDENTIAL_PASSWORD 环境变量                         │
│  3. 自动解密凭证文件                                                │
│  4. 获取 Refresh Token                                              │
│  5. 继续正常流程...                                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 加密凭证文件结构

```
┌─────────────────────────────────────────────────────────────────┐
│  凭证文件 (credential.enc)                                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  【AES-256-GCM 加密】                                            │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Header:                                                   │  │
│  │  - salt (16 bytes): 密钥派生盐值                           │  │
│  │  - nonce (12 bytes): GCM 随机数                            │  │
│  │                                                            │  │
│  │  Ciphertext:                                               │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │  {                                                   │  │  │
│  │  │    "refresh_token": "<Refresh Token>",              │  │  │
│  │  │    "user_id": "000000001",                          │  │  │
│  │  │    "issued_at": "2026-05-25T10:00:00Z",             │  │  │
│  │  │    "version": 1                                      │  │  │
│  │  │  }                                                   │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 环境变量说明

| 变量名 | 说明 | 存储位置 | 安全级别 |
|--------|------|----------|----------|
| `MCP_CREDENTIAL_FILE` | 加密凭证文件路径 | `.mcp.json` 配置文件 | 低（文件本身加密） |
| `MCP_CREDENTIAL_PASSWORD` | 解密密码 | shell 环境变量（每次手动设置） | 高（不落盘） |
| `MCP_REFRESH_TOKEN` | 明文 Token（兼容旧配置） | `.mcp.json` 配置文件 | 低 |

---

## 关键文件

### 1. 加密工具

**文件**：`prototype/tools/encrypt_credential.py`

用户运行此工具创建加密凭证文件：

```bash
$ python encrypt_credential.py
请输入 Refresh Token: <粘贴>
请设置凭证密码: ****
请确认密码: ****
凭证文件已保存到: ~/.mcp/credential.enc
```

### 2. 本地代理修改

**文件**：`prototype/local_proxy/main.py`

修改 `TokenRefreshManager` 类：

```python
class TokenRefreshManager:
    def __init__(self, remote_url: str):
        self.remote_url = remote_url
        self.refresh_token = None

        # 优先级：明文环境变量 > 加密凭证文件
        self.refresh_token = os.environ.get("MCP_REFRESH_TOKEN")

        if not self.refresh_token:
            credential_file = os.environ.get("MCP_CREDENTIAL_FILE")
            password = os.environ.get("MCP_CREDENTIAL_PASSWORD")

            if credential_file and password:
                self.refresh_token = self._decrypt_credential(credential_file, password)
            elif credential_file:
                raise ValueError(
                    "已配置加密凭证文件，但未提供密码。\n"
                    "请在启动前设置环境变量:\n"
                    "  export MCP_CREDENTIAL_PASSWORD='你的密码'"
                )

        if not self.refresh_token:
            raise ValueError(
                "未配置认证令牌，请设置:\n"
                "  MCP_REFRESH_TOKEN (明文 Token)\n"
                "  或 MCP_CREDENTIAL_FILE + MCP_CREDENTIAL_PASSWORD (加密凭证)"
            )

    def _decrypt_credential(self, filepath: str, password: str) -> str:
        """解密凭证文件"""
        from pathlib import Path
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes

        filepath = Path(filepath).expanduser()
        if not filepath.exists():
            raise ValueError(f"凭证文件不存在: {filepath}")

        with open(filepath, 'rb') as f:
            encrypted_data = f.read()

        if len(encrypted_data) < 28:
            raise ValueError("凭证文件格式错误")

        # 解析
        salt = encrypted_data[:16]
        nonce = encrypted_data[16:28]
        ciphertext = encrypted_data[28:]

        # 派生密钥
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = kdf.derive(password.encode('utf-8'))

        # 解密
        aesgcm = AESGCM(key)
        try:
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            credential = json.loads(plaintext.decode('utf-8'))
            logger.info(f"凭证解密成功，用户: {credential.get('user_id')}")
            return credential.get("refresh_token")
        except Exception:
            raise ValueError("密码错误或凭证文件已损坏")
```

---

## 使用方式

### 日常启动流程

```bash
# 1. 设置密码环境变量
export MCP_CREDENTIAL_PASSWORD="用户设置的密码"

# 2. 启动 Claude Code
claude
```

### 可选：使用启动脚本简化

用户可创建启动脚本 `start_claude.sh`：

```bash
#!/bin/bash
# 提示输入密码
read -s -p "请输入凭证密码: " MCP_CREDENTIAL_PASSWORD
export MCP_CREDENTIAL_PASSWORD
echo ""

# 启动 Claude Code
claude
```

---

## 配置对比

| 方式 | .mcp.json 配置 | 启动前操作 | 安全级别 |
|------|----------------|------------|----------|
| 明文 Token | `MCP_REFRESH_TOKEN` | 无 | 低（Token 明文） |
| 加密凭证 | `MCP_CREDENTIAL_FILE` + `export MCP_CREDENTIAL_PASSWORD` | 设置密码环境变量 | 高（密码不落盘） |

---

## 实施步骤

| 步骤 | 文件 | 说明 |
|------|------|------|
| 1 | `prototype/tools/encrypt_credential.py` | 新增加密工具 |
| 2 | `prototype/local_proxy/main.py` | 修改 TokenRefreshManager |
| 3 | `prototype/README.md` | 更新使用说明 |

---

## 验证方案

| 验证项 | 测试方法 | 预期结果 |
|--------|----------|----------|
| 创建凭证 | `encrypt_credential.py` | 生成 credential.enc |
| 解密成功 | 设置正确密码环境变量 | 本地代理正常启动 |
| 密码错误 | 设置错误密码 | 报错 "密码错误" |
| 缺少密码 | 只配置文件，不设置密码 | 提示设置环境变量 |

---

## 安全特性

| 特性 | 说明 |
|------|------|
| **用户自己设置密码** | 管理员不知道密码 |
| **密码不落盘** | 每次手动设置环境变量，不存储在文件 |
| **PBKDF2 密钥派生** | 100000 次迭代，增加暴力破解难度 |
| **AES-256-GCM** | 认证加密，防止篡改 |
| **凭证文件泄露安全** | 没有密码无法解密 |
| **兼容现有配置** | 仍支持 MCP_REFRESH_TOKEN 环境变量 |

---

## 状态

**状态**: 暂不实施，方案记录备查。

**原因**: 当前安全需求下，明文 Token + 双 Token 机制已足够。后续如有更高安全需求可实施此方案。