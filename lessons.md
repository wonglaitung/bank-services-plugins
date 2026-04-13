# 经验教训

记录开发过程中遇到的问题、解决方案和最佳实践。

---

## 格式规范

每个经验教训应包含：
- **日期**：发生时间
- **问题**：遇到的困难
- **原因**：问题根源
- **解决方案**：如何解决
- **预防措施**：如何避免再次发生

---

## 记录

### 1. 确认文件存在再移除引用
**日期**：2026-04-11

**问题**：因 `progress.txt` 和 `lessons.md` 文件不存在，错误地移除了 AGENTS.md 中对它们的引用。

**原因**：看到文件不存在就假设应该移除引用，未询问用户是否打算创建这些文件。

**解决方案**：询问用户后恢复引用并创建文件。

**预防措施**：移除文档引用前，应询问用户该文件是否需要创建，而非直接移除。

---

### 2. Skills 的 Windows 兼容性设计
**日期**：2026-04-11

**问题**：excel-auto-fill Skill 原本没有 Windows 支持，用户项目运行在 Windows 环境下。

**解决方案**：参考 anomaly-detector 的设计模式：
1. 创建 `scripts/` 目录存放命令行入口脚本
2. 创建 `.bat` 批处理脚本（使用 `%~dp0` 获取脚本目录）
3. 创建 `requirements.txt` 依赖文件
4. 更新 SKILL.md 添加完整的 Windows/Linux 使用说明

**设计模式**：
```
skill-name/
├── scripts/
│   └── skill_name.py      # 命令行入口脚本
├── skill_name.bat          # Windows 批处理脚本
├── requirements.txt        # 依赖文件
├── SKILL.md                # 文档
└── skill_module/           # Python 模块
```

**Windows 批处理模板**：
```batch
@echo off
REM Skill Name - Windows Batch Script
REM Description

python "%~dp0scripts\skill_name.py" %*
```

**预防措施**：新建 Skill 时，优先考虑跨平台兼容性，提供 Windows 批处理脚本和 Linux 脚本。

---

### 3. 敏感信息切勿提交到代码仓库
**日期**：2026-04-11

**问题**：AGENTS.md 中包含 GitHub Personal Access Token，推送到 GitHub 时被 Push Protection 拦截。

**原因**：将 token 硬编码在文档中，方便使用但忽略了安全风险。

**解决方案**：
1. 从文件中移除敏感 token
2. 使用 `git filter-branch` 重写所有历史提交：
   ```bash
   git filter-branch --force --tree-filter '
     if [ -f AGENTS.md ]; then
       sed -i "s/ghp_xxx/YOUR_GITHUB_TOKEN_HERE/g" AGENTS.md
     fi
   ' --prune-empty -- --all
   ```
3. 强制推送到远程仓库：`git push --force`

**正确做法**：
- Token 应存储在环境变量：`export GITHUB_TOKEN=xxx`
- 或使用 git credential helper：`git config credential.helper store`
- 文档中只写使用说明，不包含实际 token

**预防措施**：
1. 提交前检查是否包含敏感信息（API key、token、password 等）
2. 使用 `.gitignore` 排除敏感文件
3. 启用 GitHub Push Protection 自动检测
4. 如已泄露，立即 revoke token 并生成新的

---

### 4. 时间过滤边界条件处理
**日期**：2026-04-11

**问题**：Isolation Forest 设置 `lookback_days=0` 时，返回 0 个异常，即使数据中存在明显异常。

**原因**：时间过滤逻辑 `cutoff_date = utc_now - timedelta(days=lookback_days)` 在 `lookback_days=0` 时，`cutoff_date` 等于当前时间。所有历史数据的时间戳都小于当前时间，因此被过滤掉。

**解决方案**：
```python
# 错误写法
cutoff_date = utc_now - timedelta(days=lookback_days)

# 正确写法
cutoff_date = utc_now - timedelta(days=lookback_days) if lookback_days > 0 else None
```

**预防措施**：
- 时间过滤逻辑需考虑边界条件（0、负数、极大值）
- 编写单元测试覆盖边界情况
- 添加日志或警告提示用户当前行为

---

### 5. 不同方法的行为一致性
**日期**：2026-04-11

**问题**：Z-Score 默认检测全部数据，Isolation Forest 默认只检测最近 30 天，导致报告不一致（报告显示"2年数据"但实际只检测了 18-19 个最近数据点）。

**原因**：两种方法的默认参数设置不同，未考虑整体一致性。

**解决方案**：
- 统一默认行为：两种方法默认 `lookback_days=0`（检测全部数据）
- 明确区分使用场景：历史回测 vs 实时监控
- 在文档中清晰说明两种场景的参数设置

**预防措施**：
- 多方法工具需确保默认行为一致
- 设计时应考虑用户视角的直觉预期
- 报告内容应与实际检测范围一致

---

### 6. SKILL.md 文档结构最佳实践
**日期**：2026-04-11

**问题**：SKILL.md 文档结构混乱，存在重复章节、内容分散、用户难以快速上手。

**原因**：文档随功能增加逐步累积，缺乏整体规划。

**解决方案**：按用户使用顺序重新组织：

```
1. 何时使用此技能（快速判断是否适用）
2. 使用场景（历史回测/实时监控）
3. 核心能力 + 当前限制（了解能力边界）
4. 安装依赖（立即安装）
5. 检测方法（技术细节）
6. 使用流程（Windows/Linux + 参数说明）
7. 数据格式要求
8. 输出格式
9. 最佳实践
10. 常见问题
```

**关键改进**：
- 删除重复章节（安装依赖、核心能力、当前限制各出现 2 次）
- 精简冗长内容（lookback 参数说明减少 50%）
- 安装依赖提前到核心能力之后

**预防措施**：
- 文档按"用户使用流程"组织，而非"功能模块"
- 定期检查是否有重复或冗余内容
- 参考 excel-auto-fill 的文档结构模板

---

### 7. 跨平台路径格式问题
**日期**：2026-04-12

**问题**：系统注入的技能路径混合使用 Unix 风格 `~/` 和 Windows 风格 `\`，导致路径解析失败。

**示例**：
```
~/Documents\My Projects\AiAgentLab\skills\anomaly-detector\SKILL.md
```

**原因**：
- 系统在不同环境下运行（Windows WSL + Linux）
- 配置文件路径未进行统一规范化处理
- 路径拼接时未考虑平台差异

**解决方案**：使用 `pathlib` + 字符串替换混合方案：

```python
from pathlib import Path

def normalize_path(raw_path: str) -> str:
    # 使用 pathlib 解析路径
    path = Path(raw_path).expanduser()
    
    # 统一输出为正斜杠
    return str(path).replace('\\', '/')
```

**混合方案优势**：
- 存储时使用字符串替换保证格式统一
- 验证时使用 `pathlib` 确保路径有效
- 灵活应对不同场景

**预防措施**：
- 所有文件路径处理都应使用路径规范化
- 配置文件存储路径时统一使用正斜杠
- 添加单元测试覆盖跨平台路径场景

---

### 8. 命令行中文路径编码问题
**日期**：2026-04-13

**问题**：Windows CMD 传递中文路径参数时出现乱码，导致文件找不到错误。

**示例**：
```batch
REM 用户输入
python detect_anomaly.py "D:\测试\data.csv" --column 收市价

REM Python 接收到的路径（乱码）
"D:\æµ\x8bè¯\x95\data.csv"
```

**原因**：
- Windows CMD 默认使用系统编码（GBK/CP936）
- Python 3 使用 UTF-8 解码 `sys.argv`
- 编码不匹配导致中文字符变成乱码

**解决方案**：

1. **编码修复函数**（推荐）：
```python
def fix_chinese_path_encoding(raw_path: str) -> str:
    """修复命令行传递的中文路径编码问题"""
    if sys.platform != 'win32':
        return raw_path

    try:
        # UTF-8 编码 -> GBK 解码
        return raw_path.encode('utf-8').decode('gbk')
    except (UnicodeDecodeError, UnicodeEncodeError):
        return raw_path
```

2. **替代方案**（绕过命令行）：
   - 从配置文件读取路径
   - 从临时文件读取路径
   - 直接在 Python 代码中调用模块

**集成到 `normalize_path`**：
```python
def normalize_path(raw_path: str, fix_encoding: bool = True) -> str:
    # Step 1: Fix encoding issues
    if fix_encoding:
        raw_path = fix_chinese_path_encoding(raw_path)

    # Step 2: Use pathlib to parse path
    path = Path(raw_path).expanduser()
    # ... 后续处理
```

**预防措施**：
- Windows 环境下优先使用 ASCII 路径
- 或使用配置文件传递中文路径
- 所有 CLI 工具都应集成编码修复逻辑
