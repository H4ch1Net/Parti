.PHONY: setup dev api web test lint format build smoke screenshots brand docker

PY := backend/.venv/bin

setup:  ## Install backend and frontend dependencies
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
	cd frontend && npm install

api:  ## Run the API with reload on :8000
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

web:  ## Run the web app on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

dev:  ## Run API and web app together
	$(MAKE) -j2 api web

test:  ## Backend and frontend tests
	cd backend && .venv/bin/pytest -q
	cd frontend && npm test

lint:  ## Lint and typecheck
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	cd frontend && npm run typecheck

format:  ## Format backend code
	cd backend && .venv/bin/ruff format . && .venv/bin/ruff check --fix .

build:  ## Production build of the web app
	cd frontend && npm run build

smoke:  ## End-to-end smoke test (needs `make dev` running)
	cd frontend && npm run smoke

screenshots:  ## Refresh docs/screenshots (needs `make dev` running)
	cd frontend && npm run screenshots

brand:  ## Refresh banner, social image and touch icon (needs `make api` running)
	cd frontend && npm run brand

docker:  ## Single-image build serving API and web app on :8000
	docker build -t parti . && docker run --rm -p 8000:8000 parti
