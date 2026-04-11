## Why

手动将信息填入 Excel 模版是一项繁琐且容易出错的工作。用户需要逐个识别模版中的字段位置，然后手动复制粘贴数据，这不仅效率低下，还存在数据错位、遗漏等风险。开发一个自动化 SKILL 可以智能匹配信息与模版字段，实现一键填充，大幅提升工作效率并减少人为错误。

## What Changes

- 新增 `excel-auto-fill` SKILL，实现信息到 Excel 模版的自动匹配与填充
- 支持多种信息输入格式（JSON、字典、键值对等）
- 实现智能字段匹配算法（精确匹配、模糊匹配、语义匹配）
- 支持自定义映射规则和映射配置文件
- 提供填充预览和手动调整功能
- 支持多种 Excel 格式（.xlsx、.xls、.xlsm）

## Capabilities

### New Capabilities
- `excel-template-matching`: 智能识别 Excel 模版结构，解析单元格位置、字段名称、数据类型等信息
- `field-mapping-engine`: 将用户提供的信息字段与模版字段进行智能匹配，支持精确匹配、模糊匹配和语义匹配
- `excel-auto-fill`: 将匹配后的数据自动填入 Excel 模版的准确位置，并输出填充后的文件

### Modified Capabilities
<!-- 无现有能力需要修改 -->

## Impact

- 新增 SKILL 文件：`.iflow/skills/excel-auto-fill/SKILL.md`
- 依赖 Python 库：`openpyxl`（Excel 操作）、`pandas`（数据处理）、`fuzzywuzzy`（模糊匹配）
- 影响范围：用户工作流自动化场景，不涉及现有系统 API
- 输出格式：填充后的 Excel 文件（保留原模版格式）
