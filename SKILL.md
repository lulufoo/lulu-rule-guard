---
name: lulu-rule-guard
description: >-
  Hook-based read-before-write enforcement: init registers Cursor/Copilot
  hooks; add-guard-rule maps file globs to required docs.
  Triggers: lulu-rule-guard, rule-guard, init rule guard, 初始化规则守卫,
  规则守卫, add guard rule, 添加守卫规则.
meta-skill-version: 0.5.0
disable-model-invocation: true
argument-hint: "[--list | init | add-guard-rule]"
---

# lulu-rule-guard

Enforce read-before-write via hooks. Completion: hooks registered and
`fileGuard.rules` list the glob → doc mappings the project needs.

## Prerequisites

- `gh` installed and authenticated (`gh auth status`) — required only when an explicit GitHub source is used

## Platform Context

Detect once at session start. Substitute variables throughout.

| Variable | cursor | claude | copilot |
|----------|--------|--------|---------|
| `$PLATFORM` | `cursor` | `claude` | `copilot` |
| `$SKILL_ROOT` | `~/.cursor/skills/lulu-rule-guard` | `~/.claude/skills/lulu-rule-guard` | `~/.copilot/skills/lulu-rule-guard` |
| `$RULE_GUARD_DIR` | `.cursor/skills/lulu-rule-guard/` | — | `.github/lulu-rule-guard/` |
| `$CACHE_ROOT` | `.cache/cursor/lulu-rule-guard` | — | `.cache/copilot/lulu-rule-guard` |
| `$DEFAULT_DOCS_DIR` | `docs` | (same) | (same) |

### Detection

Runtime signals only; first match wins; else ask.

1. `VSCODE_TARGET_SESSION_LOG` or `COPILOT_AGENT=1` → `copilot`
2. `CURSOR_AGENT` set → `cursor`
3. `CLAUDE_CODE` set → `claude`

## Command picker

| Input | Action |
|-------|--------|
| `/lulu-rule-guard --list` | Run `$LIST` |
| User replies with a listed name | Route to that command |

## Which command

| Goal | Command |
|------|---------|
| Hook enforcement: glob → required doc in `fileGuard.rules` | **add-guard-rule** (requires **init**) |

## Script Macros

| Macro | CLI |
|-------|-----|
| `$LIST` | `python3 $SKILL_ROOT/scripts/lulu-rule-guard.py --list` |
| `$ADD_GUARD` | `python3 $SKILL_ROOT/scripts/add-guard-rule.py` |
| `$INIT` | `python3 $SKILL_ROOT/scripts/init.py --platform $PLATFORM` |

---

## Commands

### `init`

Initialize hook-based rule-guard in the current project. Cursor / Copilot only.

`init` creates the missing `$RULE_GUARD_DIR/rule-guard-config.json` (no overwrite). Runtime settings and `fileGuard.rules` live in that file.

Next: add glob → doc mappings with **add-guard-rule**.

### `add-guard-rule`

Add glob → doc mappings to `fileGuard.rules`. One of:

- `--source-url` — fetch GitHub markdown → `$DEFAULT_DOCS_DIR/` + append rules
- `--local` — register an existing local `.md` file or directory (no copy).
  Files without `rule-guard.globs` are skipped. Same glob replaces `required`.

**Optional:** `--rules-docs-dir` (GitHub source only)

After **lulu-discipline-skills** `init`, register that skill's
`$PROJECT_COPY` with `$ADD_GUARD --local $PROJECT_COPY`.

## Hooks

| Event | Platform | Script | Effect |
|-------|----------|--------|--------|
| `preToolUse` | Cursor | `entry.py` | When `fileGuard.enabled`: block write until rules satisfied |
| `preToolUse` | Copilot | `entry.py` | When `fileGuard.enabled`: block write until required doc read |
| `stop` | Both | `play_chime.py` | Chime on agent stop (macOS) |

Session state: `$CACHE_ROOT/rules-state/{session_id}/{basename}.json`

Partial reads are not counted as full reads. `fileGuard.enabled: false` or empty
`fileGuard.rules` → writes pass through.
