# Bank Services Plugins - 项目上下文

> **📋 经验教训**：所有关键警告和最佳实践请参阅 [lessons.md](lessons.md)
> **🔧 编程规范**：规范化开发流程、系统设计决策、测试验证要求请遵守 [docs/programmer_skill.md](docs/programmer_skill.md)

## 项目概述

这是 iFlow CLI 的插件仓库，包含自定义 Skills 和 OpenSpec 工作流系统。项目用于管理和开发自动化工具，支持规范化的变更管理流程。

## 目录结构

```
/data/bank-services-plugins/
├── .iflow/
│   ├── commands/               # iFlow 自定义命令
│   │   ├── opsx-propose.md     # 创建新变更
│   │   ├── opsx-apply.md       # 实现变更任务
│   │   ├── opsx-archive.md     # 归档已完成变更
│   │   └── opsx-explore.md     # 探索模式和需求分析
│   └── skills/                 # iFlow Skills 目录
│       ├── anomaly-detector/   # 时间序列异常检测 Skill
│       ├── excel-auto-fill/    # Excel 模版自动填充 Skill
│       ├── openspec-propose/   # OpenSpec 提案 Skill
│       ├── openspec-apply-change/  # OpenSpec 实现 Skill
│       ├── openspec-archive-change/ # OpenSpec 归档 Skill
│       └── openspec-explore/   # OpenSpec 探索 Skill
├── docs/
│   └── programmer_skill.md     # 编程规范和开发流程文档
├── openspec/
│   ├── config.yaml             # OpenSpec 配置
│   ├── changes/                # 变更目录
│   │   └── archive/            # 已归档的变更
│   └── specs/                  # 能力规范目录
│       ├── excel-auto-fill/
│       ├── excel-template-matching/
│       └── field-mapping-engine/
└── AGENTS.md                   # 本文件
```

## OpenSpec 工作流

### Schema: spec-driven

项目使用 `spec-driven` schema，包含以下 artifacts：

| Artifact | 说明 |
|----------|------|
| `proposal.md` | 变更提案：Why + What |
| `design.md` | 技术设计：How |
| `specs/**/*.md` | 能力规范：需求定义 |
| `tasks.md` | 实现任务清单 |

### OpenSpec 命令

| 命令 | 说明 |
|------|------|
| `/opsx-propose` | 创建新变更并生成所有 artifacts |
| `/opsx-apply` | 实现变更任务 |
| `/opsx-archive` | 归档已完成的变更 |
| `/opsx-explore` | 探索模式和需求分析 |

## 已实现的 Skills

### 1. excel-auto-fill
Excel 模版自动填充工具，支持：
- `${fieldName}` 和 `{{fieldName}}` 标记解析
- 自动检测字段名（首行/首列）
- 智能字段匹配（精确/模糊/自定义映射）
- 样式保留（字体、边框、颜色）
- 多种输入格式（JSON、字典、键值对文本）

**位置**: `.iflow/skills/excel-auto-fill/`

### 2. anomaly-detector
时间序列异常检测工具，支持：
- Z-Score 方法（实时监控）
- Isolation Forest 方法（深度分析）
- 自动参数设置（根据时间间隔优化）
- 多种时间间隔（分钟、小时、天、周）
- CSV/Excel 数据文件支持
- 多维特征提取（RSI、MACD、波动率）

**位置**: `.iflow/skills/anomaly-detector/`

## 技能开发规范

> **⚠️ 重要**：所有技能必须遵循以下规范，确保代码质量和跨平台兼容性。
> 详细规范请参考 `docs/programmer_skill.md`

### 1. 标准目录结构（必须遵守）

```
skill-name/
├── SKILL.md                    # 技能文档（必需）
├── skill_name/                 # Python 模块目录（必需）
├── scripts/skill_name.py       # CLI 入口脚本（必需）
├── skill_name.bat              # Windows 批处理脚本（必需）
├── requirements.txt            # 依赖文件（必需）
└── tests/                      # 测试目录（推荐）
```

### 2. Windows 兼容性（必须支持）

```batch
@echo off
python "%~dp0scripts\skill_name.py" %*
```

- 使用 `%~dp0` 获取脚本目录
- SKILL.md 需提供 Windows/Linux 两套说明

### 3. 模块导入规范

```python
# ✅ 模块内部：相对导入
from .core_module import main_function

# ✅ CLI 脚本：添加路径后导入
SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))
from skill_name.core_module import main_function
```

### 4. SKILL.md 文档规范（必须遵守）

**必须包含的章节**：
- 操作系统检测说明
- 何时使用此技能
- **使用场景**（必需，见下方详细要求）
- 核心能力 + 当前限制
- 安装依赖
- 使用流程（Windows/Linux + 参数说明）

**使用场景章节要求**：
- 位置：在"何时使用此技能"之后、"核心能力"之前
- 内容：每个场景需包含名称、描述、示例命令、特点说明
- 参考：`.iflow/skills/anomaly-detector/SKILL.md`

### 5. 多算法行为一致性（必须遵守）

> **⚠️ 重要**：本项目服务于银行业务，涉及多种算法。当技能支持多种算法时，必须确保行为一致。

**核心原则**：
- **默认行为一致**：不同算法的默认参数应产生一致的用户预期
- **报告内容一致**：输出报告应反映实际处理范围，避免误导
- **参数语义一致**：相同参数名在不同算法中应有相同含义

**检查清单**：
- [ ] 所有算法的默认参数是否一致？
- [ ] 相同参数名是否有相同语义？
- [ ] 输出报告是否准确反映实际处理范围？
- [ ] 是否明确区分了不同使用场景？

### 6. 核心开发原则

| 原则 | 说明 |
|------|------|
| 修改完即测试 | 每次修改后立即 `python3 -m py_compile` 和 `pytest` |
| 需求分析优先 | 深入理解需求，不急于编码 |
| 零重复代码 | 严禁复制粘贴，提取公共函数 |
| 系统定位优先 | 系统定位 > 功能实现 |
| 避免硬编码路径 | 使用相对路径，配置外化 |
| HTTP API 超时 | 必须设置超时，实现备用方案 |

### 7. 验证清单

- [ ] 目录结构符合标准
- [ ] 存在 Windows 批处理脚本 (`.bat`)
- [ ] 存在 `requirements.txt`
- [ ] 模块使用相对导入
- [ ] SKILL.md 包含"使用场景"章节
- [ ] SKILL.md 包含跨平台使用说明
- [ ] 多算法行为一致
- [ ] 测试通过：`python3 -m pytest tests/`

## 技术栈

- **Python 3.10+**: 主要开发语言
- **openpyxl**: Excel 文件处理
- **pandas**: 数据处理
- **fuzzywuzzy**: 模糊字符串匹配
- **pytest**: 单元测试

## Git 配置

- 使用 GitHub Personal Access Token 进行认证
- Token 应存储在环境变量或 git credential helper 中
- **⚠️ 切勿将 token 提交到代码仓库**

## 已归档的变更

| 日期 | 变更名称 | 说明 |
|------|----------|------|
| 2026-04-11 | excel-auto-fill-skill | Excel 模版自动填充 Skill |

## 能力规范 (Specs)

当前已定义的能力规范：

- `excel-template-matching`: Excel 模版结构解析
- `field-mapping-engine`: 字段匹配引擎
- `excel-auto-fill`: 自动填充功能

## Session Workflow

**会话开始时必须执行**：
1. 读取 `progress.txt` 文件，了解项目当前进展
2. 审查 `lessons.md` 文件，检查是否有错误需要纠正

**功能更新后**：
1. 更新 `progress.txt`，记录新的进展
2. 如有新的学习心得，更新 `lessons.md`

