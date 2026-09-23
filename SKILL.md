---
name: lulu-rule-guard
description: >-
  Block writes until the required rule documents have been read.
  add-guard-rule maps file globs to required docs.
  Triggers: lulu-rule-guard, rule-guard, init rule guard, 初始化规则守卫,
  规则守卫, add guard rule, 添加守卫规则.
meta-skill-version: 0.5.0
disable-model-invocation: true
argument-hint: "[--list | init | add-guard-rule]"
---

# lulu-rule-guard

Enforce read-before-write via hooks. Completion: hooks registered and
`fileGuard.rules` list the glob → doc mappings the project needs.

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
| `$RESOLVE_PLATFORM` | `python3 "$SKILL_ROOT/scripts/platform_context.py"` |
| `$LIST` | `python3 $SKILL_ROOT/scripts/lulu-rule-guard.py --list` |
| `$ADD_GUARD` | `python3 $SKILL_ROOT/scripts/add-guard-rule.py` |
| `$INIT` | `python3 $SKILL_ROOT/scripts/init.py --platform $PLATFORM` |

## Platform Context

Run `$RESOLVE_PLATFORM` before `$INIT`. Non-zero exit: stop and report stderr. Map stdout JSON:

| Variable | JSON field |
|----------|------------|
| `$PLATFORM` | `platform` |
| `$SKILL_ROOT` | `skill_root` |
| `$RULE_GUARD_DIR` | `rule_guard_dir` |
| `$CACHE_ROOT` | `cache_dir` |

---

## Commands

### `init`

Initialize hook-based rule-guard in the current project.

`init` creates the missing `$RULE_GUARD_DIR/rule-guard-config.json` (no overwrite). Runtime settings and `fileGuard.rules` live in that file.

Next: add glob → doc mappings with **add-guard-rule**.

### `add-guard-rule`

Register a Markdown file or directory that already exists in this project.

`$ADD_GUARD --local <path>`

The path stays inside the project. Files without `rule-guard.globs` are skipped. The same glob replaces `required`.

## Hooks

| Event | Script | Effect |
|-------|--------|--------|
| `preToolUse` | `entry.py` | When `fileGuard.enabled`: block write until rules satisfied |
| `stop` | `play_chime.py` | Chime on agent stop (macOS) |

Session state: `$CACHE_ROOT/rules-state/{session_id}/{sha256}.json` of the resolved rule path.

Partial reads are not counted as full reads. `fileGuard.enabled: false` or empty
`fileGuard.rules` → writes pass through.
