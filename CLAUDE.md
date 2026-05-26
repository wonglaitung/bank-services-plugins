# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Bank Services Plugins 是一个 Claude Code 插件仓库，包含：
1. **自定义 Skills** - 用于自动化任务（Excel 处理、时间序列异常检测、文档转换等）
2. **MCP 安全认证原型** - Sidecar 模式的财务数据安全访问方案

**关键文档：**
- `lessons.md` - 开发过程中的关键警告和最佳实践
- `docs/programmer_skill.md` - 开发流程、测试要求和代码质量标准
- `docs/mcp_tool_description_best_practices.md` - MCP 工具描述编写规范

### 语言规范
- 所有的对话沟通、代码解释和文档注释必须使用 **简体中文**
- 技术术语在中文后用括号标注英文（例如：异步处理 (Asynchronous)）

### 代码风格
- 遵循 PEP8 规范
- 变量名和函数名使用英文，注释必须是中文

---

## Skills 开发

### 已实现的 Skills

| Skill | 用途 | 位置 |
|-------|------|------|
| anomaly-detector | 时间序列异常检测（Z-Score + Isolation Forest） | `.claude/skills/anomaly-detector/` |
| excel-auto-fill | Excel 模版自动填充 | `.claude/skills/excel-auto-fill/` |
| download-site | 网页下载转 Markdown | `.claude/skills/download-site/` |
| md-to-word | Markdown 转 Word | `.claude/skills/md-to-word/` |
| sync-prototype-design | 同步原型设计到安全方案文档 | `.claude/skills/sync-prototype-design/` |

### 开发命令

```bash
# 运行测试
python3 -m pytest .claude/skills/<skill-name>/tests/ -v

# 语法检查
python3 -m py_compile .claude/skills/<skill-name>/<module_name>/__init__.py

# 安装依赖
pip3 install -r .claude/skills/<skill-name>/requirements.txt
```

### Skills 目录结构

```
skill-name/
├── SKILL.md                    # 技能文档（必需）
├── skill_name/                 # Python 模块目录（必需）
│   ├── __init__.py
│   └── path_utils.py           # 路径规范化工具（必需）
├── scripts/skill_name.py       # CLI 入口脚本（必需）
├── skill_name.bat              # Windows 批处理脚本（必需）
├── requirements.txt            # 依赖文件（必需）
└── tests/                      # 测试目录（推荐）
```

### 跨平台兼容性要点

1. **Windows 批处理模板**：
   ```batch
   @echo off
   python "%~dp0scripts\skill_name.py" %*
   ```

2. **路径规范化**（每个 skill 必须包含 `path_utils.py`）：
   - 处理混合路径格式（Unix `~/` + Windows `\`）
   - 修复中文路径编码（Windows CMD GBK 编码问题）

3. **SKILL.md 需提供两套说明** - Windows 和 Linux/macOS

---

## MCP 安全认证原型

### 架构：Sidecar 模式

```
Claude Code ──Stdio──▶ 本地代理 ──HTTPS──▶ 远端 MCP 服务 ──▶ 后台 API
                          │                      │
                          │ MCP_REFRESH_TOKEN    │ 解密 Token
                          │ 自动刷新             │ 验证有效期
                          │ Access Token         │
```

**关键特性**：
- 用户身份封装在加密 Token 中，本地代理无法查看
- Access Token 15 分钟有效，自动刷新
- Refresh Token 7 天有效，支持吊销
- IDOR 防护：工具不接受 user_id 参数，身份从上下文获取

### 原型目录结构

```
prototype/
├── local_proxy/main.py      # 本地代理（MCP Server，Token 自动刷新）
├── mcp_remote/main.py       # 远端 MCP 服务（Token 解密验证）
├── backend_api/main.py      # 模拟后台 API（业务逻辑）
└── tools/generate_token.py  # Token 生成工具
```

### 启动服务

```bash
# 生成密钥和 Token
python prototype/tools/generate_token.py --generate-key
python prototype/tools/generate_token.py --show-key
python prototype/tools/generate_token.py --user-id 000000001 --refresh-expires 7

# 启动服务
TOKEN_KEY=<密钥> python prototype/backend_api/main.py &   # 端口 8000
TOKEN_KEY=<密钥> python prototype/mcp_remote/main.py &    # 端口 8001
```

### MCP 工具命名规范

| 前缀 | 用途 | 示例 |
|------|------|------|
| `get_my_` | 当前用户查询 | `get_my_balance`, `get_my_info` |
| `list_all_` | 管理员列表查询 | `list_all_users` |
| `query_` | 灵活条件查询 | `query_sales_data` |
| `describe_` | 元数据查询 | `describe_table` |

### 工具描述规范

遵循 `docs/mcp_tool_description_best_practices.md`，描述结构：
```
<一句话功能概述>
<触发场景说明>
<返回内容说明>
<安全/权限约束>
```

---

## 核心开发原则

| 原则 | 说明 |
|------|------|
| **修改完即测试** | 每次修改后立即运行 `py_compile` 和 `pytest` |
| **需求分析优先** | 编码前深入理解需求 |
| **零重复代码** | 提取公共函数，严禁复制粘贴 |
| **系统定位优先** | 系统定位 > 功能实现 |
| **HTTP API 超时** | 必须设置超时，实现备用方案 |

---

## Session 工作流程

**会话开始时：**
1. 读取 `progress.txt` 了解项目当前进展
2. 审查 `lessons.md` 检查已知问题和最佳实践

**功能更新后：**
1. 更新 `progress.txt` 记录新进展
2. 如有新的学习心得，更新 `lessons.md`

---

## 技术栈

- **Python 3.10+** - 主要开发语言
- **openpyxl** - Excel 文件处理
- **pandas** - 数据处理
- **FastAPI** - MCP 远端服务 HTTP 层
- **FastMCP** - MCP 协议处理
- **cryptography** - Token AES-256-GCM 加密
- **pytest** - 单元测试

---

## Git 安全提醒

- MCP_REFRESH_TOKEN 等敏感信息切勿提交
- 使用环境变量或 `.gitignore` 排除敏感文件
- `.mcp.json` 包含本地 Token，不应提交到仓库