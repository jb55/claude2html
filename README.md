# claude2html

[example][example]

Convert Claude Code session logs to shareable HTML pages.

Claude Code stores conversation history in JSONL files. This tool converts those logs into clean, readable HTML that you can share or archive.

## Features

- **Clean conversation view** - Messages grouped by role with timestamps
- **Tool call visualization** - Expandable sections showing tool inputs and outputs
- **Dark/light theme** - Toggle between themes, respects system preference
- **Syntax highlighting** - Code blocks highlighted via highlight.js
- **Responsive design** - Works on desktop and mobile
- **Self-contained output** - Single HTML file with no external dependencies (except CDN for highlight.js)

## Installation

```bash
# Clone the repository
git clone https://github.com/jb55/claude2html.git
cd claude2html

# No dependencies required - uses only Python standard library
```

## Usage

```bash
# Basic usage
./claude2html.py session.jsonl

# Specify output file
./claude2html.py session.jsonl -o conversation.html

# Show tool calls expanded by default
./claude2html.py session.jsonl --expanded

# Include progress messages (hidden by default)
./claude2html.py session.jsonl --show-progress

# Include system messages (hidden by default)
./claude2html.py session.jsonl --show-system

# Include all message types
./claude2html.py session.jsonl --show-all
```

## Finding Claude Code Session Files

Claude Code stores sessions in:

```
~/.claude/projects/<project-path-hash>/<session-id>.jsonl
```

You can find recent sessions with:

```bash
find ~/.claude -name "*.jsonl" -mtime -1
```

## Example Output

The generated HTML includes:

- Header with session ID and date range
- User messages with blue accent
- Assistant messages with green accent
- Collapsible tool calls showing:
  - Tool name and summary
  - Full input parameters
  - Output/results (truncated if very long)
- Theme toggle button

## Options

| Flag | Description |
|------|-------------|
| `-o, --output` | Output HTML file (default: `<sessionId>.html`) |
| `--collapsed` | Tool calls collapsed by default (default) |
| `--expanded` | Tool calls expanded by default |
| `--show-progress` | Include progress messages |
| `--show-system` | Include system messages |
| `--show-all` | Include all message types |

## Requirements

- Python 3.7+
- No external dependencies

## License

MIT License - see [LICENSE](LICENSE) for details.

[example]: https://jb55.com/s/c99bf661-acf3-4913-9cb9-8dc42a7f2250.html
