from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sensitive_patterns import is_text_file, load_secret_patterns, scan_text_for_patterns

FORBIDDEN_NAMES = {'.env', 'db.sqlite3'}
FORBIDDEN_SUFFIXES = {'.p12', '.pfx', '.pem', '.key', '.sqlite3', '.db', '.bak'}


def iter_files(root: Path):
    for path in root.rglob('*'):
        if path.is_file():
            yield path


def main() -> int:
    parser = argparse.ArgumentParser(description='Audit desktop release artifacts for bundled private data.')
    parser.add_argument('target', type=Path, help='Release directory or unpacked artifact root')
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    target = args.target.resolve()
    if not target.exists():
        print(f'[audit] target not found: {target}', file=sys.stderr)
        return 2

    patterns = load_secret_patterns(repo_root)
    failures: list[str] = []
    for path in iter_files(target):
        name = path.name.lower()
        suffix = path.suffix.lower()
        relative = path.relative_to(target)
        if name in FORBIDDEN_NAMES or suffix in FORBIDDEN_SUFFIXES:
            failures.append(f'forbidden file: {relative}')
            continue
        if is_text_file(path):
            for pattern in scan_text_for_patterns(path, patterns):
                failures.append(f'forbidden content pattern {pattern!r}: {relative}')

    if failures:
        print('[audit] release artifact is not safe:', file=sys.stderr)
        for failure in failures:
            print(f'  - {failure}', file=sys.stderr)
        return 1
    print('[audit] OK: no forbidden private data detected.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
