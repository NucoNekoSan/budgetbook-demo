from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from sensitive_patterns import is_text_file, load_secret_patterns, scan_text_for_patterns

REPO_ROOT = Path(__file__).resolve().parents[1]
SKIP_PREFIXES = (
    'budgetbook/.venv/',
    'budgetbook/staticfiles/',
    'budgetbook/dist/',
    'budgetbook/build/',
    'release/',
    'dist/',
    'build/',
)
SKIP_PATHS = {
    'packaging/sensitive_patterns.py',
}


def run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ['git', *args],
        cwd=REPO_ROOT,
        check=False,
        text=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git_paths(staged: bool) -> list[str]:
    args = ['diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z'] if staged else ['ls-files', '--cached', '--others', '--exclude-standard', '-z']
    result = run_git(args)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode('utf-8', errors='ignore').strip() or 'git path listing failed')
    return [path.decode('utf-8', errors='ignore') for path in result.stdout.split(b'\0') if path]


def should_scan(relative_path: str) -> bool:
    normalized = relative_path.replace('\\', '/')
    if normalized in SKIP_PATHS or normalized.startswith(SKIP_PREFIXES):
        return False
    return is_text_file(Path(normalized))


def read_file(relative_path: str, staged: bool) -> str | None:
    if staged:
        result = run_git(['show', f':{relative_path}'])
        if result.returncode != 0:
            return None
        return result.stdout.decode('utf-8', errors='ignore')
    path = REPO_ROOT / relative_path
    try:
        return path.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description='Audit tracked source files for private data and secret-looking tokens.')
    parser.add_argument('--staged', action='store_true', help='Scan staged content instead of all tracked source files')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    try:
        paths = [path for path in git_paths(args.staged) if should_scan(path)]
    except RuntimeError as exc:
        print(f'[source-audit] {exc}', file=sys.stderr)
        return 2

    patterns = load_secret_patterns(REPO_ROOT)
    failures: list[str] = []
    for relative_path in paths:
        body = read_file(relative_path, args.staged)
        if body is None:
            continue
        for pattern in patterns:
            if pattern.search(body):
                failures.append(f'forbidden source content pattern {pattern.pattern!r}: {relative_path}')

    if failures:
        print('[source-audit] blocked:', file=sys.stderr)
        for failure in failures:
            print(f'  - {failure}', file=sys.stderr)
        return 1

    if args.verbose:
        mode = 'staged' if args.staged else 'source'
        print(f'[source-audit] OK: scanned {len(paths)} {mode} text files.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
