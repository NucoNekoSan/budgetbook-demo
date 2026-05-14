# BudgetBook 運用ショートカット
# 「半年後の自分が手順を忘れていても動かせる」ためのコマンド集約。
# Windows でも make が入っていれば動く。なければ scripts/ を直接呼ぶこと。

SHELL := /bin/sh
SERVICE := budgetbook
COMPOSE := docker compose

.PHONY: help up down restart logs ps shell test check selfcheck \
        backup verify-backups restore prune-audit accounting-integrity \
        migrate makemigrations build pull collect-static refresh-ui

help:
	@echo "BudgetBook make targets:"
	@echo "  up                  - docker compose up -d"
	@echo "  down                - docker compose down"
	@echo "  restart             - restart $(SERVICE)"
	@echo "  logs                - docker compose logs -f $(SERVICE)"
	@echo "  ps                  - docker compose ps"
	@echo "  shell               - bash inside $(SERVICE) container"
	@echo "  build               - docker compose build"
	@echo "  pull                - git pull then build"
	@echo ""
	@echo "  test                - run Django tests in container"
	@echo "  check               - python manage.py check + makemigrations --check"
	@echo "  selfcheck           - python manage.py self_check --verbose"
	@echo "  accounting-integrity- check_accounting_integrity"
	@echo ""
	@echo "  migrate             - python manage.py migrate"
	@echo "  makemigrations      - python manage.py makemigrations"
	@echo "  collect-static      - python manage.py collectstatic --noinput"
	@echo "  refresh-ui          - collectstatic + nginx reload (反映されないとき)"
	@echo ""
	@echo "  backup              - run scripts/backup_budgetbook.sh"
	@echo "  verify-backups      - run scripts/verify_backups.sh"
	@echo "  restore FILE=...    - restore_budgetbook.sh from FILE"
	@echo "  prune-audit         - prune_audit_logs --dry-run --keep-days=365"

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart $(SERVICE)

logs:
	$(COMPOSE) logs -f $(SERVICE)

ps:
	$(COMPOSE) ps

shell:
	$(COMPOSE) exec $(SERVICE) bash

build:
	$(COMPOSE) build

pull:
	git pull
	$(COMPOSE) build

test:
	$(COMPOSE) exec -T $(SERVICE) python manage.py test ledger

check:
	$(COMPOSE) exec -T $(SERVICE) python manage.py check
	$(COMPOSE) exec -T $(SERVICE) python manage.py makemigrations --check

selfcheck:
	$(COMPOSE) exec -T $(SERVICE) python manage.py self_check --verbose

accounting-integrity:
	$(COMPOSE) exec -T $(SERVICE) python manage.py check_accounting_integrity

migrate:
	$(COMPOSE) exec -T $(SERVICE) python manage.py migrate

makemigrations:
	$(COMPOSE) exec -T $(SERVICE) python manage.py makemigrations

collect-static:
	$(COMPOSE) exec -T $(SERVICE) python manage.py collectstatic --noinput

# CSS / JS / template の編集を反映する 1 コマンド
# - collectstatic で staticfiles/ 更新
# - nginx に reload
refresh-ui:
	$(COMPOSE) exec -T $(SERVICE) python manage.py collectstatic --noinput
	$(COMPOSE) exec -T proxy nginx -s reload || true
	@echo "UI assets refreshed. Hard-reload your browser (Ctrl+Shift+R)."

backup:
	./scripts/backup_budgetbook.sh

verify-backups:
	./scripts/verify_backups.sh

restore:
	@if [ -z "$(FILE)" ]; then echo "usage: make restore FILE=backup/db-XXXX.sqlite3"; exit 1; fi
	./scripts/restore_budgetbook.sh "$(FILE)"

prune-audit:
	$(COMPOSE) exec -T $(SERVICE) python manage.py prune_audit_logs --dry-run --keep-days=365