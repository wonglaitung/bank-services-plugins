---
name: download-site
description: 下载网页及其子页面，转换为 Markdown 格式
userInvocable: true
---

# 页面下载器

下载指定网页及其子页面，将内容转换为 Markdown 格式保存。

## 用法

### Linux / macOS

```bash
/download-site <URL> [--depth N] [--output DIR] [--domain-only]
```

### Windows

```cmd
/download-site <URL> [--depth N] [--output DIR] [--domain-only]
```

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `URL` | 要下载的页面地址（必需） | - |
| `--depth N` | 递归深度 | 1 |
| `--output DIR` | 输出目录 | ./downloaded/ |
| `--domain-only` | 只下载同域名页面 | 关闭 |

## 功能特性

- 递归下载子页面（可配置深度）
- HTML 自动转换为 Markdown 格式
- 链接本地化，支持离线阅读
- 支持限制只下载同域名页面
- 自动处理相对 URL 和绝对 URL
- 智能文件命名，避免冲突
- 自动清理导航栏、页脚等噪音内容

## 示例

### 下载单页

```
/download-site https://example.com/article
```

### 递归下载 2 层

```
/download-site https://docs.python.org/3/ --depth 2
```

### 只下载同域名，保存到指定目录

```
/download-site https://vuejs.org/guide/ --depth 3 --domain-only --output ./vue-docs/
```

## 执行步骤

当用户调用此技能时，执行以下操作：

1. 检查依赖：确保已安装 requests、beautifulsoup4、html2text
2. 创建输出目录
3. 执行下载脚本：
   - Linux/macOS: `python3 .claude/skills/download-site/scripts/download_site.py "<URL>" --depth N --output "<DIR>" [--domain-only]`
   - Windows: `download_site.bat "<URL>" --depth N --output "<DIR>" [--domain-only]`
4. 报告下载结果，包括下载的页面数量和保存位置
