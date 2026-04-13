---
name: iflow-to-claude-migration
description: Migration plan from iFlow CLI to Claude Code
date: 2026-04-13
status: approved
---

# iFlow to Claude Code Migration

## Overview

Migrate the Bank Services Plugins project from iFlow CLI to Claude Code by updating all documentation, paths, and references.

## Current State

- `.iflow/` files are staged for deletion
- `.claude/` directory exists with migrated content (untracked)
- `AGENTS.md` was deleted
- `CLAUDE.md` still references `.iflow/` paths and "iFlow CLI"

## Migration Scope

### Files to Update

| File | Changes Required |
|------|-----------------|
| `CLAUDE.md` | Update directory structure, paths, descriptions |
| `.claude/skills/excel-auto-fill/SKILL.md` | Update path references |
| `.claude/skills/anomaly-detector/SKILL.md` | Update path references |
| `.claude/skills/openspec-*/SKILL.md` | Update path references |

### Files to Remove

- `.iflow/` directory (already staged)
- `AGENTS.md` (already staged)

## Detailed Changes

### 1. CLAUDE.md

- Project description: "iFlow CLI" → "Claude Code"
- Directory structure: `.iflow/` → `.claude/`
- Command descriptions: "iFlow 自定义命令" → "Claude Code 自定义命令"
- Skill locations: Update all path references
- Remove AGENTS.md reference in directory structure

### 2. SKILL.md Files

For each skill:
- Update documentation path references from `.iflow/skills/` to `.claude/skills/`
- Update "iFlow CLI 技能系统文档" link/reference

### 3. No Code Changes

Python source code, test files, and scripts remain unchanged - they work independently of the CLI system.

## Implementation Tasks

1. Update CLAUDE.md with new paths and descriptions
2. Update excel-auto-fill/SKILL.md path references
3. Update anomaly-detector/SKILL.md path references
4. Update openspec SKILL.md files
5. Stage and commit all changes

## Success Criteria

- All documentation references `.claude/` instead of `.iflow/`
- All mentions of "iFlow CLI" changed to "Claude Code"
- Skills are invokable via Claude Code Skill tool
- No broken documentation links
