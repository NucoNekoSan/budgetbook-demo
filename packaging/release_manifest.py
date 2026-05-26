from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open('rb') as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_record(path: Path, root: Path | None, platform: str | None, version: str | None, signed: bool | None) -> dict[str, Any]:
    resolved = path.resolve()
    name = str(resolved.relative_to(root)) if root else resolved.name
    stat = resolved.stat()
    record: dict[str, Any] = {
        'name': name.replace('\\', '/'),
        'filename': resolved.name,
        'size_bytes': stat.st_size,
        'sha256': file_sha256(resolved),
    }
    if platform:
        record['platform'] = platform
    if version:
        record['version'] = version
    if signed is not None:
        record['signed'] = signed
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description='Create a JSON manifest for BudgetBook release artifacts.')
    parser.add_argument('artifacts', nargs='+', type=Path, help='Release artifact files to include')
    parser.add_argument('--output', '-o', type=Path, help='Manifest output path. Defaults to stdout.')
    parser.add_argument('--platform', choices=['windows', 'macos'], help='Artifact platform metadata')
    parser.add_argument('--version', help='Release version metadata, for example 0.1.0')
    parser.add_argument('--signed', action='store_true', help='Mark artifacts as code-signed/notarized')
    parser.add_argument('--unsigned', action='store_true', help='Mark artifacts as unsigned')
    parser.add_argument('--root', type=Path, help='Root used for relative artifact names')
    args = parser.parse_args()

    if args.signed and args.unsigned:
        print('[manifest] choose either --signed or --unsigned, not both', file=sys.stderr)
        return 2

    signed = True if args.signed else False if args.unsigned else None
    root = args.root.resolve() if args.root else None
    artifacts: list[dict[str, Any]] = []
    failures: list[str] = []

    for artifact_path in args.artifacts:
        resolved = artifact_path.resolve()
        if not resolved.is_file():
            failures.append(f'artifact not found: {artifact_path}')
            continue
        if root and not resolved.is_relative_to(root):
            failures.append(f'artifact is outside root: {artifact_path}')
            continue
        artifacts.append(artifact_record(resolved, root, args.platform, args.version, signed))

    if failures:
        for failure in failures:
            print(f'[manifest] {failure}', file=sys.stderr)
        return 1

    manifest = {
        'schema': 'budgetbook.release-manifest.v1',
        'generated_at': datetime.now(UTC).isoformat(timespec='seconds'),
        'artifacts': artifacts,
    }
    body = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(body, encoding='utf-8')
        print(f'[manifest] wrote {args.output}')
    else:
        print(body, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
