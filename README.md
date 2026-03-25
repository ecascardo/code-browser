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
pip install git+https://github.com/ecascardo/code-browser.git
```

### From source

```bash
pip install .
```

This installs the `codebrowser` command globally.

To install in development mode (changes to source take effect immediately):

```bash
pip install -e .
```

## Usage

```bash
# Browse the current directory
codebrowser

# Browse a specific directory
codebrowser /path/to/your/project

# Use a custom port (default: 8080)
codebrowser /path/to/your/project --port 3000
```

Then open `http://localhost:8080` (or your chosen port) in your browser.

You can also run it as a Python module:

```bash
python -m codebrowser /path/to/your/project
```

Press `Ctrl+C` to stop the server.

## Ignored directories

The following directories are excluded from the file listing:

`.git`, `node_modules`, `__pycache__`, `.DS_Store`, `.idea`, `.vscode`, `vendor`, `.gradle`, `build`, `dist`, `.next`

## Uninstall

```bash
pip uninstall codebrowser
```
