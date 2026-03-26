# Code Browser

A local web application that lets you browse and read source code in your browser, with a GitHub-inspired UI. No editing, no execution — just navigation and reading.

## Features

- **File and folder navigation** with breadcrumbs, sorting (directories first), and a quick filter (press `/` to focus)
- **Syntax highlighting** for 50+ languages via highlight.js
- **Markdown preview** with a Code/Preview tab toggle, rendered with marked.js
- **Mermaid diagram rendering** inside markdown files (flowcharts, sequence diagrams, etc.)
- **Image preview** for PNG, JPG, SVG, GIF, and other common formats
- **Three themes**: Dark, Light, and Solarized — persisted across sessions via localStorage
- **Live reload**: automatically detects file changes and refreshes the current view
- **Keyboard shortcuts**: `/` to filter, `Escape` to clear, browser back/forward navigation
- **Zero dependencies**: only requires Python 3 (CDN-loaded JS libraries for the frontend)

## Installation

### From GitHub (no clone required)

```bash
pipx install git+https://github.com/ecascardo/code-browser.git --pip-args="--index-url https://pypi.org/simple/"
```

### From source

```bash
pipx install . --pip-args="--index-url https://pypi.org/simple/"
```

This installs the `codebrowser` command in an isolated environment.

To install in development mode (changes to source take effect immediately):

```bash
pipx install --editable . --pip-args="--index-url https://pypi.org/simple/"
```

## Usage

```bash
# Browse the current directory
codebrowser

# Browse a specific directory
codebrowser /path/to/your/project

# Use a custom port (default: 8888)
codebrowser --port 3000
```

Then open `http://localhost:8888` (or your chosen port) in your browser.

Press `Ctrl+C` to stop the server.

## Claude Code Skill

Code Browser includes a skill for [Claude Code](https://claude.ai/code) that lets you launch the server directly from the chat with the `/codebrowser` command.

The skill is installed automatically at package installation time, creating `~/.claude/commands/codebrowser.md`. The command will be available in all your Claude Code sessions.

### Usage

Inside Claude Code, type:

```
/codebrowser
```

Claude will launch the server in the background pointing to the current directory and show you the URL (`http://localhost:8888`).

You can also pass a directory as an argument:

```
/codebrowser /path/to/project
```

## Ignored directories

The following directories are excluded from the file listing:

`.git`, `node_modules`, `__pycache__`, `.DS_Store`, `.idea`, `.vscode`, `vendor`, `.gradle`, `build`, `dist`, `.next`

## Uninstall

```bash
codebrowser-uninstall
```

`codebrowser-uninstall` removes the `/codebrowser` skill from Claude Code and uninstalls the package.
