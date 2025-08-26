# Nyelux Backend Makefile
# Production-ready commands for development, testing, and deployment

.PHONY: help install install-dev setup-db migrate test lint format clean run docker-build docker-run

# Default target
.DEFAULT_GOAL := help

# Python interpreter
PYTHON := python3.11
VENV := venv
PIP := $(VENV)/bin/pip
PYTHON_VENV := $(VENV)/bin/python

# Project variables
PROJECT_NAME := nyelux-backend
MODULE := src
TESTS := tests

# Database variables
DB_NAME := nyelux_development
DB_USER := postgres
DB_PASSWORD := password
DB_HOST := localhost
DB_PORT := 5432

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
RED := \033[0;31m
YELLOW := \033[0;33m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)Nyelux Backend Development Commands$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

install: ## Install production dependencies
	@echo "$(BLUE)Installing production dependencies...$(NC)"
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel
	$(PIP) install -r requirements.txt
	@echo "$(GREEN)✓ Dependencies installed$(NC)"

install-dev: install ## Install development dependencies
	@echo "$(BLUE)Installing development dependencies...$(NC)"
	$(PIP) install -r requirements-dev.txt 2>/dev/null || true
	pre-commit install
	@echo "$(GREEN)✓ Development dependencies installed$(NC)"

setup-db: ## Set up local PostgreSQL database
	@echo "$(BLUE)Setting up database...$(NC)"
	createdb $(DB_NAME) 2>/dev/null || echo "Database already exists"
	createdb $(DB_NAME)_test 2>/dev/null || echo "Test database already exists"
	@echo "$(GREEN)✓ Database setup complete$(NC)"

migrate: ## Run database migrations
	@echo "$(BLUE)Running database migrations...$(NC)"
	$(PYTHON_VENV) -m alembic upgrade head
	@echo "$(GREEN)✓ Migrations complete$(NC)"

migrate-create: ## Create a new migration (usage: make migrate-create name="add_user_table")
	@echo "$(BLUE)Creating new migration...$(NC)"
	$(PYTHON_VENV) -m alembic revision --autogenerate -m "$(name)"
	@echo "$(GREEN)✓ Migration created$(NC)"

seed: ## Seed database with sample data
	@echo "$(BLUE)Seeding database...$(NC)"
	$(PYTHON_VENV) scripts/seed_data.py
	@echo "$(GREEN)✓ Database seeded$(NC)"

test: ## Run all tests with coverage
	@echo "$(BLUE)Running tests...$(NC)"
	$(PYTHON_VENV) -m pytest $(TESTS) -v --cov=$(MODULE) --cov-report=term-missing --cov-report=html --cov-fail-under=80
	@echo "$(GREEN)✓ Tests complete$(NC)"

test-unit: ## Run unit tests only
	@echo "$(BLUE)Running unit tests...$(NC)"
	$(PYTHON_VENV) -m pytest $(TESTS)/unit -v --cov=$(MODULE)
	@echo "$(GREEN)✓ Unit tests complete$(NC)"

test-integration: ## Run integration tests only
	@echo "$(BLUE)Running integration tests...$(NC)"
	$(PYTHON_VENV) -m pytest $(TESTS)/integration -v
	@echo "$(GREEN)✓ Integration tests complete$(NC)"

test-watch: ## Run tests in watch mode
	@echo "$(BLUE)Running tests in watch mode...$(NC)"
	$(PYTHON_VENV) -m pytest-watch $(TESTS) -- -v

lint: ## Run all linting checks
	@echo "$(BLUE)Running linting checks...$(NC)"
	@echo "Running Black..."
	$(PYTHON_VENV) -m black --check --config pyproject.toml $(MODULE) $(TESTS)
	@echo "Running isort..."
	$(PYTHON_VENV) -m isort --check-only --settings-path pyproject.toml $(MODULE) $(TESTS)
	@echo "Running Flake8..."
	$(PYTHON_VENV) -m flake8 --config .flake8 $(MODULE) $(TESTS)
	@echo "Running MyPy..."
	$(PYTHON_VENV) -m mypy --config-file pyproject.toml $(MODULE)
	@echo "Running Bandit..."
	$(PYTHON_VENV) -m bandit -r $(MODULE) -ll
	@echo "$(GREEN)✓ All linting checks passed$(NC)"

format: ## Auto-format code with Black and isort
	@echo "$(BLUE)Formatting code...$(NC)"
	$(PYTHON_VENV) -m black --config pyproject.toml $(MODULE) $(TESTS)
	$(PYTHON_VENV) -m isort --settings-path pyproject.toml $(MODULE) $(TESTS)
	@echo "$(GREEN)✓ Code formatted$(NC)"

clean: ## Clean up generated files
	@echo "$(BLUE)Cleaning up...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/
	rm -rf dist/
	rm -rf build/
	@echo "$(GREEN)✓ Cleanup complete$(NC)"

run: ## Run the development server
	@echo "$(BLUE)Starting development server...$(NC)"
	$(PYTHON_VENV) -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

run-prod: ## Run the production server
	@echo "$(BLUE)Starting production server...$(NC)"
	$(PYTHON_VENV) -m gunicorn src.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

docker-build: ## Build Docker image
	@echo "$(BLUE)Building Docker image...$(NC)"
	docker build -t $(PROJECT_NAME):latest .
	@echo "$(GREEN)✓ Docker image built$(NC)"

docker-run: ## Run Docker container
	@echo "$(BLUE)Running Docker container...$(NC)"
	docker run -d \
		--name $(PROJECT_NAME) \
		-p 8000:8000 \
		-e DATABASE_URL=postgresql://$(DB_USER):$(DB_PASSWORD)@host.docker.internal:$(DB_PORT)/$(DB_NAME) \
		-e REDIS_URL=redis://host.docker.internal:6379/0 \
		$(PROJECT_NAME):latest
	@echo "$(GREEN)✓ Container running$(NC)"

docker-compose-up: ## Start all services with docker-compose
	@echo "$(BLUE)Starting services with docker-compose...$(NC)"
	docker-compose up -d
	@echo "$(GREEN)✓ Services started$(NC)"

docker-compose-down: ## Stop all services
	@echo "$(BLUE)Stopping services...$(NC)"
	docker-compose down
	@echo "$(GREEN)✓ Services stopped$(NC)"

docs: ## Generate API documentation
	@echo "$(BLUE)Generating documentation...$(NC)"
	$(PYTHON_VENV) -m mkdocs build
	@echo "$(GREEN)✓ Documentation generated$(NC)"

docs-serve: ## Serve documentation locally
	@echo "$(BLUE)Serving documentation...$(NC)"
	$(PYTHON_VENV) -m mkdocs serve

check-security: ## Run security checks
	@echo "$(BLUE)Running security checks...$(NC)"
	$(PYTHON_VENV) -m safety check
	$(PYTHON_VENV) -m bandit -r $(MODULE) -f json -o security-report.json
	@echo "$(GREEN)✓ Security checks complete$(NC)"

check-deps: ## Check for outdated dependencies
	@echo "$(BLUE)Checking dependencies...$(NC)"
	$(PIP) list --outdated
	@echo "$(GREEN)✓ Dependency check complete$(NC)"

setup-pre-commit: ## Set up pre-commit hooks
	@echo "$(BLUE)Setting up pre-commit hooks...$(NC)"
	pre-commit install
	pre-commit run --all-files
	@echo "$(GREEN)✓ Pre-commit hooks installed$(NC)"

backup-db: ## Backup the database
	@echo "$(BLUE)Backing up database...$(NC)"
	pg_dump -h $(DB_HOST) -U $(DB_USER) -d $(DB_NAME) > backups/$(DB_NAME)_$$(date +%Y%m%d_%H%M%S).sql
	@echo "$(GREEN)✓ Database backed up$(NC)"

restore-db: ## Restore database from backup (usage: make restore-db file=backup.sql)
	@echo "$(BLUE)Restoring database...$(NC)"
	psql -h $(DB_HOST) -U $(DB_USER) -d $(DB_NAME) < $(file)
	@echo "$(GREEN)✓ Database restored$(NC)"

logs: ## Tail application logs
	@echo "$(BLUE)Tailing logs...$(NC)"
	tail -f logs/*.log

shell: ## Open Python shell with app context
	@echo "$(BLUE)Opening Python shell...$(NC)"
	$(PYTHON_VENV) -c "import asyncio; from src.db.session import AsyncSessionLocal, engine; asyncio.run(AsyncSessionLocal().__aenter__())"

health-check: ## Check if all services are healthy
	@echo "$(BLUE)Checking service health...$(NC)"
	@$(PYTHON_VENV) scripts/health_check.py
	@echo "$(GREEN)✓ All services healthy$(NC)"

.PHONY: all
all: install setup-db migrate seed ## Complete setup for new developers
	@echo "$(GREEN)✓ Setup complete! Run 'make run' to start the server.$(NC)"
