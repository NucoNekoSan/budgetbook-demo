from __future__ import annotations

import os
import secrets
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

APP_NAME = 'BudgetBook'
HOST = '127.0.0.1'


def configure_import_path() -> None:
    if getattr(sys, 'frozen', False):
        app_root = Path(getattr(sys, '_MEIPASS', Path(sys.executable).resolve().parent))
    else:
        app_root = Path(__file__).resolve().parent.parent / 'budgetbook'
    if app_root.exists():
        sys.path.insert(0, str(app_root))
        os.chdir(app_root)


def app_data_dir() -> Path:
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA') or str(Path.home() / 'AppData' / 'Roaming')
        return Path(base) / APP_NAME
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / APP_NAME
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / APP_NAME


def reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def harden_data_permissions(data_dir: Path) -> None:
    if os.name == 'nt':
        return
    for target, mode in (
        (data_dir, 0o700),
        (data_dir / '.env', 0o600),
        (data_dir / 'db.sqlite3', 0o600),
    ):
        if target.exists():
            try:
                os.chmod(target, mode)
            except OSError:
                pass


def ensure_env_file(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    static_root = data_dir / 'staticfiles'
    db_path = data_dir / 'db.sqlite3'
    env_path = data_dir / '.env'
    if not env_path.exists():
        env_path.write_text(
            '\n'.join([
                f'SECRET_KEY={secrets.token_urlsafe(50)}',
                'DEBUG=0',
                'ALLOWED_HOSTS=127.0.0.1,localhost',
                'ENABLE_HTTPS=0',
                'SECURE_COOKIES=0',
                'TRUST_PROXY_SSL=0',
                'DEMO_MODE=0',
                'DEMO_ALLOW_WRITES=0',
                'DEMO_AUTO_LOGIN=0',
                'FIRST_RUN_SETUP_ENABLED=1',
                f'DJANGO_DB_PATH={db_path}',
                f'DJANGO_STATIC_ROOT={static_root}',
                'DJANGO_LOG_FORMAT=plain',
                'RATE_LIMIT_ENABLED=1',
                '',
            ]),
            encoding='utf-8',
        )
    harden_data_permissions(data_dir)
    return env_path


def configure_environment() -> None:
    env_path = ensure_env_file(app_data_dir())
    os.environ['BUDGETBOOK_ENV_FILE'] = str(env_path)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


def run_bootstrap() -> None:
    import django
    from django.core.management import call_command

    django.setup()
    call_command('migrate', interactive=False, verbosity=0)
    call_command('collectstatic', interactive=False, verbosity=0, clear=False)
    harden_data_permissions(app_data_dir())


def open_when_ready(port: int) -> None:
    time.sleep(1.0)
    webbrowser.open(f'http://{HOST}:{port}/')


def main() -> None:
    configure_import_path()
    configure_environment()
    run_bootstrap()
    port = reserve_port()
    print(f'BudgetBook running at http://{HOST}:{port}/', flush=True)
    if os.environ.get('BUDGETBOOK_OPEN_BROWSER', '1') != '0':
        threading.Thread(target=open_when_ready, args=(port,), daemon=True).start()

    from django.core.management import execute_from_command_line

    execute_from_command_line([
        sys.argv[0],
        'runserver',
        f'{HOST}:{port}',
        '--noreload',
    ])


if __name__ == '__main__':
    main()