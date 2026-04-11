# Bank Services Plugins - 项目上下文

> **  经验教训**：所有关键警告和最佳实践请参阅 [lessons.md](lessons.md)
> **🔧 编程规范**：规范化开发流程、系统设计决策、测试验证要求请遵守 [docs/programmer_skill.md](docs/programmer_skill.md)

## 项目概述

这是 iFlow CLI 的插件仓库，包含自定义 Skills 和 OpenSpec 工作流系统。项目用于管理和开发自动化工具，支持规范化的变更管理流程。

## 目录结构

```
/data/bank-services-plugins/
├── .iflow/
│   ├── commands/           # iFlow 自定义命令
│   └── skills/             # iFlow Skills 目录
│       ├── anomaly-detector/     # 时间序列异常检测 Skill
│       ├── excel-auto-fill/      # Excel 模版自动填充 Skill
│       └── openspec-*/           # OpenSpec 工作流 Skills
├── docs/
│   └── programmer_skill.md # 编程规范和开发流程文档
├── openspec/
│   ├── config.yaml         # OpenSpec 配置
│   ├── changes/            # 变更目录
│   │   └── archive/        # 已归档的变更
│   └── specs/              # 能力规范目录
└── AGENTS.md               # 本文件
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
| `/opsx:propose` | 创建新变更并生成所有 artifacts |
| `/opsx:apply` | 实现变更任务 |
| `/opsx:archive` | 归档已完成的变更 |
| `/opsx:explore` | 探索模式和需求分析 |

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
- Z-Score 方法
- Isolation Forest 方法
- 多种时间间隔（分钟、小时、天、周）
- CSV/Excel 数据文件

**位置**: `.iflow/skills/anomaly-detector/`

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

- GitHub Personal Access Token: `YOUR_GITHUB_TOKEN_HERE`
- 用于 git push 认证

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

