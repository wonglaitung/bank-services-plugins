# Bank Services Plugins

Claude Code 插件仓库，包含自定义 Skills 用于自动化任务。

## 已实现的 Skills

### anomaly-detector - 时间序列异常检测

使用 Z-Score 和 Isolation Forest 方法检测时间序列数据中的异常点。

**特性：**
- 双检测方法：Z-Score（实时监控）+ Isolation Forest（深度分析）
- 多时间间隔：分钟、小时、天、周
- 自动参数优化
- 支持 CSV/Excel 数据文件

**使用示例：**
```bash
# 检测全部数据
python3 .claude/skills/anomaly-detector/scripts/detect_anomaly.py data.csv --column price

# 实时监控模式
python3 .claude/skills/anomaly-detector/scripts/detect_anomaly.py data.csv --column price --time-interval hour --lookback 1
```

### excel-auto-fill - Excel 模版自动填充

自动匹配数据字段并填充到 Excel 模版中。

**特性：**
- 多种标记格式：`${fieldName}` 和 `{{fieldName}}`
- 智能字段匹配：精确、模糊、自定义映射
- 自动检测字段位置（水平/垂直布局）
- 保留模版格式

**使用示例：**
```bash
# 使用 JSON 数据填充模版
python3 .claude/skills/excel-auto-fill/scripts/excel_auto_fill.py template.xlsx data.json

# 指定输出文件
python3 .claude/skills/excel-auto-fill/scripts/excel_auto_fill.py template.xlsx data.json -o output.xlsx
```

## 安装

### 依赖安装

```bash
# anomaly-detector
pip install pandas numpy scikit-learn openpyxl

# excel-auto-fill
pip install openpyxl pandas fuzzywuzzy python-Levenshtein PyYAML
```

### 按技能安装

```bash
pip install -r .claude/skills/anomaly-detector/requirements.txt
pip install -r .claude/skills/excel-auto-fill/requirements.txt
```

## 项目结构

```
bank-services-plugins/
├── .claude/
│   └── skills/
│       ├── anomaly-detector/       # 时间序列异常检测
│       └── excel-auto-fill/        # Excel 模版自动填充
├── docs/
│   ├── programmer_skill.md         # 开发规范
│   └── superpowers/specs/          # 设计文档
├── lessons.md                      # 经验教训
├── progress.txt                    # 项目进展
├── CLAUDE.md                       # Claude Code 指南
└── README.md                       # 本文件
```

## 开发

### 运行测试

```bash
python3 -m pytest .claude/skills/<skill-name>/tests/
```

### 语法检查

```bash
python3 -m py_compile .claude/skills/<skill-name>/<module_name>/__init__.py
```

## 技术栈

- Python 3.10+
- pandas / numpy
- scikit-learn
- openpyxl
- fuzzywuzzy

## 许可证

MIT License
