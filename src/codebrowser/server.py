#!/usr/bin/env python3
"""
Local Code Browser - GitHub-style file/code navigator.
Usage: python3 code_browser.py [directory] [--port PORT]
"""

import http.server
import json
import os
import sys
import mimetypes
import urllib.parse
import threading
import time
import hashlib
ROOT_DIR = os.getcwd()
PORT = 8888

IGNORED = {'.git', 'node_modules', '__pycache__', '.DS_Store', '.idea', '.vscode', 'vendor', '.gradle', 'build', 'dist', '.next'}

LANG_MAP = {
    '.py': 'python', '.js': 'javascript', '.ts': 'typescript', '.tsx': 'tsx',
    '.jsx': 'jsx', '.java': 'java', '.go': 'go', '.rs': 'rust', '.rb': 'ruby',
    '.c': 'c', '.cpp': 'cpp', '.h': 'c', '.hpp': 'cpp', '.cs': 'csharp',
    '.swift': 'swift', '.kt': 'kotlin', '.scala': 'scala', '.php': 'php',
    '.sh': 'bash', '.zsh': 'bash', '.bash': 'bash', '.fish': 'bash',
    '.html': 'xml', '.htm': 'xml', '.xml': 'xml', '.svg': 'xml',
    '.css': 'css', '.scss': 'scss', '.less': 'less', '.sass': 'scss',
    '.json': 'json', '.yaml': 'yaml', '.yml': 'yaml', '.toml': 'ini',
    '.ini': 'ini', '.cfg': 'ini', '.conf': 'ini', '.properties': 'properties',
    '.md': 'markdown', '.markdown': 'markdown', '.rst': 'plaintext',
    '.sql': 'sql', '.graphql': 'graphql', '.gql': 'graphql',
    '.dockerfile': 'dockerfile', '.proto': 'protobuf', '.gradle': 'gradle',
    '.groovy': 'groovy', '.lua': 'lua', '.r': 'r', '.R': 'r',
    '.m': 'objectivec', '.mm': 'objectivec', '.pl': 'perl',
    '.ex': 'elixir', '.exs': 'elixir', '.erl': 'erlang', '.hs': 'haskell',
    '.tf': 'hcl', '.vue': 'xml', '.dart': 'dart', '.zig': 'zig',
    '.makefile': 'makefile', '.cmake': 'cmake',
}

SPECIAL_FILES = {
    'Makefile': 'makefile', 'Dockerfile': 'dockerfile', 'Jenkinsfile': 'groovy',
    'Vagrantfile': 'ruby', 'Gemfile': 'ruby', 'Rakefile': 'ruby',
    'CMakeLists.txt': 'cmake', '.gitignore': 'plaintext', '.env': 'bash',
    'go.mod': 'go', 'go.sum': 'plaintext', 'Cargo.toml': 'toml',
    'Cargo.lock': 'toml', 'pom.xml': 'xml', 'build.gradle': 'gradle',
    'build.gradle.kts': 'kotlin',
}

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.svg'}


# ── File watcher ──────────────────────────────────────────────────────────────

class FileWatcher:
    """Watches ROOT_DIR for file changes using mtime snapshots."""

    def __init__(self, root, interval=1.5):
        self.root = root
        self.interval = interval
        self._snapshot = {}
        self._lock = threading.Lock()
        self._change_id = 0
        self._take_snapshot()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _take_snapshot(self):
        """Build a dict of {relative_path: mtime} for all non-ignored files."""
        snap = {}
        for dirpath, dirnames, filenames in os.walk(self.root):
            # Filter ignored directories in-place
            dirnames[:] = [d for d in dirnames if d not in IGNORED]
            for fname in filenames:
                if fname in IGNORED:
                    continue
                full = os.path.join(dirpath, fname)
                try:
                    snap[full] = os.path.getmtime(full)
                except OSError:
                    pass
        return snap

    def _run(self):
        while True:
            time.sleep(self.interval)
            new_snap = self._take_snapshot()
            if new_snap != self._snapshot:
                with self._lock:
                    self._snapshot = new_snap
                    self._change_id += 1

    @property
    def change_id(self):
        with self._lock:
            return self._change_id


watcher = None  # initialized in main()


def get_html_template():
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        return f.read()


class BrowseHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def get_safe_path(self, rel_path):
        if not rel_path:
            return ROOT_DIR
        full = os.path.normpath(os.path.join(ROOT_DIR, rel_path))
        if not full.startswith(ROOT_DIR):
            return None
        return full

    def is_binary(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                chunk = f.read(8192)
                return b'\x00' in chunk
        except Exception:
            return True

    def get_language(self, filepath):
        name = os.path.basename(filepath)
        if name in SPECIAL_FILES:
            return SPECIAL_FILES[name]
        ext = os.path.splitext(name)[1].lower()
        return LANG_MAP.get(ext, 'plaintext')

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == '/' or path == '':
            self.send_html(get_html_template())
            return

        if path == '/api/info':
            name = os.path.basename(ROOT_DIR) or 'root'
            self.send_json({'name': name, 'root': ROOT_DIR})
            return

        if path == '/api/changes':
            self.send_json({'change_id': watcher.change_id if watcher else 0})
            return

        if path == '/api/browse':
            rel = params.get('path', [''])[0]
            full = self.get_safe_path(rel)
            if not full or not os.path.exists(full):
                self.send_json({'error': 'Path not found'}, 404)
                return

            if os.path.isdir(full):
                entries = []
                try:
                    for item in os.listdir(full):
                        if item in IGNORED:
                            continue
                        item_path = os.path.join(full, item)
                        is_dir = os.path.isdir(item_path)
                        size = 0 if is_dir else os.path.getsize(item_path)
                        entries.append({
                            'name': item,
                            'is_dir': is_dir,
                            'size': size,
                        })
                except PermissionError:
                    self.send_json({'error': 'Permission denied'}, 403)
                    return
                self.send_json({'type': 'directory', 'entries': entries})
            else:
                ext = os.path.splitext(full)[1].lower()
                size = os.path.getsize(full)
                is_image = ext in IMAGE_EXTENSIONS
                is_bin = not is_image and self.is_binary(full)
                lang = self.get_language(full)
                content = ''
                lines = 0

                if not is_bin and not is_image:
                    try:
                        with open(full, 'r', encoding='utf-8', errors='replace') as f:
                            content = f.read()
                        lines = content.count('\n') + (1 if content and not content.endswith('\n') else 0)
                    except Exception:
                        is_bin = True

                self.send_json({
                    'type': 'file',
                    'content': content,
                    'lines': lines,
                    'size': size,
                    'language': lang,
                    'is_binary': is_bin,
                    'is_image': is_image,
                })
            return

        if path == '/api/raw':
            rel = params.get('path', [''])[0]
            full = self.get_safe_path(rel)
            if not full or not os.path.exists(full):
                self.send_response(404)
                self.end_headers()
                return
            mime, _ = mimetypes.guess_type(full)
            mime = mime or 'application/octet-stream'
            size = os.path.getsize(full)
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(size))
            self.end_headers()
            with open(full, 'rb') as f:
                self.wfile.write(f.read())
            return

        self.send_response(404)
        self.end_headers()


def cmd_help():
    print("""Usage: codebrowser [directory] [options]

Options:
  --port PORT       Port to listen on (default: 8888)
  --help, -h        Show this help message

Examples:
  codebrowser                          Browse current directory
  codebrowser /path/to/project         Browse a specific directory
  codebrowser /path/to/project --port 3000
""")



def main():
    global ROOT_DIR, PORT, watcher
    args = sys.argv[1:]
    help_ = False
    i = 0
    while i < len(args):
        if args[i] == '--port' and i + 1 < len(args):
            PORT = int(args[i + 1])
            i += 2
        elif args[i] in ('--help', '-h'):
            help_ = True
            i += 1
        elif not args[i].startswith('-'):
            ROOT_DIR = os.path.abspath(args[i])
            i += 1
        else:
            i += 1

    if help_:
        cmd_help()
        return

    if not os.path.isdir(ROOT_DIR):
        print(f"Error: '{ROOT_DIR}' is not a valid directory.")
        sys.exit(1)

    # Start file watcher
    watcher = FileWatcher(ROOT_DIR)

    import socket
    server = http.server.HTTPServer(('127.0.0.1', PORT), BrowseHandler)
    server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    print(f"\n  Code Browser")
    print(f"  Browsing: {ROOT_DIR}")
    print(f"  URL:      http://localhost:{PORT}")
    print(f"  Live reload: enabled\n")
    print(f"  Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == '__main__':
    main()
