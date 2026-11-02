"""Offline heuristic scan; prints locations/types only, never matching values.

Scans reachable local Git blobs plus current tracked and unignored files. Compares
local .env credential values without printing them. Does not scan databases.
"""
import re
import subprocess
from pathlib import Path
from dotenv import dotenv_values


def git(*args):
    return subprocess.check_output(['git', *args])


PATTERNS = {
    'OpenAI-shaped key': rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}',
    'Discord-shaped token': rb'\b[A-Za-z0-9_-]{23,28}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{25,}',
    'GitHub-shaped token': rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})',
    'AWS-shaped key': rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'private key': rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'credential-bearing URL': rb'\w+://[^\s:/]+:[^\s/@]+@',
    'literal credential assignment': rb'''(?im)(?:api_key|password|secret|bot_token|access_token)\s*[=:]\s*["'][^"'\r\n]{16,}["']''',
}


def main():
    local = dotenv_values('.env') if Path('.env').exists() else {}
    credentials = [v.encode() for k, v in local.items()
                   if v and len(v) >= 16 and any(word in k.upper() for word in ('TOKEN', 'KEY', 'PASSWORD', 'SECRET'))]
    findings = set()
    count = 0

    def scan(data, location):
        nonlocal count
        count += 1
        for kind, pattern in PATTERNS.items():
            if re.search(pattern, data):
                findings.add((location, kind))
        if any(value in data for value in credentials):
            findings.add((location, 'matches local credential'))

    objects = git('rev-list', '--objects', '--all').decode().splitlines()
    for entry in objects:
        oid, _, path = entry.partition(' ')
        if git('cat-file', '-t', oid).strip() == b'blob':
            scan(git('cat-file', 'blob', oid), f'history:{oid[:12]}:{path}')
    paths = git('ls-files', '-z', '--cached', '--others', '--exclude-standard').decode().split('\0')
    for name in filter(None, paths):
        path = Path(name)
        if path.is_file() and path.suffix not in ('.db', '.sqlite', '.sqlite3'):
            scan(path.read_bytes(), f'worktree:{name}')
    print(f'Scanned {count} blob/file versions across all locally reachable refs and the worktree.')
    for location, kind in sorted(findings):
        print(f'REVIEW {kind}: {location}')
    print(f'{len(findings)} potential findings. Heuristic results require review; remote-only refs and deleted/unreachable objects are outside scope.')
    return bool(findings)


if __name__ == '__main__':
    raise SystemExit(main())
