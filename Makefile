.PHONY: install install-web install-api install-worker install-packages \
       lint lint-web lint-py test test-web test-py \
       dev-web dev-api dev-worker dev-redis \
       docker-web docker-backend docker-backend-down clean

# ===== INSTALL =====
install: install-web install-api install-worker

install-web:
	cd apps/web && npm install

install-api:
	cd services/api && pip install -e ".[dev]"

install-worker:
	cd workers/ocr && pip install -e ".[dev]"

install-packages:
	cd packages/ocr_core && pip install -e .
	cd packages/contracts && pip install -e .

# ===== LINT =====
lint: lint-web lint-py

lint-web:
	cd apps/web && npx tsc --noEmit && npx eslint src/

lint-py:
	ruff check services/ workers/ packages/
	ruff format --check services/ workers/ packages/
	mypy services/api/app/ workers/ocr/app/

# ===== TEST =====
test: test-web test-py

test-web:
	cd apps/web && npx vitest run

test-py:
	pytest services/api/tests/ workers/ocr/tests/ packages/ocr_core/tests/ packages/contracts/tests/ -v

# ===== DEV SERVERS =====
dev-web:
	cd apps/web && npx vite --host 0.0.0.0

dev-api:
	cd services/api && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

dev-worker:
	cd workers/ocr && celery -A app.celery_app worker --loglevel=info --concurrency=$${CELERY_CONCURRENCY:-2}

dev-redis:
	docker run --rm -p 6379:6379 redis:alpine

# ===== DOCKER =====
docker-web:
	cd infra/web && docker compose up --build

docker-backend:
	cd infra/backend && docker compose up --build

docker-backend-down:
	cd infra/backend && docker compose down

# ===== CLEAN =====
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name dist -exec rm -rf {} + 2>/dev/null || true
