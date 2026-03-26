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
import subprocess
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


def get_git_status(root):
    """Returns dict mapping relative filepath -> simplified git status (M/A/D)."""
    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return {}
        status_map = {}
        for line in result.stdout.splitlines():
            if len(line) < 4:
                continue
            x, y = line[0], line[1]
            filepath = line[3:]
            if ' -> ' in filepath:
                filepath = filepath.split(' -> ')[1]
            filepath = filepath.strip('"')
            if x == '?' and y == '?':
                status = 'A'
            elif x == 'D' or y == 'D':
                status = 'D'
            elif x == 'A' or y == 'A':
                status = 'A'
            else:
                status = 'M'
            status_map[filepath] = status
        return status_map
    except Exception:
        return {}


def get_current_branch(root):
    """Returns the current git branch name or empty string."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=root, capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else ''
    except Exception:
        return ''


def get_pr_info(root):
    """Returns (number, url, state) of the current branch's PR using gh CLI, or (None, None, None)."""
    try:
        result = subprocess.run(
            ['gh', 'pr', 'view', '--json', 'number,url,state'],
            cwd=root, capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get('number'), data.get('url', ''), data.get('state', '')
    except Exception:
        pass
    return None, None, None


def get_all_branches(root):
    """Returns list of local branch names."""
    try:
        result = subprocess.run(
            ['git', 'branch', '--format=%(refname:short)'],
            cwd=root, capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return []
        return [b.strip() for b in result.stdout.splitlines() if b.strip()]
    except Exception:
        return []


def get_base_branch(root):
    """Returns the name of the upstream base branch (develop/main/master) or None."""
    for branch in ['develop', 'main', 'master']:
        result = subprocess.run(
            ['git', 'rev-parse', '--verify', branch],
            cwd=root, capture_output=True, timeout=5
        )
        if result.returncode == 0:
            return branch
    return None


def get_merge_base(root, base_branch):
    """Returns the merge-base commit hash between HEAD and base_branch, or None."""
    try:
        result = subprocess.run(
            ['git', 'merge-base', 'HEAD', base_branch],
            cwd=root, capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def get_git_status_base(root, base_branch=None):
    """Returns (status_map, base_branch) where status_map maps filepath -> M/A/D vs base branch merge-base."""
    base = base_branch or get_base_branch(root)
    if not base:
        return {}, None
    merge_base = get_merge_base(root, base)
    if not merge_base:
        return {}, base
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-status', merge_base],
            cwd=root, capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return {}, base
        status_map = {}
        for line in result.stdout.splitlines():
            parts = line.split('\t')
            if len(parts) < 2:
                continue
            st = parts[0][0]
            filepath = parts[-1]
            if st == 'D':
                status_map[filepath] = 'D'
            elif st == 'A':
                status_map[filepath] = 'A'
            else:
                status_map[filepath] = 'M'
        return status_map, base
    except Exception:
        return {}, base


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
            base = get_base_branch(ROOT_DIR)
            branch = get_current_branch(ROOT_DIR)
            pr_number, pr_url, pr_state = get_pr_info(ROOT_DIR)
            self.send_json({
                'name': name,
                'root': ROOT_DIR,
                'base_branch': base or '',
                'current_branch': branch,
                'pr_number': pr_number,
                'pr_url': pr_url or '',
                'pr_state': pr_state or '',
            })
            return

        if path == '/api/changes':
            self.send_json({'change_id': watcher.change_id if watcher else 0})
            return

        if path == '/api/branches':
            all_branches = get_all_branches(ROOT_DIR)
            base_candidates = [b for b in ['develop', 'main', 'master'] if b in all_branches]
            self.send_json({'branches': base_candidates})
            return

        if path == '/api/browse':
            rel = params.get('path', [''])[0]
            base_override = params.get('base', [''])[0] or None
            full = self.get_safe_path(rel)
            if not full or not os.path.exists(full):
                self.send_json({'error': 'Path not found'}, 404)
                return

            if os.path.isdir(full):
                entries = []
                git_status = get_git_status(ROOT_DIR)
                git_status_base, base_branch = get_git_status_base(ROOT_DIR, base_override)
                priority = {'D': 3, 'M': 2, 'A': 1}
                # Prefix for entries in the current directory (relative to ROOT_DIR)
                dir_rel = rel.replace(os.sep, '/').strip('/')
                dir_prefix = (dir_rel + '/') if dir_rel else ''
                seen_names = set()
                try:
                    for item in os.listdir(full):
                        if item in IGNORED:
                            continue
                        item_path = os.path.join(full, item)
                        is_dir = os.path.isdir(item_path)
                        size = 0 if is_dir else os.path.getsize(item_path)
                        rel_item = os.path.relpath(item_path, ROOT_DIR).replace(os.sep, '/')
                        git_st = None
                        git_st_base = None
                        if is_dir:
                            prefix = rel_item + '/'
                            for k, v in git_status.items():
                                if k.startswith(prefix):
                                    if git_st is None or priority.get(v, 0) > priority.get(git_st, 0):
                                        git_st = v
                            for k, v in git_status_base.items():
                                if k.startswith(prefix):
                                    if git_st_base is None or priority.get(v, 0) > priority.get(git_st_base, 0):
                                        git_st_base = v
                        else:
                            git_st = git_status.get(rel_item)
                            git_st_base = git_status_base.get(rel_item)
                        seen_names.add(item)
                        entries.append({
                            'name': item,
                            'is_dir': is_dir,
                            'size': size,
                            'git_status': git_st,
                            'git_status_base': git_st_base,
                        })
                except PermissionError:
                    self.send_json({'error': 'Permission denied'}, 403)
                    return
                # Add deleted files tracked by git that no longer exist on disk
                all_deleted = {p: s for p, s in {**git_status_base, **git_status}.items() if s == 'D'}
                for git_path, git_st in all_deleted.items():
                    if not git_path.startswith(dir_prefix):
                        continue
                    remainder = git_path[len(dir_prefix):]
                    if '/' in remainder:
                        continue  # belongs to a subdirectory, not direct child
                    if remainder in seen_names:
                        continue
                    entries.append({
                        'name': remainder,
                        'is_dir': False,
                        'size': 0,
                        'git_status': git_status.get(git_path),
                        'git_status_base': git_status_base.get(git_path),
                    })
                self.send_json({'type': 'directory', 'entries': entries, 'base_branch': base_branch or ''})
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

                rel_file = os.path.relpath(full, ROOT_DIR).replace(os.sep, '/')
                git_st = get_git_status(ROOT_DIR).get(rel_file)
                git_status_base, base_branch = get_git_status_base(ROOT_DIR, base_override)
                git_st_base = git_status_base.get(rel_file)
                self.send_json({
                    'type': 'file',
                    'content': content,
                    'lines': lines,
                    'size': size,
                    'language': lang,
                    'is_binary': is_bin,
                    'is_image': is_image,
                    'git_status': git_st,
                    'git_status_base': git_st_base,
                    'base_branch': base_branch or '',
                })
            return

        if path == '/api/diff':
            rel = params.get('path', [''])[0]
            mode = params.get('mode', ['local'])[0]
            base_override = params.get('base', [''])[0] or None
            full = self.get_safe_path(rel)
            if not full:
                self.send_json({'error': 'Invalid path'}, 400)
                return
            try:
                if mode == 'base':
                    base = base_override or get_base_branch(ROOT_DIR)
                    if not base:
                        self.send_json({'diff': '', 'info': 'No base branch found'})
                        return
                    merge_base = get_merge_base(ROOT_DIR, base)
                    if not merge_base:
                        self.send_json({'diff': ''})
                        return
                    result = subprocess.run(
                        ['git', 'diff', merge_base, '--', rel],
                        cwd=ROOT_DIR, capture_output=True, text=True, timeout=10
                    )
                else:
                    result = subprocess.run(
                        ['git', 'diff', 'HEAD', '--', rel],
                        cwd=ROOT_DIR, capture_output=True, text=True, timeout=10
                    )
                self.send_json({'diff': result.stdout})
            except Exception as e:
                self.send_json({'error': str(e)}, 500)
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


CLAUDE_SKILL_CONTENT = """\
Launch the Code Browser web server for browsing source code.

Run `codebrowser $ARGUMENTS` using the Bash tool in the background.
If no directory argument is given, use the current working directory.
After starting, tell the user the URL (default: http://localhost:8888) and remind them to press Ctrl+C to stop the server.
"""


def cmd_install_claude(silent=False):
    commands_dir = os.path.expanduser("~/.claude/commands")
    os.makedirs(commands_dir, exist_ok=True)
    skill_path = os.path.join(commands_dir, "codebrowser.md")
    try:
        with open(skill_path, "r", encoding="utf-8") as f:
            current = f.read()
    except FileNotFoundError:
        current = None
    if current == CLAUDE_SKILL_CONTENT:
        return
    with open(skill_path, "w", encoding="utf-8") as f:
        f.write(CLAUDE_SKILL_CONTENT)
    if not silent:
        print(f"Skill installed: {skill_path}")
        print("Use /codebrowser inside Claude Code to launch the browser.")


def cmd_uninstall_claude():
    skill_path = os.path.expanduser("~/.claude/commands/codebrowser.md")
    if os.path.exists(skill_path):
        os.remove(skill_path)
        print(f"Skill removed: {skill_path}")
    else:
        print("Claude Code skill not found, nothing to remove.")


def cmd_help():
    print("""Usage: codebrowser [directory] [options]

Options:
  --port PORT         Port to listen on (default: 8888)
  --uninstall_claude  Remove the /codebrowser skill from Claude Code
  --help, -h          Show this help message

Examples:
  codebrowser                          Browse current directory
  codebrowser /path/to/project         Browse a specific directory
  codebrowser /path/to/project --port 3000
  codebrowser --uninstall_claude       Remove Claude Code skill
""")



def uninstall_main():
    cmd_uninstall_claude()
    import subprocess
    result = subprocess.run(["pipx", "uninstall", "codebrowser"])
    sys.exit(result.returncode)


def main():
    global ROOT_DIR, PORT, watcher
    args = sys.argv[1:]
    help_ = False
    uninstall_claude = False
    i = 0
    while i < len(args):
        if args[i] == '--port' and i + 1 < len(args):
            PORT = int(args[i + 1])
            i += 2
        elif args[i] in ('--help', '-h'):
            help_ = True
            i += 1
        elif args[i] == '--uninstall_claude':
            uninstall_claude = True
            i += 1
        elif not args[i].startswith('-'):
            ROOT_DIR = os.path.abspath(args[i])
            i += 1
        else:
            i += 1

    if help_:
        cmd_help()
        return

    if uninstall_claude:
        cmd_uninstall_claude()
        return

    try:
        cmd_install_claude(silent=True)
    except Exception:
        pass

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
