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

### 1. 标准目录结构（必须遵守）

每个技能必须遵循以下结构：

```
skill-name/
├── SKILL.md                    # 技能文档（必需）
├── skill_name/                 # Python 模块目录（必需，与技能同名）
│   ├── __init__.py            # 包初始化
│   ├── core_module.py         # 核心功能模块
│   └── ...
├── scripts/                    # 命令行脚本目录（必需）
│   └── skill_name.py          # CLI 入口脚本
├── skill_name.bat              # Windows 批处理脚本（必需）
├── requirements.txt            # 依赖文件（必需）
└── tests/                      # 测试目录（推荐）
    ├── test_modules.py
    └── ...
```

**示例对比**：
```
anomaly-detector/               # ✅ 正确
├── SKILL.md
├── anomaly_detector/           # 模块在子目录
│   ├── __init__.py
│   ├── zscore_detector.py
│   └── ...
├── scripts/
│   └── detect_anomaly.py
├── detect_anomaly.bat
└── requirements.txt
```

### 2. Windows 兼容性（必须支持）

**批处理脚本模板** (`skill_name.bat`)：
```batch
@echo off
REM Skill Name - Windows Batch Script
REM Description

python "%~dp0scripts\skill_name.py" %*
```

**关键点**：
- 使用 `%~dp0` 获取脚本所在目录，支持任意安装路径
- 所有路径处理使用相对路径，避免硬编码
- 在 SKILL.md 中提供 Windows 和 Linux/macOS 两套使用说明

### 3. 模块导入规范

**模块内部使用相对导入**：
```python
# ✅ 正确：相对导入
from .auto_filler import AutoFiller
from .exceptions import ExcelAutoFillError

# ❌ 错误：绝对导入
from auto_filler import AutoFiller
```

**CLI 脚本导入模块**：
```python
# 添加技能目录到路径
SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# 从模块包导入
from skill_name.core_module import main_function
```

### 4. 文档规范

SKILL.md 必须包含：
- 操作系统检测说明（Windows/Linux/macOS）
- 两套使用说明（批处理脚本 + Python 脚本）
- 依赖安装命令（pip/pip3）
- 命令行参数说明
- 示例用法

### 5. 验证清单

开发新技能或修改现有技能时，必须验证：

- [ ] 目录结构符合标准
- [ ] 存在 Windows 批处理脚本 (`.bat`)
- [ ] 存在 `requirements.txt`
- [ ] 模块文件在子目录中，使用相对导入
- [ ] SKILL.md 包含跨平台使用说明
- [ ] 所有测试通过：`python3 -m pytest tests/`
- [ ] 语法检查通过：`python3 -m py_compile **/*.py`

## 开发规范

详见 `docs/programmer_skill.md`，核心原则：

### 1. 修改完即测试（最高优先级）
```bash
# 语法检查
python3 -m py_compile <文件路径>

# 运行测试
python3 -m pytest tests/
```

### 2. 需求分析优先
- 深入理解需求，不急于编码
- 识别核心目标和边界条件

### 3. 零重复代码原则
- 严禁复制粘贴相似代码
- 提取公共函数复用

### 4. 系统定位优先
- 系统定位 > 功能实现
- 差异化 > 一致性
- 目标用户决定功能

### 5. 避免硬编码路径
```python
# 推荐：基于脚本目录构建相对路径
import os
script_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(script_dir, 'data')
```

### 6. HTTP API 超时处理
- 必须设置合理的超时时间
- 实现备用方案

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

