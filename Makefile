.PHONY: help install dev run api web deploy-prep clean lint format test jupyter streamlit train

# Default target
help:
	@echo "🏈 NFL Picks App - Available Commands"
	@echo ""
	@echo "📦 Setup & Development:"
	@echo "  install       Install dependencies with uv"
	@echo "  dev           Install dev dependencies and setup pre-commit"
	@echo "  run           Run the Streamlit app locally"
	@echo "  api           Run the FastAPI backend locally"
	@echo "  web           Run the React frontend dev server"
	@echo ""
	@echo "🚀 Deployment:"
	@echo "  deploy-prep   Generate requirements.txt for Render"
	@echo ""
	@echo "🧪 Data Management:"
	@echo "  update-lines  Update market lines for current week"
	@echo "  update-results Update final game results (for standings)"
	@echo "  verify-db     Verify database tables exist"
	@echo ""
	@echo "🤖 ML:"
	@echo "  train         Train the spread model (ARGS=\"--seasons 2023 2024\")"
	@echo ""
	@echo "🧹 Maintenance:"
	@echo "  clean         Clean up generated files"
	@echo "  lint          Run ruff linting"
	@echo "  format        Run ruff formatting"
	@echo "  test          Run tests (if any)"

# Setup & Development
install:
	@echo "📦 Installing dependencies..."
	uv sync

dev: install
	@echo "🛠️  Setting up development environment..."
	uv run pre-commit install || echo "Pre-commit not configured"

run:
	@echo "🏃 Running Streamlit app..."
	uv run streamlit run app/main.py

api:
	@echo "⚡ Running FastAPI backend..."
	uv run uvicorn g_nfl.api.main:app --reload --port 8000

web:
	@echo "⚛️  Running React frontend..."
	cd web && npm run dev

# Deployment
deploy-prep:
	@echo "🚀 Generating requirements.txt for Render..."
	uv export --no-default-groups --no-hashes --no-emit-project -o requirements.txt
	@echo "✅ requirements.txt updated"

# Data Management
update-lines:
	@echo "📊 Updating market lines for week 1..."
	uv run python scripts/update_market_lines.py --season 2025 --week 1

update-lines-all:
	@echo "📊 Updating market lines for all weeks..."
	uv run python scripts/update_market_lines.py --season 2025 --weeks 1-18

update-results:
	@echo "🏁 Updating game results..."
	uv run python scripts/update_results.py $(ARGS)

verify-db:
	@echo "🔍 Verifying database tables..."
	uv run python scripts/verify_tables.py

verify-db-test:
	@echo "🧪 Testing database operations..."
	uv run python scripts/verify_tables.py --test

# ML
train:
	@echo "🏋️  Training spread model..."
	uv run python -m g_nfl.ml.train $(ARGS)

# Maintenance
clean:
	@echo "🧹 Cleaning up..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +

lint:
	@echo "🔍 Running linting..."
	uv run ruff check .

format:
	@echo "🪄 Formatting code..."
	uv run ruff format .
	uv run ruff check --fix .

test:
	@echo "🧪 Running tests..."
	uv run pytest || echo "No tests found"

# Development shortcuts
jupyter:
	@echo "📓 Starting Jupyter Lab..."
	uv run jupyter lab

streamlit:
	@echo "🎈 Running Streamlit app..."
	uv run streamlit run app/main.py
