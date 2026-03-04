.PHONY: up down test-core db-bootstrap

up:
	./scripts/dev-up.sh

down:
	docker compose down

test-core:
	docker build -t odoo-core-test ./apps/core-svc && docker run --rm -v $(PWD)/apps/core-svc:/app -w /app -e PYTHONPATH=/app odoo-core-test pytest -q tests

db-bootstrap:
	./scripts/db-bootstrap.sh
