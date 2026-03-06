.PHONY: up down test-core db-bootstrap mcp-server email-mcp-server

up:
	./scripts/dev-up.sh

down:
	docker compose down

test-core:
	docker build -t odoo-core-test ./apps/core-svc && docker run --rm -v $(PWD)/apps/core-svc:/app -w /app -e PYTHONPATH=/app odoo-core-test pytest -q tests

db-bootstrap:
	./scripts/db-bootstrap.sh

mcp-server:
	docker compose run --rm -i --profile mcp mcp-server

email-mcp-server:
	docker compose run --rm -i -e EMAIL_MCP_TRANSPORT=stdio sold-item-email-mcp
