# conversation-exporter

A [Claude skill](https://docs.claude.com/en/docs/claude-code/skills) that exports individual Claude conversations from a `conversations.json` data export into clean, standalone Markdown files — formatted for compatibility with [basic-memory](https://github.com/basicmachines-co/basic-memory).

Use it to pull a specific chat out of your Claude data export and drop it into Claude Code, a project knowledge base, or a basic-memory store.

## What it does

Given a `conversations.json` from Claude's **Settings → Account → Export Data**, the skill can:

- **List** every conversation (index, date, message count, title)
- **Search** conversations by keyword across titles and all message text
- **Export** one, several, or all conversations to Markdown — by index, UUID, or `--all`

Output filenames follow basic-memory's convention: `{YYYYMMDD}-{Clean_Title}.md`.

### Formatting parity with basic-memory

The Markdown matches basic-memory's `ClaudeConversationsImporter` output exactly — frontmatter field order, `### Sender (timestamp)` message headers, attachment rendering, and filename casing.

On top of that, it **preserves content basic-memory's importer drops**:

| Block type    | Rendered as                          |
| ------------- | ------------------------------------ |
| `tool_use`    | `[Tool call: name]` + JSON input     |
| `tool_result` | `[Tool result]` + content            |
| `image`       | `[Image]` placeholder                |
| `document`    | `[Document]` placeholder             |
| `thinking`    | `[thinking block]` marker — or the full text, quoted, with `--include-thinking` |

## Repository layout

```
conversation-exporter/
├── SKILL.md                      # Skill definition + workflow (the entry point)
├── scripts/
│   └── export_conversation.py    # Standalone CLI that does the work
├── requirements.txt              # PyYAML (optional — script has a fallback)
├── LICENSE
└── README.md
```

## Install as a Claude skill

**claude.ai / Claude Desktop:** zip this folder (or grab the repo ZIP from GitHub) and upload it on claude.ai under **Settings → Capabilities → Skills**. Uploaded skills sync across your devices.

**Claude Code:** copy the folder into a skills directory:

```bash
# Personal skill (available in every Claude Code session)
cp -r conversation-exporter ~/.claude/skills/

# …or as a project skill (available only inside one repo)
cp -r conversation-exporter /path/to/your/project/.claude/skills/
```

Claude triggers the skill automatically when you ask to export, extract, or convert a conversation from a `conversations.json` file.

> **Note:** the paths in `SKILL.md` (`/mnt/user-data/uploads`, `/mnt/user-data/outputs`, `present_files`) reflect Claude's managed file-tool environment. The script itself takes arbitrary input/output paths as CLI arguments, so it runs anywhere.

## Use the script directly

The CLI is fully standalone — no skill harness required.

```bash
# Install the optional dependency (recommended for clean YAML escaping)
pip install pyyaml

# List all conversations
python scripts/export_conversation.py conversations.json --list

# Search by keyword (title + all message text, including content blocks)
python scripts/export_conversation.py conversations.json --search "MCP server"

# Export by index (comma-separate for several)
python scripts/export_conversation.py conversations.json --index 1,5,12 --output ./out/

# Export by UUID
python scripts/export_conversation.py conversations.json --uuid "abc-123" --output ./out/

# Export everything
python scripts/export_conversation.py conversations.json --all --output ./out/
```

## Requirements

- **Python 3.10+** (uses `str | None` style type hints)
- **PyYAML** — optional. Produces the cleanest YAML frontmatter; the script falls back to manual escaping if it isn't installed.

## License

[MIT](LICENSE) © 2026 [joshuaonsc](https://github.com/joshuaonsc)
