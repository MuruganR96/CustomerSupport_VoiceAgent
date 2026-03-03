.PHONY: help build up down logs restart clean dev

# Default: show help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Docker Commands ───────────────────────────────────────────────────────────

build: ## Build all Docker images
	docker compose build

up: ## Start all services
	docker compose up -d

down: ## Stop all services
	docker compose down

logs: ## Follow logs for all services
	docker compose logs -f

restart: ## Restart all services
	docker compose down && docker compose up -d

clean: ## Remove all containers, images, and volumes
	docker compose down -v --rmi all

# ── Individual Service Commands ───────────────────────────────────────────────

logs-backend: ## Follow backend logs
	docker compose logs -f backend

logs-agent: ## Follow agent worker logs
	docker compose logs -f agent-worker

logs-livekit: ## Follow LiveKit server logs
	docker compose logs -f livekit-server

# ── Development Commands ──────────────────────────────────────────────────────

dev-backend: ## Run backend locally (outside Docker)
	cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

dev-frontend: ## Run frontend dev server locally
	cd frontend && npm install && npm run dev

dev-agent: ## Run agent worker locally
	cd agent_worker && python -m livekit.agents.cli dev --agent main

# ── Setup ─────────────────────────────────────────────────────────────────────

setup: ## Copy .env.example to .env
	cp .env.example .env
	@echo "Edit .env with your API keys before running 'make up'"

install: ## Install all dependencies locally
	cd backend && pip install -r requirements.txt
	cd agent_worker && pip install -r requirements.txt
	cd frontend && npm install
