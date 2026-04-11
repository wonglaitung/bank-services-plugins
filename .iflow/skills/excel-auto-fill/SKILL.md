---
name: excel-auto-fill
description: "Automatically match and fill data into Excel templates. Supports multiple input formats (JSON, key-value text), matching strategies (exact, fuzzy, custom mapping), and preserves template formatting."
license: MIT
---

# Excel Auto Fill

Excel 模版自动填充工具，支持智能字段匹配和多种输入格式。

## 检查操作系统

在使用本技能前，请确认您的操作系统类型：

### Windows
- 打开 CMD 或 PowerShell
- 查看提示符是否为 `C:\>` 或 `PS C:\>`
- **使用方法**：查看下方"Windows 用户"部分

### Linux/macOS
- 打开终端
- Linux 提示符通常包含 `$` 或用户名@主机名
- macOS 提示符通常是 `MacBook-Username:~ username$`
- **使用方法**：查看下方"Linux/macOS 用户"部分

### 快速检测命令

**Windows CMD：**
```cmd
ver
```

**Linux/macOS：**
```bash
uname -a
```

## 何时使用此技能

当您需要以下任一场景时使用此技能：

- **报表填充**：将数据填充到 Excel 报表模版
- **表单生成**：批量生成格式化的 Excel 表单
- **数据转换**：将 JSON/字典数据转换为 Excel 文件
- **自动化办公**：减少重复的 Excel 数据录入工作

## 核心能力

- **多种标记格式**：`${fieldName}` 和 `{{fieldName}}`
- **自动字段检测**：首行/首列自动识别
- **智能匹配**：精确匹配、模糊匹配、自定义映射
- **格式保留**：字体、边框、颜色完整保留
- **多种输入格式**：JSON、字典、键值对文本

## 配置使用

技能脚本位于技能目录中，使用时请替换 `\full\path\to` 为实际的安装路径。

**脚本路径：**

- **Linux/macOS：** `/full/path/to/skills/excel-auto-fill/scripts/excel_auto_fill.py`
- **Windows：** `\full\path\to\skills\excel-auto-fill\excel_auto_fill.bat`

**使用示例：**

```bash
# Linux/macOS
python3 /full/path/to/skills/excel-auto-fill/scripts/excel_auto_fill.py template.xlsx data.json

# Windows
\full\path\to\skills\excel-auto-fill\excel_auto_fill.bat template.xlsx data.json
```

**注意**：`\full\path\to` 为示例路径，请替换为实际的安装根路径。

## 安装依赖

技能需要以下 Python 包：

```bash
# Linux/macOS（使用 python3）
pip3 install -r /full/path/to/skills/excel-auto-fill/requirements.txt

# Windows CMD（使用 python）
pip install -r \full\path\to\skills\excel-auto-fill\requirements.txt

# 直接安装
pip install openpyxl pandas fuzzywuzzy python-Levenshtein PyYAML
```

**依赖版本要求**：
- openpyxl >= 3.0.0
- pandas >= 1.3.0
- fuzzywuzzy >= 0.18.0
- python-Levenshtein >= 0.12.0（加速模糊匹配）
- PyYAML >= 5.4.0（自定义映射配置）

## 使用流程

### Windows 用户

使用批处理脚本直接运行，无需手动调用 Python 命令。

**批处理脚本位置：**
```
\full\path\to\skills\excel-auto-fill\excel_auto_fill.bat
```

**使用示例：**

```cmd
# 基本用法：使用 JSON 文件填充
\full\path\to\skills\excel-auto-fill\excel_auto_fill.bat template.xlsx data.json

# 使用 JSON 字符串填充
\full\path\to\skills\excel-auto-fill\excel_auto_fill.bat template.xlsx "{\"name\": \"John\", \"amount\": 1000}"

# 指定输出文件
\full\path\to\skills\excel-auto-fill\excel_auto_fill.bat template.xlsx data.json -o output.xlsx

# 使用键值对文本
\full\path\to\skills\excel-auto-fill\excel_auto_fill.bat template.xlsx -d "name: John\namount: 1000"

# 使用自定义映射
\full\path\to\skills\excel-auto-fill\excel_auto_fill.bat template.xlsx data.json -m mapping.yaml

# 覆盖已存在的输出文件
\full\path\to\skills\excel-auto-fill\excel_auto_fill.bat template.xlsx data.json --overwrite

# 查看帮助信息
\full\path\to\skills\excel-auto-fill\excel_auto_fill.bat --help
```

### Linux/macOS 用户

直接使用 Python 命令运行脚本。

```bash
# 基本用法：使用 JSON 文件填充
python3 /full/path/to/skills/excel-auto-fill/scripts/excel_auto_fill.py template.xlsx data.json

# 使用 JSON 字符串填充
python3 /full/path/to/skills/excel-auto-fill/scripts/excel_auto_fill.py template.xlsx '{"name": "John", "amount": 1000}'

# 指定输出文件
python3 /full/path/to/skills/excel-auto-fill/scripts/excel_auto_fill.py template.xlsx data.json -o output.xlsx

# 使用键值对文本
python3 /full/path/to/skills/excel-auto-fill/scripts/excel_auto_fill.py template.xlsx -d "name: John\namount: 1000"

# 使用自定义映射
python3 /full/path/to/skills/excel-auto-fill/scripts/excel_auto_fill.py template.xlsx data.json -m mapping.yaml

# 覆盖已存在的输出文件
python3 /full/path/to/skills/excel-auto-fill/scripts/excel_auto_fill.py template.xlsx data.json --overwrite

# 显示详细信息
python3 /full/path/to/skills/excel-auto-fill/scripts/excel_auto_fill.py template.xlsx data.json -v

# 查看帮助信息
python3 /full/path/to/skills/excel-auto-fill/scripts/excel_auto_fill.py --help
```

### 命令行参数

| 参数 | 简写 | 必需 | 说明 |
|------|------|------|------|
| `template` | - | ✅ | Excel 模版文件路径 |
| `data` | - | ❌ | 数据（JSON 字符串或文件路径） |
| `-d` | `--data-text` | ❌ | 键值对格式的数据文本 |
| `-o` | `--output` | ❌ | 输出文件路径（默认：template_filled.xlsx） |
| `-m` | `--mapping` | ❌ | 自定义映射配置文件（YAML/JSON） |
| `-t` | `--threshold` | ❌ | 模糊匹配阈值 0-100（默认：70） |
| `--no-preview` | - | ❌ | 跳过映射预览 |
| `--default` | - | ❌ | 缺失字段的默认值 |
| `--overwrite` | - | ❌ | 覆盖已存在的输出文件 |
| `-v` | `--verbose` | - | ❌ | 显示详细信息 |
| `--help` | `-h` | ❌ | 显示帮助信息 |

## 数据格式要求

### JSON 文件格式

```json
{
  "customer_name": "John Doe",
  "order_date": "2024-01-15",
  "amount": 1500.00
}
```

### 键值对文本格式

```
customer_name: John Doe
order_date: 2024-01-15
amount: 1500.00
```

### Python 字典

```python
{
    "customer_name": "John Doe",
    "order_date": "2024-01-15",
    "amount": 1500.00
}
```

## 模版标记格式

技能识别以下字段标记：

- `${fieldName}` - 标准标记
- `{{fieldName}}` - Jinja 风格标记

如果模版中没有标记，技能会自动从以下位置检测字段名：
- 首行（水平布局）
- 首列（垂直布局）

## 自定义映射配置

创建 YAML 或 JSON 文件指定显式字段映射：

**YAML 格式：**
```yaml
mappings:
  input_field_name: template_field_name
  cust_name: customer_name
  order_dt: order_date
```

**JSON 格式：**
```json
{
  "mappings": {
    "input_field_name": "template_field_name",
    "cust_name": "customer_name",
    "order_dt": "order_date"
  }
}
```

## 匹配策略

### 1. 精确匹配
不区分大小写的精确字符串比较。

### 2. 模糊匹配
处理拼写错误、缩写、变体形式（阈值可配置）。

### 3. 自定义映射
显式用户定义的映射（最高优先级）。

## 输出格式

```
==================================================
填充成功!
==================================================
输出文件: /path/to/template_filled.xlsx

统计信息:
  - 已填充字段: 5
  - 已填充单元格: 8
  - 匹配字段: 5
```

## 最佳实践

### 1. 使用 JSON 文件管理数据
```bash
# 将数据保存为 JSON 文件，便于管理和复用
python3 excel_auto_fill.py template.xlsx data.json
```

### 2. 使用自定义映射处理字段名差异
```bash
# 当数据字段名与模版字段名不一致时
python3 excel_auto_fill.py template.xlsx data.json -m mapping.yaml
```

### 3. 调整模糊匹配阈值
```bash
# 更严格的匹配（减少误匹配）
python3 excel_auto_fill.py template.xlsx data.json -t 90

# 更宽松的匹配（处理更多变体）
python3 excel_auto_fill.py template.xlsx data.json -t 50
```

### 4. 批量处理
```bash
# 使用 shell 循环批量处理多个文件
for data in data/*.json; do
    python3 excel_auto_fill.py template.xlsx "$data" -o "output/$(basename $data .json)_filled.xlsx"
done
```

## 常见问题

**Q: 提示"未找到匹配字段"？**

A: 检查数据字段名是否与模版中的标记或首行/首列一致。可以使用自定义映射配置。

**Q: 如何处理缺失字段？**

A: 使用 `--default` 参数设置默认值，或确保数据包含所有必要字段。

**Q: 输出文件已存在怎么办？**

A: 使用 `--overwrite` 参数覆盖已存在的文件，或指定不同的输出路径。

**Q: 如何查看匹配详情？**

A: 使用 `-v` 参数显示详细信息，包括匹配的字段列表。

## 技术依赖

技能依赖的 Python 包已列在 `requirements.txt` 中：

- **openpyxl** >= 3.0.0: Excel 文件读写
- **pandas** >= 1.3.0: 数据处理
- **fuzzywuzzy** >= 0.18.0: 模糊字符串匹配
- **python-Levenshtein** >= 0.12.0: 加速模糊匹配（可选）
- **PyYAML** >= 5.4.0: YAML 配置文件解析

**依赖文件位置**：
```
/full/path/to/skills/excel-auto-fill/requirements.txt
```

## 脚本位置

**Python 脚本：**
```
/full/path/to/skills/excel-auto-fill/scripts/excel_auto_fill.py
```

**Windows 批处理脚本：**
```
\full\path\to\skills\excel-auto-fill\excel_auto_fill.bat
```

## 相关资源

- [openpyxl 文档](https://openpyxl.readthedocs.io/)
- [fuzzywuzzy 文档](https://github.com/seatgeek/fuzzywuzzy)
- [iFlow CLI 技能系统文档](https://platform.iflow.cn/cli/examples/skill)