from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from sensitive_patterns import is_text_file, load_secret_patterns, scan_text_for_patterns

REPO_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_TRACKED_NAMES = {'.env', 'db.sqlite3'}
FORBIDDEN_TRACKED_SUFFIXES = {'.p12', '.pfx', '.pem', '.key', '.sqlite3', '.db', '.bak'}
FORBIDDEN_TRACKED_PREFIXES = (
    'release/',
    'dist/',
    'build/',
    'budgetbook/dist/',
    'budgetbook/build/',
    'budgetbook/staticfiles/',
)
FORBIDDEN_TRACKED_PATHS = {'budgetbook/BudgetBook.spec'}
REQUIRED_PATHS = (
    'desktop/launcher.py',
    'packaging/audit_release.py',
    'packaging/release_manifest.py',
    'packaging/audit_source_sensitive.py',
    'packaging/sensitive_patterns.py',
    'packaging/windows/build-installer.ps1',
    'packaging/windows/BudgetBook.iss',
    'packaging/windows/sign-windows.ps1',
    'packaging/macos/build-macos.sh',
    'packaging/macos/sign-and-notarize.sh',
    'docs/DESKTOP_DISTRIBUTION.md',
    'docs/GITHUB_RELEASE_PROCESS.md',
)
PUBLISHABLE_SUFFIXES = {'.exe', '.dmg', '.msi', '.pkg', '.zip'}
SOURCE_SCAN_SKIP_PREFIXES = (
    'budgetbook/.venv/',
    'budgetbook/staticfiles/',
    'budgetbook/dist/',
    'budgetbook/build/',
    'release/',
    'dist/',
    'build/',
)
SOURCE_SCAN_SKIP_PATHS = {
    'packaging/sensitive_patterns.py',
}


def run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ['git', *args],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def tracked_files() -> list[str]:
    result = run_git(['ls-files', '-z'])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or 'git ls-files failed')
    return [path for path in result.stdout.split('\0') if path]



def source_files() -> list[str]:
    result = run_git(['ls-files', '--cached', '--others', '--exclude-standard', '-z'])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or 'git source file listing failed')
    return [path for path in result.stdout.split('\0') if path]


def check_tracked_files(files: list[str]) -> list[str]:
    failures: list[str] = []
    for tracked_path in files:
        normalized = tracked_path.replace('\\', '/')
        path = Path(normalized)
        if normalized in FORBIDDEN_TRACKED_PATHS:
            failures.append(f'generated desktop spec is tracked: {normalized}')
        if normalized.startswith(FORBIDDEN_TRACKED_PREFIXES):
            failures.append(f'generated release/build output is tracked: {normalized}')
        if path.name.lower() in FORBIDDEN_TRACKED_NAMES:
            failures.append(f'private runtime file is tracked: {normalized}')
        if path.suffix.lower() in FORBIDDEN_TRACKED_SUFFIXES:
            failures.append(f'private/binary data file is tracked: {normalized}')
    return failures


def check_required_paths() -> list[str]:
    failures: list[str] = []
    for relative_path in REQUIRED_PATHS:
        if not (REPO_ROOT / relative_path).exists():
            failures.append(f'required release file is missing: {relative_path}')
    return failures


def check_release_artifacts(release_root: Path) -> list[str]:
    failures: list[str] = []
    if not release_root.exists():
        return failures
    for artifact in release_root.rglob('*'):
        if not artifact.is_file() or artifact.suffix.lower() not in PUBLISHABLE_SUFFIXES:
            continue
        checksum = artifact.with_name(f'{artifact.name}.sha256')
        if not checksum.is_file():
            failures.append(f'missing sha256 file for artifact: {artifact.relative_to(REPO_ROOT)}')
    return failures


def check_source_sensitive_patterns(files: list[str]) -> list[str]:
    patterns = load_secret_patterns(REPO_ROOT)
    failures: list[str] = []
    for tracked_path in files:
        normalized = tracked_path.replace('\\', '/')
        if normalized in SOURCE_SCAN_SKIP_PATHS or normalized.startswith(SOURCE_SCAN_SKIP_PREFIXES):
            continue
        path = REPO_ROOT / normalized
        if not path.is_file() or not is_text_file(path):
            continue
        for pattern in scan_text_for_patterns(path, patterns):
            failures.append(f'forbidden source content pattern {pattern!r}: {normalized}')
    return failures


def check_clean_worktree() -> list[str]:
    result = run_git(['status', '--porcelain'])
    if result.returncode != 0:
        return [result.stderr.strip() or 'git status failed']
    if result.stdout.strip():
        return ['working tree is not clean; commit/review changes before creating a public GitHub release']
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description='Check BudgetBook desktop release readiness guardrails.')
    parser.add_argument('--require-clean', action='store_true', help='Fail when the Git working tree has uncommitted changes')
    parser.add_argument('--release-root', type=Path, default=REPO_ROOT / 'release', help='Release output directory to check')
    args = parser.parse_args()

    failures: list[str] = []
    try:
        files = tracked_files()
        failures.extend(check_tracked_files(files))
        failures.extend(check_source_sensitive_patterns(source_files()))
    except RuntimeError as exc:
        failures.append(str(exc))
    failures.extend(check_required_paths())
    failures.extend(check_release_artifacts(args.release_root.resolve()))
    if args.require_clean:
        failures.extend(check_clean_worktree())

    if failures:
        print('[release-ready] blocked:', file=sys.stderr)
        for failure in failures:
            print(f'  - {failure}', file=sys.stderr)
        return 1

    print('[release-ready] OK: release guardrails passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
