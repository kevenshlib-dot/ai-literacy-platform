.PHONY: help dev up down build test lint migrate

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
	pytest tests/ -v

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
