.PHONY: help install dev run api web deploy-prep clean lint format test jupyter streamlit train backtest market-ratings mlflow-ui update-context

# Season and week default to config.py; override on the command line, e.g.
#   make update-lines WEEK=7
SEASON ?= $(shell uv run python -c "from g_nfl.utils.config import CUR_SEASON; print(CUR_SEASON)")
WEEK ?= $(shell uv run python -c "from g_nfl.utils.config import CUR_WEEK; print(CUR_WEEK)")

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
	@echo "  update-context Update game context + team EPA (for game detail)"
	@echo "  verify-db     Verify database tables exist"
	@echo "  load-pool     Load pool standings workbook (ARGS=\"<xlsx> --season 2025\")"
	@echo "  pool-report   Pool pick-trend report (ARGS=\"<xlsx> --season 2025\")"
	@echo ""
	@echo "🤖 ML:"
	@echo "  train         Train the spread model (ARGS=\"--seasons 2023 2024\")"
	@echo "  backtest      Walk-forward backtest with betting metrics (ARGS=\"--output report.md\")"
	@echo "  market-ratings Market-derived power ratings (ARGS=\"--tune\" or \"--seasons 2023 2024\")"
	@echo "  mlflow-ui     Open MLflow UI at http://localhost:5000"
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
	uv run uvicorn g_nfl.api.main:app --reload --reload-dir src --port 8000

web:
	@echo "⚛️  Running React frontend..."
	cd web && [ -d node_modules ] || npm install
	cd web && npm run dev

# Deployment
deploy-prep:
	@echo "🚀 Generating requirements.txt for Render..."
	uv export --no-default-groups --no-hashes --no-emit-project -o requirements.txt
	@echo "✅ requirements.txt updated"

# Data Management
#
# Run this LAST, just before picks are submitted. The row it writes replaces
# the week's previous one, and the whole value of the number is how late it is:
# our stored 2025 lines were pulled a median of 66 hours before kickoff, which
# is earlier than the pool line itself, and that is why the pool-vs-market edge
# is still unmeasured. See notes/pool-spread-edge.md.
update-lines:
	@echo "📊 Updating market lines for the current week..."
	uv run python scripts/update_market_lines.py --season $(SEASON) --week $(WEEK)

update-lines-all:
	@echo "📊 Updating market lines for all weeks..."
	uv run python scripts/update_market_lines.py --season $(SEASON) --weeks 1-18

update-results:
	@echo "🏁 Updating game results..."
	uv run python scripts/update_results.py $(ARGS)

update-context:
	@echo "🌦️  Updating game context and team EPA..."
	uv run python scripts/update_game_context.py $(ARGS)

verify-db:
	@echo "🔍 Verifying database tables..."
	uv run python scripts/verify_tables.py

load-pool:
	@echo "🏊 Loading pool picks workbook into Supabase..."
	uv run python scripts/load_pool_picks.py $(ARGS)

pool-report:
	@echo "📈 Pool pick-trend report..."
	uv run python -m g_nfl.pool.analysis $(ARGS)

verify-db-test:
	@echo "🧪 Testing database operations..."
	uv run python scripts/verify_tables.py --test

# ML
train:
	@echo "🏋️  Training spread model..."
	uv run python -m g_nfl.ml.train $(ARGS)

backtest:
	@echo "📈 Running walk-forward backtest..."
	uv run python -m g_nfl.ml.evaluate $(ARGS)

market-ratings:
	@echo "📊 Running market-derived power ratings..."
	uv run python -m g_nfl.ml.market_ratings $(ARGS)

mlflow-ui:
	@echo "📊 Opening MLflow UI at http://localhost:5000 ..."
	uv run mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000

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
