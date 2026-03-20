.PHONY: help dev up down build test lint migrate webui-up webui-down webui-logs

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

dev: ## Start development server locally
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

up: ## Start all services with Docker Compose
	docker-compose up -d

down: ## Stop all Docker Compose services
	docker-compose down

build: ## Build Docker image
	docker-compose build

test: ## Run tests
	TESTING=true pytest tests/ -v

lint: ## Run linter
	ruff check app/ --select E,F,W --ignore E501

migrate: ## Run database migrations
	alembic upgrade head

migrate-create: ## Create a new migration (usage: make migrate-create msg="description")
	alembic revision --autogenerate -m "$(msg)"

logs: ## View application logs
	docker-compose logs -f app

ps: ## Show running containers
	docker-compose ps

webui-up: ## Start Open WebUI (LLM Chat interface on port 3100)
	docker compose -f docker-compose.webui.yml up -d

webui-down: ## Stop Open WebUI
	docker compose -f docker-compose.webui.yml down

webui-logs: ## View Open WebUI logs
	docker compose -f docker-compose.webui.yml logs -f
