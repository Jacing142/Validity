.PHONY: dev dev-backend dev-frontend docker docker-down test-mcp clean

dev:
	@echo "Run 'make dev-backend' and 'make dev-frontend' in separate terminals"

dev-backend:
	uvicorn backend.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

docker:
	docker compose up --build

docker-down:
	docker compose down

test-mcp:
	python scripts/test_mcp.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
