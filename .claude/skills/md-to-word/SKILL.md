---
name: md-to-word
description: "Convert Markdown files to Word documents (.docx) while preserving full formatting including headings, paragraphs, lists, code blocks, quotes, horizontal rules, and tables. Supports batch conversion and recursive directory processing."
license: MIT
---

# MD to Word Converter

将 Markdown 文件转换为 Word 文档，保留完整格式。

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

- **格式转换**：将 Markdown 文档转换为 Word 格式，供需要 .docx 文件的场景使用
- **批量处理**：一次性转换多个 Markdown 文件
- **报告生成**：为团队准备 Word 版本的技术报告或文档
- **内容归档**：将项目文档从 Markdown 归档为 Word 格式
- **客户交付**：向需要 Word 格式的客户或合作伙伴交付文档

## 配置使用

技能脚本位于技能目录中，使用时请替换 `\full\path\to` 为实际的安装路径。

**脚本路径：**

- **Linux/macOS：** `/full/path/to/skills/md-to-word/scripts/md_to_word.py`
- **Windows：** `\full\path\to\skills\md-to-word\md_to_word.bat`

**使用示例：**

```bash
# Linux/macOS
python3 /full/path/to/skills/md-to-word/scripts/md_to_word.py README.md

# Windows
\full\path\to\skills\md-to-word\md_to_word.bat README.md
```

**注意**：`\full\path\to` 为示例路径，请替换为实际的安装根路径。

## 安装依赖

技能需要以下 Python 包：

```bash
# Linux/macOS（使用 python3）
pip3 install -r /full/path/to/skills/md-to-word/requirements.txt

# Windows CMD（使用 python）
pip install -r \full\path\to\skills\md-to-word\requirements.txt

# 直接安装
pip install python-docx>=1.1.0
```

**依赖版本要求**：
- python-docx >= 1.1.0

## 核心能力

- **完整格式保留**：标题（H1-H6）、段落、列表、代码块、引用、水平线、表格
- **表格处理**：表头自动加粗，应用表格网格样式
- **批量操作**：支持通配符批量转换多个文件
- **递归处理**：递归搜索并转换子目录中的所有 Markdown 文件
- **灵活输出**：保持原文件名或自定义输出路径

## 当前限制

- 不支持嵌套列表（列表内套列表）
- 表格对齐格式（左/中/右）会被统一处理为默认样式
- 行内格式（粗体、斜体、代码）会保留 Markdown 标记，不会转换为 Word 格式

## 使用流程

### Windows 用户

使用批处理脚本直接运行，无需手动调用 Python 命令。

**批处理脚本位置：**
```
\full\path\to\skills\md-to-word\md_to_word.bat
```

**优势：**
- 自动调用 Python 解释器
- 自动传递所有参数
- 无需配置环境变量 PATH
- 可以直接双击运行（如果需要交互式输入）

**使用示例：**

```cmd
# 转换单个文件（自动使用原文件名 + .docx）
\full\path\to\skills\md-to-word\md_to_word.bat README.md

# 指定输出文件名
\full\path\to\skills\md-to-word\md_to_word.bat README.md --output README_word.docx

# 批量转换当前目录所有 Markdown 文件
\full\path\to\skills\md-to-word\md_to_word.bat *.md

# 批量转换指定目录
\full\path\to\skills\md-to-word\md_to_word.bat docs\*.md

# 递归处理子目录中的所有 Markdown 文件
\full\path\to\skills\md-to-word\md_to_word.bat . --recursive

# 查看完整帮助信息
\full\path\to\skills\md-to-word\md_to_word.bat --help
```

### Linux/macOS 用户

直接使用 Python 命令运行脚本。

```bash
# 转换单个文件（自动使用原文件名 + .docx）
python3 /full/path/to/skills/md-to-word/scripts/md_to_word.py README.md

# 指定输出文件名
python3 /full/path/to/skills/md-to-word/scripts/md_to_word.py README.md --output README_word.docx

# 批量转换当前目录所有 Markdown 文件
python3 /full/path/to/skills/md-to-word/scripts/md_to_word.py *.md

# 批量转换指定目录
python3 /full/path/to/skills/md-to-word/scripts/md_to_word.py docs/*.md

# 递归处理子目录中的所有 Markdown 文件
python3 /full/path/to/skills/md-to-word/scripts/md_to_word.py . --recursive

# 查看完整帮助信息
python3 /full/path/to/skills/md-to-word/scripts/md_to_word.py --help
```

### 命令行参数

| 参数 | 简写 | 必需 | 说明 |
|------|------|------|------|
| `input_files` | - | ✅ | 输入 Markdown 文件路径（支持通配符） |
| `--output` | `-o` | ❌ | 输出 Word 文件路径（仅限单个文件时使用） |
| `--recursive` | `-r` | ❌ | 递归处理子目录 |
| `--help` | `-h` | ❌ | 显示帮助信息 |

## 支持的 Markdown 元素

| 元素类别 | 语法示例 | 转换效果 |
|----------|----------|----------|
| **标题** | `# H1`, `## H2`, `### H3` | Word 标题样式（H1-H3 加粗，字号递减） |
| **段落** | 普通文本 | Word 段落，11pt 字号 |
| **无序列表** | `- 项目`, `* 项目` | Word 项目符号列表 |
| **有序列表** | `1. 项目`, `2. 项目` | Word 编号列表 |
| **代码块** | \`\`\`code\`\`\` | 代码块样式（Courier New 字体，9pt，缩进） |
| **引用** | `> 引用文本` | 斜体样式，左缩进 |
| **水平线** | `---`, `***`, `___` | 下划线分割线 |
| **表格** | `\| 列1 \| 列2 \|` | Word 表格，网格样式，表头加粗 |

## 最佳实践

### 1. 批量转换项目文档

当需要将整个项目的文档转换为 Word 格式时：

**Linux/macOS：**
```bash
# 转换所有 Markdown 文件
python3 /full/path/to/skills/md-to-word/scripts/md_to_word.py *.md

# 或递归处理所有子目录
python3 /full/path/to/skills/md-to-word/scripts/md_to_word.py . --recursive
```

**Windows：**
```cmd
# 转换所有 Markdown 文件
\full\path\to\skills\md-to-word\md_to_word.bat *.md

# 或递归处理所有子目录
\full\path\to\skills\md-to-word\md_to_word.bat . -r
```

### 2. 为重要文档指定明确名称

当转换最终交付的文档时，使用明确的输出名称：

**Linux/macOS：**
```bash
python3 /full/path/to/skills/md-to-word/scripts/md_to_word.py draft.md -o "Final Report v1.0.docx"
```

**Windows：**
```cmd
\full\path\to\skills\md-to-word\md_to_word.bat draft.md -o "Final Report v1.0.docx"
```

### 3. 验证转换结果

转换完成后，在 Word 中打开文件检查：

- 表格格式是否正确
- 代码块是否完整
- 列表缩进是否合适
- 标题层级是否清晰

## 常见问题

**Q: 转换后的表格格式不正确？**

A: 确保 Markdown 表格使用标准的 `|` 分隔符，并且每行列数一致。

**Q: 代码块格式丢失？**

A: 代码块会使用等宽字体显示，但不会保留语法高亮。

**Q: 如何转换包含图片的 Markdown 文件？**

A: 当前版本不支持图片转换，图片会被跳过。请手动添加图片到 Word 文档。

## 技术依赖

技能依赖的 Python 包已列在 `requirements.txt` 中：

- **python-docx** >= 1.1.0: Word 文档生成和操作库

**依赖文件位置**：
```
/full/path/to/skills/md-to-word/requirements.txt
```

## 脚本位置

**Python 脚本：**
```
/full/path/to/skills/md-to-word/scripts/md_to_word.py
```

**Windows 批处理脚本：**
```
\full\path\to\skills\md-to-word\md_to_word.bat
```

## 相关资源

- [python-docx 官方文档](https://python-docx.readthedocs.io/)
- [Markdown 语法完整指南](https://www.markdownguide.org/)
- [iFlow CLI 技能系统文档](https://platform.iflow.cn/cli/examples/skill)