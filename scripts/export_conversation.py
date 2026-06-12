#!/usr/bin/env python3
"""
Export individual Claude conversations from a conversations.json data export to markdown files.

Combines basic-memory's formatting conventions with explicit preservation of tool_use,
tool_result, image, and document content blocks that basic-memory's importer drops.

Formatting parity with basic-memory verified against:
- src/basic_memory/importers/claude_conversations_importer.py
- src/basic_memory/importers/utils.py (clean_filename, format_timestamp)
- src/basic_memory/markdown/markdown_processor.py (frontmatter field ordering)
- src/basic_memory/markdown/schemas.py (EntityFrontmatter, EntityMarkdown)
- tests/cli/test_import_claude_conversations.py (filename casing, None text, attachments)

Usage:
    python export_conversation.py <conversations.json> --list
    python export_conversation.py <conversations.json> --search "MCP server"
    python export_conversation.py <conversations.json> --index 42 --output /mnt/user-data/outputs/
    python export_conversation.py <conversations.json> --uuid "abc-123" --output /mnt/user-data/outputs/
    python export_conversation.py <conversations.json> --index 1,5,12 --output /mnt/user-data/outputs/
    python export_conversation.py <conversations.json> --all --output /mnt/user-data/outputs/
"""

import json
import sys
import re
import argparse
from collections import OrderedDict
from pathlib import Path
from datetime import datetime

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# ---------------------------------------------------------------------------
# Utility functions — ported from basic_memory/importers/utils.py
# ---------------------------------------------------------------------------

def load_conversations(filepath: str) -> list[dict]:
    """Load and return the conversations array from a conversations.json file."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array of conversations at the top level.")
    return data


def clean_filename(name: str | None) -> str:
    """Clean a string to be used as a filename.

    Ported from basic_memory/importers/utils.py — preserves case, uses underscores.
    """
    if not name:
        return "untitled"
    # Replace common punctuation and whitespace with underscores
    name = re.sub(r"[\s\-,.:/\\\[\]\(\)]+", "_", name)
    # Remove any non-alphanumeric or underscore characters
    name = re.sub(r"[^\w]+", "", name)
    if len(name) > 100:
        name = name[:100]
    if not name:
        name = "untitled"
    return name


def format_timestamp(timestamp) -> str:
    """Format a timestamp for display in message headers.

    Ported from basic_memory/importers/utils.py — handles ISO 8601, unix timestamps
    (int/float), and string-encoded unix timestamps.
    """
    parsed_timestamp = timestamp
    if isinstance(timestamp, str):
        try:
            parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed_timestamp = datetime.fromtimestamp(float(timestamp)).astimezone()
            except ValueError:
                return timestamp
    elif isinstance(timestamp, (int, float)):
        parsed_timestamp = datetime.fromtimestamp(timestamp).astimezone()

    if isinstance(parsed_timestamp, datetime):
        return parsed_timestamp.strftime("%Y-%m-%d %H:%M:%S")

    return str(parsed_timestamp)


def date_prefix(ts: str) -> str:
    """Extract a YYYYMMDD prefix for filenames.

    Matches basic-memory's convention: datetime.fromisoformat(...).strftime("%Y%m%d")
    """
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y%m%d")
    except (ValueError, TypeError):
        return "00000000"


def date_display(ts: str) -> str:
    """Extract a YYYY-MM-DD string for display in listings."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return "unknown"


def render_frontmatter(metadata: OrderedDict) -> str:
    """Render YAML frontmatter with proper escaping.

    Uses PyYAML's SafeDumper when available (matching basic-memory's dump_frontmatter).
    Falls back to manual escaping that handles colons, quotes, and special characters.
    """
    if HAS_YAML:
        yaml_str = yaml.dump(
            dict(metadata),
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
            Dumper=yaml.SafeDumper,
        )
        return f"---\n{yaml_str}---"
    else:
        # Manual fallback — use single quotes for strings with special chars,
        # escaping any internal single quotes by doubling them (YAML convention).
        lines = ["---"]
        for key, value in metadata.items():
            if isinstance(value, str) and any(
                c in value for c in ':{}[],"\'#|>&*!%@`\n'
            ):
                escaped = value.replace("'", "''")
                lines.append(f"{key}: '{escaped}'")
            elif isinstance(value, str):
                lines.append(f"{key}: {value}")
            else:
                lines.append(f"{key}: {value}")
        lines.append("---")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Content extraction — extends basic-memory with tool call / non-text handling
# ---------------------------------------------------------------------------

def safe_text(value) -> str:
    """Safely extract text, handling None values.

    Addresses basic-memory issue #236: content blocks can have {"type": "text", "text": None}
    where dict.get("text", "") returns None (key exists), not "" (default).
    """
    if value is None:
        return ""
    return str(value).strip()


def extract_message_text(message: dict, include_thinking: bool = False) -> str:
    """
    Extract display text from a chat message's content blocks.

    basic-memory only extracts blocks with a .text field and joins them with spaces,
    silently dropping tool_use, tool_result, image, and document blocks. This function
    preserves those blocks with descriptive inline labels.

    Thinking blocks render as a bare "[thinking block]" marker unless include_thinking
    is set, in which case their text is embedded as a quoted [Thinking] section.
    """
    content_blocks = message.get("content", [])
    if content_blocks and isinstance(content_blocks, list):
        parts = []
        for block in content_blocks:
            if not block:
                continue
            block_type = block.get("type", "")

            if block_type == "text":
                text = safe_text(block.get("text"))
                if text:
                    parts.append(text)

            elif block_type == "tool_use":
                tool_name = block.get("name", "unknown_tool")
                tool_input = block.get("input", {})
                parts.append(f"[Tool call: {tool_name}]")
                if tool_input:
                    try:
                        input_str = json.dumps(tool_input, indent=2)
                        parts.append(f"```json\n{input_str}\n```")
                    except (TypeError, ValueError):
                        parts.append(f"```\n{tool_input}\n```")

            elif block_type == "tool_result":
                tool_content = block.get("content", "")
                if isinstance(tool_content, list):
                    for sub in tool_content:
                        if isinstance(sub, dict) and sub.get("type") == "text":
                            sub_text = safe_text(sub.get("text"))
                            if sub_text:
                                parts.append(f"[Tool result]\n{sub_text}")
                        elif isinstance(sub, dict) and sub.get("type") == "image":
                            parts.append("[Tool result: image]")
                        else:
                            parts.append(
                                f"[Tool result: {sub.get('type', 'unknown') if isinstance(sub, dict) else 'unknown'}]"
                            )
                elif isinstance(tool_content, str) and tool_content.strip():
                    parts.append(f"[Tool result]\n{tool_content}")

            elif block_type == "image":
                parts.append("[Image]")

            elif block_type == "document":
                parts.append("[Document]")

            elif block_type == "thinking":
                thinking_text = safe_text(block.get("thinking")) if include_thinking else ""
                if thinking_text:
                    quoted = "\n".join(
                        f"> {line}" if line else ">" for line in thinking_text.splitlines()
                    )
                    parts.append(f"[Thinking]\n{quoted}")
                else:
                    parts.append("[thinking block]")

            else:
                parts.append(f"[{block_type or 'unknown'} block]")

        if parts:
            return "\n\n".join(parts)

    # Fallback to top-level text field
    return safe_text(message.get("text"))


def extract_searchable_text(message: dict) -> str:
    """Extract all searchable text from a message, including content blocks.

    Unlike extract_message_text (which formats for display), this concatenates all
    text content for keyword matching — covering both the top-level text field and
    every text block in the content array.
    """
    parts = []
    top_text = safe_text(message.get("text"))
    if top_text:
        parts.append(top_text)

    for block in message.get("content", []):
        if not block:
            continue
        block_text = safe_text(block.get("text"))
        if block_text:
            parts.append(block_text)

    return " ".join(parts)


def format_attachments(message: dict) -> str:
    """Format message-level attachments. Matches basic-memory's attachment handling."""
    attachments = message.get("attachments", [])
    if not attachments:
        return ""

    parts = []
    for attachment in attachments:
        if "file_name" in attachment:
            parts.append(f"\n**Attachment: {attachment['file_name']}**")
            if "extracted_content" in attachment:
                parts.append("```")
                parts.append(attachment["extracted_content"])
                parts.append("```")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Markdown conversion
# ---------------------------------------------------------------------------

def conversation_to_markdown(conversation: dict, include_thinking: bool = False) -> str:
    """
    Convert a single conversation dict to a markdown string.

    Follows basic-memory's formatting:
    - Frontmatter field order: title, type, permalink, then metadata (via MarkdownProcessor)
    - YAML values properly escaped via SafeDumper
    - H1 title
    - H3 message headers: ### Sender (timestamp)
    - Attachment blocks with code-fenced extracted_content
    - Unnamed conversations default to "Conversation {uuid}"

    Extends basic-memory by preserving tool_use, tool_result, image, and document
    content blocks inline.
    """
    uuid = conversation.get("uuid", "unknown")
    title = conversation.get("name") or f"Conversation {uuid}"
    created = conversation.get("created_at", "")
    modified = conversation.get("updated_at", "")
    # Permalink only: strip hyphens left by bracketed titles ("[x] Tuning" would
    # otherwise yield "-x-tuning"). Filenames keep basic-memory's convention byte-for-byte.
    permalink = clean_filename(title).lower().replace("_", "-").strip("-") or "untitled"
    messages = conversation.get("chat_messages", [])

    # Frontmatter — field order matches basic-memory's MarkdownProcessor:
    # title, type, permalink first, then remaining metadata
    frontmatter = OrderedDict()
    frontmatter["title"] = title
    frontmatter["type"] = "conversation"
    frontmatter["permalink"] = permalink
    frontmatter["uuid"] = uuid
    frontmatter["created"] = created
    frontmatter["modified"] = modified
    frontmatter["message_count"] = len(messages)
    frontmatter["source"] = "claude.ai"

    lines = []
    lines.append(render_frontmatter(frontmatter))
    lines.append("")

    # Content — matches basic-memory's _format_chat_markdown
    lines.append(f"# {title}\n")

    for msg in messages:
        sender = msg.get("sender", "unknown")
        ts = format_timestamp(msg.get("created_at", ""))

        # H3 header with inline timestamp — basic-memory convention
        lines.append(f"### {sender.title()} ({ts})")

        # Message content
        text = extract_message_text(msg, include_thinking)
        lines.append(text if text else "")

        # Attachments — basic-memory convention
        attachment_text = format_attachments(msg)
        if attachment_text:
            lines.append(attachment_text)

        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Listing, searching, exporting
# ---------------------------------------------------------------------------

def list_conversations(conversations: list[dict]) -> None:
    """Print a table of all conversations with index, title, date, and message count."""
    print(f"{'Idx':<6} {'Date':<12} {'Messages':<10} {'Title'}")
    print("-" * 80)
    for i, conv in enumerate(conversations):
        title = conv.get("name") or "Untitled"
        date = date_display(conv.get("created_at", ""))
        msg_count = len(conv.get("chat_messages", []))
        display_title = title[:50] + "..." if len(title) > 50 else title
        print(f"{i:<6} {date:<12} {msg_count:<10} {display_title}")
    print(f"\nTotal: {len(conversations)} conversations")


def search_conversations(conversations: list[dict], query: str) -> list[tuple[int, dict]]:
    """Search conversations by keyword.

    Matches against title and all message text — both the top-level text field and
    text within content blocks, so tool_use messages with surrounding text are findable.
    """
    query_lower = query.lower()
    results = []
    for i, conv in enumerate(conversations):
        title = (conv.get("name") or "").lower()
        if query_lower in title:
            results.append((i, conv))
            continue
        for msg in conv.get("chat_messages", []):
            searchable = extract_searchable_text(msg).lower()
            if query_lower in searchable:
                results.append((i, conv))
                break
    return results


def export_conversations(
    conversations: list[dict],
    indices: list[int],
    output_dir: str,
    include_thinking: bool = False,
) -> list[str]:
    """Export selected conversations to markdown files. Returns list of output paths."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    exported = []
    for idx in indices:
        if idx < 0 or idx >= len(conversations):
            print(
                f"WARNING: Index {idx} out of range (0-{len(conversations)-1}), skipping.",
                file=sys.stderr,
            )
            continue

        conv = conversations[idx]
        markdown = conversation_to_markdown(conv, include_thinking)

        # Filename: {YYYYMMDD}-{Clean_Title}.md — basic-memory convention
        title = conv.get("name") or f"Conversation {conv.get('uuid', 'untitled')}"
        dp = date_prefix(conv.get("created_at", ""))
        clean_title = clean_filename(title)
        filename = f"{dp}-{clean_title}.md"
        filepath = output_path / filename

        # Handle collisions
        counter = 1
        while filepath.exists():
            filepath = output_path / f"{dp}-{clean_title}_{counter}.md"
            counter += 1

        filepath.write_text(markdown, encoding="utf-8")
        exported.append(str(filepath))
        print(f"Exported: {filepath}")

    return exported


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Export Claude conversations from conversations.json to markdown."
    )
    parser.add_argument("input_file", help="Path to conversations.json")
    parser.add_argument("--list", action="store_true", help="List all conversations")
    parser.add_argument("--search", type=str, help="Search conversations by keyword")
    parser.add_argument(
        "--index",
        type=str,
        help="Export conversation(s) by index (comma-separated for multiple)",
    )
    parser.add_argument("--uuid", type=str, help="Export conversation by UUID")
    parser.add_argument("--all", action="store_true", help="Export all conversations")
    parser.add_argument(
        "--output",
        type=str,
        default=".",
        help="Output directory (default: current directory)",
    )
    parser.add_argument(
        "--include-thinking",
        action="store_true",
        help="Embed thinking-block text as quoted [Thinking] sections "
        "(default: bare [thinking block] markers)",
    )

    args = parser.parse_args()
    try:
        conversations = load_conversations(args.input_file)
    except FileNotFoundError:
        sys.exit(f"Error: file not found: {args.input_file}")
    except json.JSONDecodeError as e:
        sys.exit(f"Error: {args.input_file} is not valid JSON ({e}).")
    except ValueError as e:
        sys.exit(f"Error: {e}")

    if args.list:
        list_conversations(conversations)
        return

    if args.search:
        results = search_conversations(conversations, args.search)
        if not results:
            print(f"No conversations matching '{args.search}'.")
            return
        print(f"{'Idx':<6} {'Date':<12} {'Messages':<10} {'Title'}")
        print("-" * 80)
        for orig_idx, conv in results:
            title = conv.get("name") or "Untitled"
            date = date_display(conv.get("created_at", ""))
            msg_count = len(conv.get("chat_messages", []))
            display_title = title[:50] + "..." if len(title) > 50 else title
            print(f"{orig_idx:<6} {date:<12} {msg_count:<10} {display_title}")
        print(f"\nFound: {len(results)} conversations")
        return

    if args.uuid:
        for i, conv in enumerate(conversations):
            if conv.get("uuid") == args.uuid:
                exported = export_conversations(conversations, [i], args.output, args.include_thinking)
                if exported:
                    print(f"\nDone. Exported {len(exported)} conversation(s).")
                return
        print(f"No conversation found with UUID: {args.uuid}", file=sys.stderr)
        sys.exit(1)

    if args.all:
        indices = list(range(len(conversations)))
        exported = export_conversations(conversations, indices, args.output, args.include_thinking)
        print(f"\nDone. Exported {len(exported)} conversation(s).")
        return

    if args.index:
        try:
            indices = [int(x.strip()) for x in args.index.split(",") if x.strip()]
        except ValueError:
            sys.exit(f"Error: --index expects comma-separated integers, got: {args.index!r}")
        exported = export_conversations(conversations, indices, args.output, args.include_thinking)
        print(f"\nDone. Exported {len(exported)} conversation(s).")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
