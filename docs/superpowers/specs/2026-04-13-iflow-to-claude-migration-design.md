---
name: iflow-to-claude-migration
description: Migration plan from iFlow CLI to Claude Code
date: 2026-04-13
status: completed
completed-date: 2026-04-14
---

# iFlow to Claude Code Migration

## Overview

Migrate the Bank Services Plugins project from iFlow CLI to Claude Code by updating all documentation, paths, and references.

## Current State

✅ 迁移已完成：
- `.iflow/` 目录已删除
- `.claude/` 目录已创建并包含迁移后的内容
- `AGENTS.md` 已删除，被 `CLAUDE.md` 替代
- 所有文档已更新，移除对 `.iflow/` 和 "iFlow CLI" 的引用

## Migration Scope

### Files Updated

| File | Changes |
|------|---------|
| `CLAUDE.md` | 更新目录结构、路径、描述 |
| `progress.txt` | 添加迁移完成记录 |
| `lessons.md` | 删除过时的 iFlow 相关经验教训 |

### Files Removed

- `.iflow/` directory
- `AGENTS.md`
- OpenSpec skills (openspec-propose, openspec-apply-change, openspec-archive-change, openspec-explore)

## Success Criteria

- [x] All documentation references `.claude/` instead of `.iflow/`
- [x] All mentions of "iFlow CLI" changed to "Claude Code"
- [x] Skills are invokable via Claude Code Skill tool
- [x] No broken documentation links
