---
name: conversation-exporter
description: Export individual Claude conversations from a data export to clean markdown files. Use this skill whenever the user wants to extract, export, or convert a specific conversation from their Claude data export (conversations.json) into a markdown file. Trigger when the user mentions exporting a chat, extracting a conversation, converting conversations.json, or needs a conversation in markdown format for use in Claude Code or another context. Also trigger when the user uploads a conversations.json file and asks to find, search, list, or export conversations from it. This skill produces output compatible with basic-memory's conversation import format. Do NOT use this skill if the user wants to export the current in-progress conversation — this skill requires a conversations.json file from Claude's Settings → Export Data feature.
---

# Conversation Exporter

Export individual Claude conversations from a `conversations.json` data export (Settings → Account → Export Data) to standalone markdown files, formatted for compatibility with basic-memory.

If the user asks to export the *current in-progress* conversation, this skill can't do that — it only operates on an already-exported `conversations.json`.

## Workflow

### Step 0: Ensure PyYAML is available

The script prefers PyYAML for safe YAML frontmatter escaping, with a manual fallback if it's unavailable — so if the install fails, proceed anyway. Install it if possible:

```bash
pip install pyyaml --break-system-packages
```

### Step 1: Locate the uploaded file

The user will upload their `conversations.json`. Check `/mnt/user-data/uploads/` for it.

If the user uploaded a ZIP file instead of a bare JSON, extract it first:

```bash
cd /mnt/user-data/uploads && unzip -o *.zip
```

Then locate the `conversations.json` inside the extracted contents.

### Step 2: List or search conversations

Determine the path to `export_conversation.py` — it's at `scripts/export_conversation.py` within this skill's directory (the same directory as this SKILL.md). Set it as a variable for the commands below:

```bash
SCRIPT="<this skill's directory>/scripts/export_conversation.py"
```

Then run:

```bash
# List all conversations (index, date, message count, title)
python "$SCRIPT" /mnt/user-data/uploads/conversations.json --list

# Search by keyword (matches title and all message text, including content blocks)
python "$SCRIPT" /mnt/user-data/uploads/conversations.json --search "search term"
```

If the list is very long, use `--search` first or pipe through `head -50`.

### Step 3: Export selected conversation(s)

```bash
# Single conversation by index
python "$SCRIPT" /mnt/user-data/uploads/conversations.json --index 42 --output /mnt/user-data/outputs/

# Multiple conversations by index
python "$SCRIPT" /mnt/user-data/uploads/conversations.json --index 1,5,12 --output /mnt/user-data/outputs/

# All conversations at once
python "$SCRIPT" /mnt/user-data/uploads/conversations.json --all --output /mnt/user-data/outputs/

# By UUID if known
python "$SCRIPT" /mnt/user-data/uploads/conversations.json --uuid "abc-123" --output /mnt/user-data/outputs/
```

### Step 4: Present the file(s)

Use `present_files` to hand the markdown file(s) to the user. Files are named `{YYYYMMDD}-{Clean_Title}.md` matching basic-memory's convention.

## Output format

Markdown output matches basic-memory's `ClaudeConversationsImporter` formatting exactly — frontmatter field order, `### Sender (timestamp)` message headers, attachment rendering, filename convention, and unnamed-conversation defaults.

The script additionally preserves content that basic-memory's importer drops: `tool_use` blocks render as `[Tool call: name]` with JSON input, `tool_result` blocks render as `[Tool result]` with content, and `image`/`document` blocks get labeled placeholders. Thinking blocks render as a `[thinking block]` marker; pass `--include-thinking` to embed the full thinking text as a quoted block.
