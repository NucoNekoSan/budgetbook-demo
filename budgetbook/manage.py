#!/usr/bin/env python
import os
import sys
from pathlib import Path


def _add_local_venv_site_packages() -> None:
    """Allow manage.py to run even if IDE uses the wrong interpreter."""
    project_root = Path(__file__).resolve().parent
    if os.name == 'nt':
        site_packages = project_root / '.venv' / 'Lib' / 'site-packages'
    else:
        site_packages = project_root / '.venv' / 'lib'
        candidates = sorted(site_packages.glob('python*/site-packages'))
        site_packages = candidates[-1] if candidates else site_packages

    if site_packages.exists():
        path_value = str(site_packages)
        if path_value not in sys.path:
            sys.path.insert(0, path_value)


def main() -> None:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        _add_local_venv_site_packages()
        try:
            from django.core.management import execute_from_command_line
        except ImportError as retry_exc:
            raise ImportError(
                "Couldn't import Django. Set your interpreter to "
                f"{Path(__file__).resolve().parent / '.venv' / 'Scripts' / 'python.exe'} "
                "(Windows) or activate .venv before running manage.py."
            ) from retry_exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
