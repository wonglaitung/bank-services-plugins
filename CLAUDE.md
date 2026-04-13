# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Bank Services Plugins 是一个 Claude Code 插件仓库，包含自定义 Skills 用于自动化任务。项目专注于 Excel 处理和时间序列分析。

**关键文档：**
- [lessons.md](lessons.md) - 开发过程中的关键警告和最佳实践
- [docs/programmer_skill.md](docs/programmer_skill.md) - 开发流程、测试要求和代码质量标准

### 语言规范
- 所有的对话沟通、代码解释和文档注释必须使用 **简体中文**。
- 如果输出包含技术术语，建议在中文后用括号标注英文（例如：异步处理 (Asynchronous)）。

### 代码风格
- 遵循 PEP8 规范。
- 变量名和函数名必须使用英文，但注释必须是中文。

## 已实现的 Skills

### anomaly-detector
时间序列异常检测工具，使用 Z-Score 和 Isolation Forest 方法。支持多种时间间隔（分钟、小时、天、周），适用于 CSV/Excel 数据文件。

**位置：** `.claude/skills/anomaly-detector/`

### excel-auto-fill
Excel 模版自动填充工具，支持多种输入格式（JSON、键值对文本）、匹配策略（精确、模糊、自定义映射），保留模版格式。

**位置：** `.claude/skills/excel-auto-fill/`

## 开发命令

```bash
# 运行测试
python3 -m pytest .claude/skills/<skill-name>/tests/ -v

# 语法检查
python3 -m py_compile .claude/skills/<skill-name>/<module_name>/__init__.py

# 安装依赖
pip3 install -r .claude/skills/<skill-name>/requirements.txt
```

## Skills 开发规范

### 标准目录结构

```
skill-name/
├── SKILL.md                    # 技能文档（必需）
├── skill_name/                 # Python 模块目录（必需）
│   ├── __init__.py
│   ├── path_utils.py           # 路径规范化工具
│   └── ...                     # 其他模块
├── scripts/skill_name.py       # CLI 入口脚本（必需）
├── skill_name.bat              # Windows 批处理脚本（必需）
├── requirements.txt            # 依赖文件（必需）
└── tests/                      # 测试目录（推荐）
```

### 跨平台兼容性

Skills 必须同时支持 Windows 和 Linux/macOS：

1. **Windows 批处理脚本模板：**
   ```batch
   @echo off
   python "%~dp0scripts\skill_name.py" %*
   ```

2. **使用 `%~dp0` 获取脚本目录** - 确保路径在任何工作目录下都能正常工作

3. **SKILL.md 需提供两套说明** - 分别提供 Windows 和 Linux/macOS 的使用示例

### 模块导入规范

```python
# 模块内部：使用相对导入
from .core_module import main_function

# CLI 脚本：添加路径后导入
SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))
from skill_name.core_module import main_function
```

### 路径规范化（重要）

每个 skill 必须包含 `path_utils.py`，处理：

1. **混合路径格式**：Unix `~/` + Windows `\`
2. **中文路径编码**（Windows CMD 环境下）

```python
from skill_name.path_utils import normalize_path

# 自动处理：波浪号扩展、反斜杠转换、中文编码修复
normalized = normalize_path("D:\\测试\\data.csv")
# 结果: "D:/测试/data.csv"（编码已修复）
```

**中文路径编码修复原理**：
- Windows CMD 使用 GBK 编码传递参数
- Python 3 使用 UTF-8 解码 `sys.argv`
- `normalize_path()` 自动执行 `encode('utf-8').decode('gbk')` 修复乱码

### 多算法行为一致性

当 skill 支持多种算法时，必须确保：
- **默认行为一致**：不同算法的默认参数应产生一致的用户预期
- **报告内容一致**：输出报告应反映实际处理范围
- **参数语义一致**：相同参数名在不同算法中应有相同含义

## 核心开发原则

| 原则 | 说明 |
|------|------|
| 修改完即测试 | 每次修改后立即运行 `python3 -m py_compile` 和 `pytest` |
| 需求分析优先 | 编码前深入理解需求 |
| 零重复代码 | 提取公共函数，严禁复制粘贴 |
| 系统定位优先 | 系统定位 > 功能实现 |
| HTTP API 超时 | 必须设置超时，实现备用方案 |

## Session 工作流程

**会话开始时：**
1. 读取 `progress.txt` 了解项目当前进展
2. 审查 `lessons.md` 检查已知问题和最佳实践

**功能更新后：**
1. 更新 `progress.txt` 记录新进展
2. 如有新的学习心得，更新 `lessons.md`

## 技术栈

- **Python 3.10+** - 主要开发语言
- **openpyxl** - Excel 文件处理
- **pandas** - 数据处理
- **fuzzywuzzy** - 模糊字符串匹配
- **pytest** - 单元测试

## Git 配置

- 使用 GitHub Personal Access Token 进行认证
- Token 应存储在环境变量或 git credential helper 中
- **切勿将 token 提交到代码仓库**
