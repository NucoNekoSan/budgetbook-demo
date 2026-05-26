from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable, Pattern

DEFAULT_SECRET_PATTERNS = (
    r'(?m)^SECRET_KEY=(?!(?:change-me|ci-secret-key-not-for-production|ランダム|（ランダム)).{32,}$',
    r'(?m)^BUDGETBOOK_ENV_FILE=.+',
    r'-----BEGIN (?:RSA |EC |OPENSSH |DSA |)?PRIVATE KEY-----',
    r'\bAKIA[0-9A-Z]{16}\b',
    r'\bghp_[A-Za-z0-9_]{30,}\b',
    r'\bgithub_pat_[A-Za-z0-9_]{20,}\b',
    r'\bsk-[A-Za-z0-9_-]{20,}\b',
    r'\b(?:xoxb|xoxp|xoxa)-[A-Za-z0-9-]{20,}\b',
)
TEXT_SUFFIXES = {
    '.txt', '.md', '.py', '.html', '.css', '.js', '.json', '.yml', '.yaml', '.toml', '.cfg', '.ini', '.ps1', '.sh', '.env', '.example'
}
LOCAL_PATTERN_FILES = ('.sensitive-patterns.local', 'sensitive-patterns.local')


def pattern_file(repo_root: Path) -> Path | None:
    configured = os.environ.get('BUDGETBOOK_SENSITIVE_PATTERNS')
    if configured:
        return Path(configured).expanduser().resolve()
    for name in LOCAL_PATTERN_FILES:
        candidate = repo_root / name
        if candidate.exists():
            return candidate.resolve()
    return None


def load_secret_patterns(repo_root: Path) -> list[Pattern[str]]:
    pattern_strings = list(DEFAULT_SECRET_PATTERNS)
    local_file = pattern_file(repo_root)
    if local_file and local_file.exists():
        for raw_line in local_file.read_text(encoding='utf-8', errors='ignore').splitlines():
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue
            pattern_strings.append(line)
    return [re.compile(pattern) for pattern in pattern_strings]


def is_text_file(path: Path) -> bool:
    if path.name in {'.env', '.env.example'}:
        return True
    return path.suffix.lower() in TEXT_SUFFIXES


def scan_text_for_patterns(path: Path, patterns: Iterable[Pattern[str]]) -> list[str]:
    try:
        body = path.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return []
    failures: list[str] = []
    for pattern in patterns:
        if pattern.search(body):
            failures.append(pattern.pattern)
    return failures
