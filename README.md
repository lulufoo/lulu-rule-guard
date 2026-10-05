# lulu-rule-guard

Blocks a write until the session has fully read the rule document configured for that file.

## Commands

| Command | Effect |
|---------|--------|
| `/lulu-rule-guard --list` | List commands |
| `/lulu-rule-guard init` | Register hooks and create config if it is missing. An existing config file is left unchanged |
| `/lulu-rule-guard add-guard-rule --local <path>` | Map file globs to a local rule document or directory. Requires `init` |

`add-guard-rule` registers Markdown that already exists in the project. The path must stay inside the project. Files without `rule-guard.globs` frontmatter are skipped. The same glob replaces the existing `required` entry.

## After `init`

`init` writes the hooks and config for the current platform.

| Platform | Hooks | Config |
|----------|-------|--------|
| Cursor | `.cursor/hooks.json` | `.agents/config/lulu-rule-guard/rule-guard-config.json` |
| Copilot | `.github/hooks/hooks.json` | `.agents/config/lulu-rule-guard/rule-guard-config.json` |
| Claude | `.claude/settings.json` | `.agents/config/lulu-rule-guard/rule-guard-config.json` |
| Codex | `.codex/hooks.json` | `.agents/config/lulu-rule-guard/rule-guard-config.json` |
| OpenCode | `.opencode/plugins/lulu-rule-guard.ts` (plugin bridge) | `.agents/config/lulu-rule-guard/rule-guard-config.json` |

Config is platform-neutral and shared. When `.agents/config/lulu-rule-guard/rule-guard-config.json` does not exist, the legacy per-platform path (`.cursor/skills/lulu-rule-guard/`, `.github/lulu-rule-guard/`, `.claude/lulu-rule-guard/`, `.codex/lulu-rule-guard/`) is the fallback.

OpenCode has no declarative hooks.json; `init` writes a TypeScript plugin that calls the same `entry.py` (`tool.execute.before`, deny = throw). Restart OpenCode after `init` for the plugin to load.

`preToolUse` enforces the guard. `init` strips leftover `play_chime` stop entries and does not register a completion sound.

When `fileGuard.enabled` is true and `rules` is non-empty, a write that matches a glob is allowed only after the session has fully read that rule's `required` document. A partial read does not count. Writes pass through when the guard is off or `rules` is empty.

## Config

`init` writes `version` and an empty `fileGuard`. The sample below is that file after rules are added. `required` is a path inside the project.

```json
{
  "version": 2,
  "fileGuard": {
    "enabled": true,
    "rulesDocsDir": "docs",
    "rules": [
      {
        "glob": "**/*.py",
        "required": ["docs/coding/py.md"]
      }
    ]
  }
}
```

| Field | Meaning |
|-------|---------|
| `version` | Config version. Current value is `2` |
| `fileGuard.enabled` | Enforce read-before-write |
| `fileGuard.rulesDocsDir` | Relative directory name stored on `fileGuard`. Absolute paths are rejected |
| `rules[].glob` | Files this rule guards |
| `rules[].required` | Documents that must be fully read before those writes. Paths are relative to the project root |
