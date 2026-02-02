#!/usr/bin/env python3
"""
Convert Claude Code session JSONL files to shareable HTML pages.
"""

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO8601 timestamp."""
    # Handle various formats
    ts = ts.replace('Z', '+00:00')
    if '.' in ts:
        # Truncate microseconds to 6 digits if longer
        parts = ts.split('.')
        if '+' in parts[1]:
            frac, tz = parts[1].split('+')
            frac = frac[:6]
            ts = f"{parts[0]}.{frac}+{tz}"
        elif '-' in parts[1][1:]:  # Skip first char in case of negative
            idx = parts[1].rfind('-')
            frac, tz = parts[1][:idx], parts[1][idx+1:]
            frac = frac[:6]
            ts = f"{parts[0]}.{frac}-{tz}"
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return datetime.now()


def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return html.escape(text)


def markdown_to_html(text: str) -> str:
    """Convert basic markdown to HTML."""
    lines = text.split('\n')
    result = []
    in_code_block = False
    code_lang = ''
    code_lines = []
    in_list = False
    list_type = None

    def close_list():
        nonlocal in_list, list_type
        if in_list:
            result.append(f'</{list_type}>')
            in_list = False
            list_type = None

    for line in lines:
        # Code blocks
        if line.startswith('```'):
            if in_code_block:
                code_content = escape_html('\n'.join(code_lines))
                lang_class = f' class="language-{code_lang}"' if code_lang else ''
                result.append(f'<pre><code{lang_class}>{code_content}</code></pre>')
                in_code_block = False
                code_lines = []
                code_lang = ''
            else:
                close_list()
                in_code_block = True
                code_lang = line[3:].strip()
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        # Headers
        if line.startswith('######'):
            close_list()
            result.append(f'<h6>{escape_html(line[6:].strip())}</h6>')
            continue
        if line.startswith('#####'):
            close_list()
            result.append(f'<h5>{escape_html(line[5:].strip())}</h5>')
            continue
        if line.startswith('####'):
            close_list()
            result.append(f'<h4>{escape_html(line[4:].strip())}</h4>')
            continue
        if line.startswith('###'):
            close_list()
            result.append(f'<h3>{escape_html(line[3:].strip())}</h3>')
            continue
        if line.startswith('##'):
            close_list()
            result.append(f'<h2>{escape_html(line[2:].strip())}</h2>')
            continue
        if line.startswith('#'):
            close_list()
            result.append(f'<h1>{escape_html(line[1:].strip())}</h1>')
            continue

        # Unordered lists
        if re.match(r'^[\-\*]\s', line):
            if not in_list or list_type != 'ul':
                close_list()
                result.append('<ul>')
                in_list = True
                list_type = 'ul'
            content = inline_markdown(line[2:].strip())
            result.append(f'<li>{content}</li>')
            continue

        # Ordered lists
        ol_match = re.match(r'^(\d+)\.\s', line)
        if ol_match:
            if not in_list or list_type != 'ol':
                close_list()
                result.append('<ol>')
                in_list = True
                list_type = 'ol'
            content = inline_markdown(line[len(ol_match.group(0)):].strip())
            result.append(f'<li>{content}</li>')
            continue

        # Empty line
        if not line.strip():
            close_list()
            result.append('<br>')
            continue

        # Regular paragraph
        close_list()
        result.append(f'<p>{inline_markdown(line)}</p>')

    close_list()

    # Handle unclosed code block
    if in_code_block:
        code_content = escape_html('\n'.join(code_lines))
        result.append(f'<pre><code>{code_content}</code></pre>')

    return '\n'.join(result)


def inline_markdown(text: str) -> str:
    """Convert inline markdown (bold, italic, code, links)."""
    # Escape HTML first
    text = escape_html(text)

    # Inline code (must be before bold/italic to avoid conflicts)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)

    # Bold
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'__([^_]+)__', r'<strong>\1</strong>', text)

    # Italic
    text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)
    text = re.sub(r'_([^_]+)_', r'<em>\1</em>', text)

    # Links
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

    return text


def format_tool_input(tool_name: str, input_data: dict) -> str:
    """Format tool input for display."""
    if tool_name == 'Bash':
        cmd = input_data.get('command', '')
        desc = input_data.get('description', '')
        result = f'$ {cmd}'
        if desc:
            result = f'# {desc}\n{result}'
        return result

    if tool_name in ('Read', 'Write', 'Edit'):
        path = input_data.get('file_path', '')
        if tool_name == 'Edit':
            old = input_data.get('old_string', '')
            new = input_data.get('new_string', '')
            return f'File: {path}\n\n--- Old:\n{old}\n\n+++ New:\n{new}'
        if tool_name == 'Write':
            content = input_data.get('content', '')
            if len(content) > 500:
                content = content[:500] + '\n... (truncated)'
            return f'File: {path}\n\nContent:\n{content}'
        return f'File: {path}'

    if tool_name == 'Glob':
        pattern = input_data.get('pattern', '')
        path = input_data.get('path', '.')
        return f'Pattern: {pattern}\nPath: {path}'

    if tool_name == 'Grep':
        pattern = input_data.get('pattern', '')
        path = input_data.get('path', '.')
        return f'Pattern: {pattern}\nPath: {path}'

    if tool_name == 'TodoWrite':
        todos = input_data.get('todos', [])
        lines = []
        for todo in todos:
            status = todo.get('status', 'pending')
            content = todo.get('content', '')
            marker = {'pending': '[ ]', 'in_progress': '[~]', 'completed': '[x]'}.get(status, '[ ]')
            lines.append(f'{marker} {content}')
        return '\n'.join(lines)

    if tool_name == 'AskUserQuestion':
        questions = input_data.get('questions', [])
        lines = []
        for q in questions:
            lines.append(f"Q: {q.get('question', '')}")
            for opt in q.get('options', []):
                lines.append(f"  - {opt.get('label', '')}: {opt.get('description', '')}")
        return '\n'.join(lines)

    # Default: JSON format
    return json.dumps(input_data, indent=2)


TOOL_EMOJIS = {
    'Bash': '💻',
    'Read': '📖',
    'Write': '✏️',
    'Edit': '🔧',
    'Glob': '🔍',
    'Grep': '🔎',
    'TodoWrite': '📋',
    'AskUserQuestion': '❓',
    'Task': '🚀',
    'WebFetch': '🌐',
    'WebSearch': '🔍',
}


def get_tool_emoji(tool_name: str) -> str:
    """Get emoji for a tool."""
    return TOOL_EMOJIS.get(tool_name, '🔧')


def get_tool_summary(tool_name: str, input_data: dict) -> str:
    """Get a short summary for tool call header."""
    emoji = get_tool_emoji(tool_name)

    if tool_name == 'Bash':
        desc = input_data.get('description', '')
        if desc:
            return f'{emoji} Bash: {desc}'
        cmd = input_data.get('command', '')
        if len(cmd) > 50:
            cmd = cmd[:50] + '...'
        return f'{emoji} Bash: {cmd}'

    if tool_name in ('Read', 'Write', 'Edit'):
        path = input_data.get('file_path', '')
        if path:
            # Show just filename
            name = Path(path).name
            return f'{emoji} {tool_name}: {name}'
        return f'{emoji} {tool_name}'

    if tool_name == 'Glob':
        return f"{emoji} Glob: {input_data.get('pattern', '')}"

    if tool_name == 'Grep':
        return f"{emoji} Grep: {input_data.get('pattern', '')}"

    if tool_name == 'TodoWrite':
        todos = input_data.get('todos', [])
        return f'{emoji} TodoWrite: {len(todos)} items'

    if tool_name == 'AskUserQuestion':
        return f'{emoji} AskUserQuestion'

    if tool_name == 'Task':
        desc = input_data.get('description', '')
        return f'{emoji} Task: {desc}' if desc else f'{emoji} Task'

    return f'{emoji} {tool_name}'


def truncate_output(text: str, max_lines: int = 100, max_chars: int = 10000) -> tuple[str, bool]:
    """Truncate long output, return (truncated_text, was_truncated)."""
    lines = text.split('\n')
    truncated = False

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True

    result = '\n'.join(lines)

    if len(result) > max_chars:
        result = result[:max_chars]
        truncated = True

    return result, truncated


def render_message(msg: dict, tool_results: dict, collapsed: bool) -> str:
    """Render a single message to HTML."""
    msg_type = msg.get('type')
    timestamp = msg.get('timestamp', '')
    message = msg.get('message', {})

    if msg_type == 'user':
        content = message.get('content', '')

        # String content (user prompt)
        if isinstance(content, str):
            # Strip "Human: " prefix if present
            if content.startswith('Human: '):
                content = content[7:]

            ts_display = ''
            if timestamp:
                try:
                    dt = parse_timestamp(timestamp)
                    ts_display = f'<span class="timestamp">{dt.strftime("%H:%M:%S")}</span>'
                except:
                    pass

            return f'''
            <div class="message user">
                <div class="message-header">
                    <span class="role">User</span>
                    {ts_display}
                </div>
                <div class="content">{markdown_to_html(content)}</div>
            </div>
            '''

        # Array content (tool results) - these get paired with tool_use, skip standalone rendering
        return ''

    if msg_type == 'assistant':
        content = message.get('content', [])
        if not content:
            return ''

        ts_display = ''
        if timestamp:
            try:
                dt = parse_timestamp(timestamp)
                ts_display = f'<span class="timestamp">{dt.strftime("%H:%M:%S")}</span>'
            except:
                pass

        parts = []
        for block in content:
            block_type = block.get('type')

            if block_type == 'text':
                text = block.get('text', '')
                if text.strip():
                    parts.append(f'<div class="text-block">{markdown_to_html(text)}</div>')

            elif block_type == 'tool_use':
                tool_id = block.get('id', '')
                tool_name = block.get('name', '')
                tool_input = block.get('input', {})

                summary = escape_html(get_tool_summary(tool_name, tool_input))
                input_formatted = escape_html(format_tool_input(tool_name, tool_input))

                # Get paired result
                result_html = ''
                if tool_id in tool_results:
                    result = tool_results[tool_id]
                    result_content = result.get('content', '')
                    is_error = result.get('is_error', False)

                    if result_content:
                        truncated_content, was_truncated = truncate_output(str(result_content))
                        error_class = ' error' if is_error else ''
                        truncated_note = ' <span class="truncated">(truncated)</span>' if was_truncated else ''
                        result_html = f'''
                        <div class="tool-result{error_class}">
                            <div class="result-header">Output{truncated_note}</div>
                            <pre class="result-content">{escape_html(truncated_content)}</pre>
                        </div>
                        '''

                open_attr = '' if collapsed else ' open'
                parts.append(f'''
                <details class="tool-call"{open_attr}>
                    <summary>{summary}</summary>
                    <pre class="tool-input">{input_formatted}</pre>
                    {result_html}
                </details>
                ''')

        if not parts:
            return ''

        return f'''
        <div class="message assistant">
            <div class="message-header">
                <span class="role">Assistant</span>
                {ts_display}
            </div>
            <div class="content">
                {''.join(parts)}
            </div>
        </div>
        '''

    # Progress, system, queue-operation messages
    if msg_type == 'progress':
        content = msg.get('content', {})
        operation = content.get('operation', '')
        tool = content.get('tool', '')
        ts_display = ''
        if timestamp:
            try:
                dt = parse_timestamp(timestamp)
                ts_display = f'<span class="timestamp">{dt.strftime("%H:%M:%S")}</span>'
            except:
                pass
        return f'''
        <div class="message system-msg progress-msg">
            <div class="message-header">
                <span class="role">Progress</span>
                {ts_display}
            </div>
            <div class="content"><code>{escape_html(tool)}: {escape_html(operation)}</code></div>
        </div>
        '''

    if msg_type == 'system':
        content = msg.get('message', msg.get('content', ''))
        if isinstance(content, dict):
            content = json.dumps(content, indent=2)
        ts_display = ''
        if timestamp:
            try:
                dt = parse_timestamp(timestamp)
                ts_display = f'<span class="timestamp">{dt.strftime("%H:%M:%S")}</span>'
            except:
                pass
        return f'''
        <div class="message system-msg">
            <div class="message-header">
                <span class="role">System</span>
                {ts_display}
            </div>
            <div class="content"><pre>{escape_html(str(content))}</pre></div>
        </div>
        '''

    if msg_type == 'queue-operation':
        return ''  # Usually not useful to display

    return ''


def generate_html(messages: list, session_id: str, collapsed: bool) -> str:
    """Generate complete HTML page."""

    # Extract tool results from user messages
    tool_results = {}
    for msg in messages:
        if msg.get('type') == 'user':
            content = msg.get('message', {}).get('content', [])
            if isinstance(content, list):
                for item in content:
                    if item.get('type') == 'tool_result':
                        tool_results[item.get('tool_use_id', '')] = item

    # Get date range
    timestamps = []
    for msg in messages:
        ts = msg.get('timestamp')
        if ts:
            try:
                timestamps.append(parse_timestamp(ts))
            except:
                pass

    date_range = ''
    if timestamps:
        start = min(timestamps)
        end = max(timestamps)
        if start.date() == end.date():
            date_range = f'{start.strftime("%Y-%m-%d %H:%M")} - {end.strftime("%H:%M")}'
        else:
            date_range = f'{start.strftime("%Y-%m-%d %H:%M")} - {end.strftime("%Y-%m-%d %H:%M")}'

    # Render messages
    rendered_messages = []
    for msg in messages:
        html_content = render_message(msg, tool_results, collapsed)
        if html_content:
            rendered_messages.append(html_content)

    css = '''
        /* Dark theme (default) */
        :root {
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --bg-tertiary: #010409;
            --bg-elevated: #21262d;
            --text-primary: #e6edf3;
            --text-secondary: #8b949e;
            --text-muted: #6e7681;
            --accent: #58a6ff;
            --accent-emphasis: #1f6feb;
            --accent-subtle: rgba(56, 139, 253, 0.15);
            --user-bg: #0d1117;
            --user-border: #1f6feb;
            --assistant-bg: #161b22;
            --assistant-border: #30363d;
            --border: #30363d;
            --border-subtle: #21262d;
            --error: #f85149;
            --error-subtle: rgba(248, 81, 73, 0.15);
            --success: #3fb950;
            --success-subtle: rgba(63, 185, 80, 0.15);
            --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
            --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.4);
            --shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.5);
            --radius-sm: 6px;
            --radius-md: 8px;
            --radius-lg: 12px;
        }

        /* Light theme */
        [data-theme="light"] {
            --bg-primary: #ffffff;
            --bg-secondary: #f6f8fa;
            --bg-tertiary: #ffffff;
            --bg-elevated: #ffffff;
            --text-primary: #1f2328;
            --text-secondary: #656d76;
            --text-muted: #8c959f;
            --accent: #0969da;
            --accent-emphasis: #0550ae;
            --accent-subtle: rgba(9, 105, 218, 0.1);
            --user-bg: #f6f8fa;
            --user-border: #0969da;
            --assistant-bg: #ffffff;
            --assistant-border: #d0d7de;
            --border: #d0d7de;
            --border-subtle: #eaeef2;
            --error: #cf222e;
            --error-subtle: rgba(207, 34, 46, 0.1);
            --success: #1a7f37;
            --success-subtle: rgba(26, 127, 55, 0.1);
            --shadow-sm: 0 1px 2px rgba(31, 35, 40, 0.04);
            --shadow-md: 0 4px 12px rgba(31, 35, 40, 0.08);
            --shadow-lg: 0 8px 24px rgba(31, 35, 40, 0.12);
        }

        * {
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif;
            background: var(--bg-tertiary);
            color: var(--text-primary);
            margin: 0;
            padding: 0;
            line-height: 1.6;
            font-size: 15px;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
            transition: background-color 0.2s ease, color 0.2s ease;
        }

        header {
            background: var(--bg-secondary);
            padding: 1.25rem 2rem;
            border-bottom: 1px solid var(--border);
            position: sticky;
            top: 0;
            z-index: 100;
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: var(--shadow-sm);
        }

        header .header-content {
            display: flex;
            flex-direction: column;
        }

        header h1 {
            margin: 0;
            font-size: 1.25rem;
            font-weight: 600;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        header h1::before {
            content: '';
            display: inline-block;
            width: 24px;
            height: 24px;
            background: linear-gradient(135deg, var(--accent) 0%, var(--accent-emphasis) 100%);
            border-radius: 6px;
        }

        header .meta {
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-top: 0.35rem;
        }

        .theme-toggle {
            background: var(--bg-elevated);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            padding: 0.5rem 0.75rem;
            cursor: pointer;
            color: var(--text-secondary);
            font-size: 0.85rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            transition: all 0.15s ease;
        }

        .theme-toggle:hover {
            background: var(--accent-subtle);
            border-color: var(--accent);
            color: var(--accent);
        }

        .theme-toggle svg {
            width: 16px;
            height: 16px;
        }

        .conversation {
            max-width: 960px;
            margin: 0 auto;
            padding: 1.5rem;
        }

        .message {
            margin-bottom: 1.5rem;
            border-radius: var(--radius-lg);
            overflow: hidden;
            box-shadow: var(--shadow-sm);
            transition: transform 0.15s ease, box-shadow 0.15s ease;
            animation: messageSlideIn 0.3s ease-out;
        }

        @keyframes messageSlideIn {
            from {
                opacity: 0;
                transform: translateY(8px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .message:hover {
            box-shadow: var(--shadow-md);
        }

        .message.user {
            background: var(--user-bg);
            border: 1px solid var(--user-border);
            border-left: 3px solid var(--user-border);
        }

        .message.assistant {
            background: var(--assistant-bg);
            border: 1px solid var(--assistant-border);
            border-left: 3px solid var(--accent);
        }

        .message.system-msg {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            opacity: 0.75;
            font-size: 0.85rem;
        }

        .message.system-msg.progress-msg {
            opacity: 0.6;
        }

        .message-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 1.25rem;
            background: rgba(0, 0, 0, 0.05);
            border-bottom: 1px solid var(--border-subtle);
        }

        [data-theme="light"] .message-header {
            background: rgba(0, 0, 0, 0.02);
        }

        .message-header .role {
            font-weight: 600;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .message.user .role {
            color: var(--accent);
        }

        .message.assistant .role {
            color: var(--success);
        }

        .role-icon {
            width: 18px;
            height: 18px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.7rem;
        }

        .message.user .role-icon {
            background: var(--accent-subtle);
            color: var(--accent);
        }

        .message.assistant .role-icon {
            background: var(--success-subtle);
            color: var(--success);
        }

        .timestamp {
            font-size: 0.75rem;
            color: var(--text-muted);
            font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
            font-variant-numeric: tabular-nums;
        }

        .content {
            padding: 1.25rem;
        }

        .content p {
            margin: 0 0 0.75rem 0;
        }

        .content p:last-child {
            margin-bottom: 0;
        }

        .content h1, .content h2, .content h3, .content h4, .content h5, .content h6 {
            margin: 1.25rem 0 0.75rem 0;
            color: var(--text-primary);
            font-weight: 600;
            line-height: 1.3;
        }

        .content h1 { font-size: 1.5rem; }
        .content h2 { font-size: 1.3rem; }
        .content h3 { font-size: 1.15rem; }
        .content h4 { font-size: 1rem; }

        .content h1:first-child, .content h2:first-child, .content h3:first-child {
            margin-top: 0;
        }

        .content ul, .content ol {
            margin: 0.75rem 0;
            padding-left: 1.75rem;
        }

        .content li {
            margin: 0.35rem 0;
        }

        .content code {
            background: var(--bg-elevated);
            padding: 0.2rem 0.5rem;
            border-radius: var(--radius-sm);
            font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', 'Consolas', monospace;
            font-size: 0.875em;
            border: 1px solid var(--border-subtle);
        }

        .content pre {
            background: var(--bg-primary);
            padding: 1rem 1.25rem;
            border-radius: var(--radius-md);
            overflow-x: auto;
            margin: 1rem 0;
            border: 1px solid var(--border);
            box-shadow: var(--shadow-sm);
        }

        .content pre code {
            background: none;
            padding: 0;
            font-size: 0.85rem;
            line-height: 1.6;
            border: none;
        }

        .content a {
            color: var(--accent);
            text-decoration: none;
            border-bottom: 1px solid transparent;
            transition: border-color 0.15s ease;
        }

        .content a:hover {
            border-bottom-color: var(--accent);
        }

        .content strong {
            font-weight: 600;
            color: var(--text-primary);
        }

        .text-block {
            margin-bottom: 1rem;
        }

        .text-block:last-child {
            margin-bottom: 0;
        }

        details.tool-call {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: var(--radius-md);
            margin: 1rem 0;
            overflow: hidden;
            box-shadow: var(--shadow-sm);
            transition: all 0.2s ease;
        }

        details.tool-call:hover {
            border-color: var(--accent);
        }

        details.tool-call summary {
            padding: 0.75rem 1rem;
            cursor: pointer;
            font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
            font-size: 0.85rem;
            background: var(--bg-elevated);
            color: var(--accent);
            user-select: none;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            transition: all 0.15s ease;
        }

        details.tool-call summary::before {
            content: '▶';
            font-size: 0.65rem;
            transition: transform 0.2s ease;
        }

        details.tool-call[open] summary::before {
            transform: rotate(90deg);
        }

        details.tool-call summary::-webkit-details-marker {
            display: none;
        }

        details.tool-call summary:hover {
            background: var(--accent-subtle);
        }

        details.tool-call[open] summary {
            border-bottom: 1px solid var(--border);
        }

        .tool-input {
            margin: 0;
            padding: 1rem 1.25rem;
            background: var(--bg-primary);
            font-size: 0.8rem;
            font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
            border-bottom: 1px solid var(--border);
            white-space: pre-wrap;
            word-break: break-word;
            line-height: 1.5;
        }

        .tool-result {
            border-top: 1px solid var(--border);
        }

        .tool-result.error {
            background: var(--error-subtle);
        }

        .result-header {
            padding: 0.5rem 1.25rem;
            font-size: 0.7rem;
            font-weight: 600;
            color: var(--text-muted);
            background: var(--bg-elevated);
            text-transform: uppercase;
            letter-spacing: 0.08em;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .tool-result.error .result-header {
            color: var(--error);
            background: var(--error-subtle);
        }

        .truncated {
            color: var(--text-muted);
            font-style: italic;
            text-transform: none;
            font-weight: 400;
        }

        .result-content {
            margin: 0;
            padding: 1rem 1.25rem;
            background: var(--bg-primary);
            font-size: 0.8rem;
            font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
            max-height: 500px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-break: break-word;
            line-height: 1.5;
        }

        /* Syntax highlighting integration */
        .hljs {
            background: transparent !important;
            padding: 0 !important;
        }

        /* Scrollbar styling */
        ::-webkit-scrollbar {
            width: 10px;
            height: 10px;
        }

        ::-webkit-scrollbar-track {
            background: var(--bg-tertiary);
            border-radius: 5px;
        }

        ::-webkit-scrollbar-thumb {
            background: var(--border);
            border-radius: 5px;
            border: 2px solid var(--bg-tertiary);
        }

        ::-webkit-scrollbar-thumb:hover {
            background: var(--text-muted);
        }

        /* Firefox scrollbar */
        * {
            scrollbar-width: thin;
            scrollbar-color: var(--border) var(--bg-tertiary);
        }

        /* Print styles */
        @media print {
            header {
                position: static;
            }
            .theme-toggle {
                display: none;
            }
            .message {
                break-inside: avoid;
                box-shadow: none;
                border: 1px solid #ccc;
            }
        }

        /* Responsive */
        @media (max-width: 768px) {
            header {
                padding: 1rem;
                flex-direction: column;
                align-items: flex-start;
                gap: 0.75rem;
            }
            .conversation {
                padding: 1rem;
            }
            .content {
                padding: 1rem;
            }
        }
    '''

    js = '''
        // Theme toggle functionality
        (function() {
            const themeToggle = document.getElementById('theme-toggle');
            const html = document.documentElement;

            // Check for saved theme preference or system preference
            function getPreferredTheme() {
                const saved = localStorage.getItem('theme');
                if (saved) return saved;
                return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
            }

            function setTheme(theme) {
                html.setAttribute('data-theme', theme);
                localStorage.setItem('theme', theme);
                updateToggleIcon(theme);
            }

            function updateToggleIcon(theme) {
                const sunIcon = themeToggle.querySelector('.sun-icon');
                const moonIcon = themeToggle.querySelector('.moon-icon');
                const label = themeToggle.querySelector('.theme-label');
                if (theme === 'light') {
                    sunIcon.style.display = 'none';
                    moonIcon.style.display = 'block';
                    label.textContent = 'Dark';
                } else {
                    sunIcon.style.display = 'block';
                    moonIcon.style.display = 'none';
                    label.textContent = 'Light';
                }
            }

            // Initialize theme
            setTheme(getPreferredTheme());

            // Toggle on click
            themeToggle.addEventListener('click', function() {
                const current = html.getAttribute('data-theme') || 'dark';
                setTheme(current === 'dark' ? 'light' : 'dark');
            });

            // Listen for system preference changes
            window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', function(e) {
                if (!localStorage.getItem('theme')) {
                    setTheme(e.matches ? 'light' : 'dark');
                }
            });
        })();

        // Initialize syntax highlighting
        document.addEventListener('DOMContentLoaded', function() {
            document.querySelectorAll('pre code').forEach(function(block) {
                hljs.highlightElement(block);
            });
        });
    '''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Claude Code Session - {escape_html(session_id)}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css" id="hljs-dark">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css" id="hljs-light" disabled>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
    <style>{css}</style>
    <script>
        // Theme-aware highlight.js stylesheet switching
        (function() {{
            function updateHljsTheme(theme) {{
                document.getElementById('hljs-dark').disabled = theme === 'light';
                document.getElementById('hljs-light').disabled = theme === 'dark';
            }}
            // Watch for theme changes
            const observer = new MutationObserver(function(mutations) {{
                mutations.forEach(function(mutation) {{
                    if (mutation.attributeName === 'data-theme') {{
                        updateHljsTheme(document.documentElement.getAttribute('data-theme') || 'dark');
                    }}
                }});
            }});
            observer.observe(document.documentElement, {{ attributes: true }});
            // Initial state
            updateHljsTheme(document.documentElement.getAttribute('data-theme') || 'dark');
        }})();
    </script>
</head>
<body>
    <header>
        <div class="header-content">
            <h1>Claude Code Session</h1>
            <div class="meta">
                <span>Session: {escape_html(session_id)}</span>
                {f' &middot; <span>{escape_html(date_range)}</span>' if date_range else ''}
            </div>
        </div>
        <button class="theme-toggle" id="theme-toggle" aria-label="Toggle theme">
            <svg class="sun-icon" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="5"></circle>
                <line x1="12" y1="1" x2="12" y2="3"></line>
                <line x1="12" y1="21" x2="12" y2="23"></line>
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
                <line x1="1" y1="12" x2="3" y2="12"></line>
                <line x1="21" y1="12" x2="23" y2="12"></line>
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
            </svg>
            <svg class="moon-icon" style="display:none" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
            </svg>
            <span class="theme-label">Light</span>
        </button>
    </header>
    <div class="conversation">
        {''.join(rendered_messages)}
    </div>
    <script>{js}</script>
</body>
</html>'''


def main():
    parser = argparse.ArgumentParser(
        description='Convert Claude Code session JSONL files to shareable HTML pages.'
    )
    parser.add_argument('input', help='Input JSONL file')
    parser.add_argument('-o', '--output', help='Output HTML file (default: <sessionId>.html)')
    parser.add_argument('--collapsed', action='store_true', default=True,
                        help='Tool calls collapsed by default (default)')
    parser.add_argument('--expanded', action='store_true',
                        help='Tool calls expanded by default')
    parser.add_argument('--show-progress', action='store_true',
                        help='Include progress messages (hidden by default)')
    parser.add_argument('--show-system', action='store_true',
                        help='Include system messages (hidden by default)')
    parser.add_argument('--show-all', action='store_true',
                        help='Include all message types (progress, system, queue)')

    args = parser.parse_args()

    # Handle collapsed/expanded
    collapsed = not args.expanded

    # Set skip flags (skip by default, unless --show-* is passed)
    skip_progress = not args.show_progress and not args.show_all
    skip_system = not args.show_system and not args.show_all
    skip_queue = not args.show_all  # queue-operation is rarely useful

    # Read and parse JSONL
    input_path = Path(args.input)
    if not input_path.exists():
        print(f'Error: File not found: {args.input}', file=sys.stderr)
        sys.exit(1)

    messages = []
    session_id = input_path.stem

    with open(input_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                msg_type = msg.get('type', '')

                # Apply filters
                if skip_progress and msg_type == 'progress':
                    continue
                if skip_system and msg_type == 'system':
                    continue
                if skip_queue and msg_type == 'queue-operation':
                    continue

                messages.append(msg)
            except json.JSONDecodeError as e:
                print(f'Warning: Invalid JSON on line {line_num}: {e}', file=sys.stderr)

    if not messages:
        print('Error: No valid messages found in file', file=sys.stderr)
        sys.exit(1)

    # Sort by timestamp
    messages.sort(key=lambda m: m.get('timestamp', ''))

    # Generate HTML
    html_content = generate_html(messages, session_id, collapsed)

    # Write output
    output_path = Path(args.output) if args.output else Path(f'{session_id}.html')
    output_path.write_text(html_content, encoding='utf-8')

    print(f'Generated: {output_path}')
    print(f'Messages: {len(messages)}')


if __name__ == '__main__':
    main()
