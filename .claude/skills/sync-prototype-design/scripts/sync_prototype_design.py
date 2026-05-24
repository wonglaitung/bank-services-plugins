#!/usr/bin/env python3
"""
同步原型设计到安全方案文档

对比 mcp_prototype_sidecar.md 和 mcp_security_authentication.md，
识别需要同步的内容，生成同步报告。
"""

import os
import sys
import re
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple


# 项目根目录 (脚本在 .claude/skills/sync-prototype-design/scripts/ 下)
# 需要向上 4 级目录到达项目根目录
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent.parent

# 文档路径
PROTOTYPE_DOC = PROJECT_ROOT / "docs" / "mcp_prototype_sidecar.md"
SECURITY_DOC = PROJECT_ROOT / "docs" / "mcp_security_authentication.md"


@dataclass
class SyncItem:
    """同步检查项"""
    name: str
    prototype_section: str
    security_section: str
    status: str  # 'synced', 'pending', 'missing'
    suggestion: str = ""


# 同步检查清单
SYNC_CHECKLIST: List[SyncItem] = [
    SyncItem(
        name="Sidecar 架构模式",
        prototype_section="第 2 节",
        security_section="第 4-5 节",
        status="synced"
    ),
    SyncItem(
        name="MCP 协议透传原理",
        prototype_section="第 3 节",
        security_section="第 8 节",
        status="synced"
    ),
    SyncItem(
        name="身份注入机制",
        prototype_section="第 4 节",
        security_section="第 8-9 节",
        status="synced"
    ),
    SyncItem(
        name="FastMCP API 使用",
        prototype_section="第 5.3 节",
        security_section="第 10 节",
        status="synced"
    ),
    SyncItem(
        name="JSON-RPC 响应格式",
        prototype_section="第 5.3 节",
        security_section="第 10 节",
        status="synced"
    ),
    SyncItem(
        name="ContextVar 身份隔离",
        prototype_section="第 5.2 节",
        security_section="第 10 节",
        status="synced"
    ),
    SyncItem(
        name="工具函数签名设计",
        prototype_section="第 5.4 节",
        security_section="第 3 节",
        status="synced"
    ),
]


def read_file(filepath: Path) -> str:
    """读取文件内容"""
    if not filepath.exists():
        print(f"错误: 文件不存在 {filepath}")
        sys.exit(1)
    return filepath.read_text(encoding='utf-8')


def extract_section(content: str, section_num: str) -> str:
    """提取指定章节内容"""
    # 匹配章节标题，如 "## 5." 或 "### 5.3"
    pattern = rf"(^##\s+{re.escape(section_num)}.*?)(?=^##\s+\d|\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1)
    return ""


def check_keyword_exists(content: str, keyword: str) -> bool:
    """检查关键词是否存在"""
    return keyword.lower() in content.lower()


def generate_report(checklist: List[SyncItem]) -> str:
    """生成同步报告"""
    lines = [
        "=" * 50,
        "MCP 原型设计同步报告",
        "=" * 50,
        "",
    ]

    # 已同步项
    synced = [item for item in checklist if item.status == "synced"]
    if synced:
        lines.append("[已同步项]")
        for item in synced:
            lines.append(f"✓ {item.name}")
        lines.append("")

    # 待同步项
    pending = [item for item in checklist if item.status == "pending"]
    if pending:
        lines.append("[待同步项]")
        for item in pending:
            lines.append(f"△ {item.name} - {item.suggestion}")
        lines.append("")

    # 缺失项
    missing = [item for item in checklist if item.status == "missing"]
    if missing:
        lines.append("[缺失项]")
        for item in missing:
            lines.append(f"✗ {item.name} - {item.suggestion}")
        lines.append("")

    # 同步建议
    if pending or missing:
        lines.append("[同步建议]")
        suggestions = []
        for i, item in enumerate(pending + missing, 1):
            suggestions.append(f"{i}. {item.suggestion}")
        lines.extend(suggestions)
        lines.append("")

    lines.append("=" * 50)

    return "\n".join(lines)


def main():
    """主函数"""
    print("正在检查原型和方案文档...")

    # 读取文档
    prototype_content = read_file(PROTOTYPE_DOC)
    security_content = read_file(SECURITY_DOC)

    # 检查关键内容
    checks = [
        ("Sidecar", "Sidecar"),
        ("本地代理", "本地代理"),
        ("透传", "透传"),
        ("ContextVar", "ContextVar"),
        ("list_tools", "list_tools"),
        ("call_tool", "call_tool"),
        ("jsonrpc", "jsonrpc"),
    ]

    for proto_kw, security_kw in checks:
        proto_exists = check_keyword_exists(prototype_content, proto_kw)
        security_exists = check_keyword_exists(security_content, security_kw)

        # 如果原型有但方案没有，标记为待同步
        if proto_exists and not security_exists:
            for item in SYNC_CHECKLIST:
                if proto_kw.lower() in item.name.lower():
                    item.status = "pending"
                    item.suggestion = f"方案缺少 {security_kw} 相关内容"

    # 生成报告
    report = generate_report(SYNC_CHECKLIST)
    print(report)


if __name__ == "__main__":
    main()
