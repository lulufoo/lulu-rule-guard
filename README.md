# lulu-rule-guard

A Cursor and Copilot skill that blocks a write until the session has fully read the rule document configured for that file.

Install the skill at `~/.cursor/skills/lulu-rule-guard`. In a project, run the commands below. The skill detects Cursor or Copilot and writes that platform's hooks and config.

## Commands

| Command | Effect |
|---------|--------|
| `/lulu-rule-guard --list` | List commands |
| `/lulu-rule-guard init` | Register hooks and create config if it is missing. An existing config file is left unchanged |
| `/lulu-rule-guard add-guard-rule --local <path>` | Map file globs to a local rule document or directory. Requires `init` |

`add-guard-rule` skips Markdown that has no `rule-guard.globs` frontmatter. The same glob replaces the existing `required` entry. `--source-url` fetches a GitHub Markdown file instead of using a local path.

## After `init`

| Platform | Hooks | Config |
|----------|-------|--------|
| Cursor | `.cursor/hooks.json` | `.cursor/skills/lulu-rule-guard/rule-guard-config.json` |
| Copilot | `.github/hooks/hooks.json` | `.github/lulu-rule-guard/rule-guard-config.json` |

`preToolUse` enforces the guard. `stop` plays the chime when that setting is on.

When `fileGuard.enabled` is true and `rules` is non-empty, a write that matches a glob is allowed only after the session has fully read that rule's `required` document. A partial read does not count. Writes pass through when the guard is off or `rules` is empty.

## Config

`init` writes `version` and an empty `fileGuard`. It does not write `chime`. The sample below is that file after rules and the optional chime block are added. `required` is a path inside the project.

```json
{
  "version": 2,
  "chime": {
    "enabled": false,
    "sound": "/System/Library/Sounds/Funk.aiff",
    "volume": 1,
    "gain": 25
  },
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
| `chime.enabled` | Play a sound when the agent stops. Omitted means off |
| `chime.sound` / `volume` / `gain` | Sound file, volume, and gain |
| `fileGuard.enabled` | Enforce read-before-write |
| `fileGuard.rulesDocsDir` | Project directory for rule documents fetched from GitHub. Absolute paths are rejected |
| `rules[].glob` | Files this rule guards |
| `rules[].required` | Documents that must be fully read before those writes. Paths are relative to the project root |
