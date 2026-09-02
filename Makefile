.PHONY: case no-homers predict backtest-guardrails help install dev bootstrap push-data pull-data run api web deploy-prep clean lint format test jupyter streamlit train backtest market-ratings mlflow-ui update-context ingest-fantasy

# Default target
help:
	@echo "🏈 NFL Picks App - Available Commands"
	@echo ""
	@echo "📦 Setup & Development:"
	@echo "  install       Install dependencies with uv"
	@echo "  dev           Install dev dependencies and setup pre-commit"
	@echo "  bootstrap     Fresh clone -> working repo (warms caches, pulls data)"
	@echo "  push-data     Upload irreplaceable source documents to Supabase"
	@echo "  pull-data     Fetch them back (ARGS=--force to overwrite newer local)"
	@echo "  run           Run the fantasy draft board (Streamlit) locally"
	@echo "  api           Run the FastAPI backend locally"
	@echo "  web           Run the React frontend dev server"
	@echo ""
	@echo "🚀 Deployment:"
	@echo "  deploy-prep   Generate requirements.txt for Render"
	@echo ""
	@echo "🧪 Data Management:"
	@echo "  update-lines  Snapshot market lines (ARGS=\"--snapshot deadline\")"
	@echo "  update-results Update final game results (for standings)"
	@echo "  update-context Update game context + team EPA (for game detail)"
	@echo "  verify-db     Verify database tables exist"
	@echo "  load-pool     Load pool standings workbook (ARGS=\"<xlsx> --season 2025\")"
	@echo "  pool-report   Pool pick-trend report (ARGS=\"<xlsx> --season 2025\")"
	@echo "  ingest-fantasy Snapshot fantasy projections to Supabase (SEASON=2026)"
	@echo ""
	@echo "🤖 ML:"
	@echo "  train         Train the spread model (ARGS=\"--seasons 2023 2024\")"
	@echo "  backtest      Walk-forward backtest with betting metrics (ARGS=\"--output report.md\")"
	@echo "  predict       Model line, market line and edge for one week (ARGS=\"--week 1\")"
	@echo "  backtest-guardrails Replay the entry with the No Homers guardrails"
	@echo "  no-homers     Submit the mechanical entry (ARGS=--dry-run)"
	@echo "  case          Build the case for the room (ARGS=\"--output case.md\")"
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

bootstrap: install
	@echo "🥾 Bootstrapping a fresh clone (slow: warms ~163M of nflverse cache)..."
	uv run python scripts/bootstrap.py $(ARGS)

push-data:
	@echo "☁️  Uploading source documents to Supabase Storage..."
	uv run python scripts/sync_data.py push $(ARGS)

pull-data:
	@echo "⬇️  Fetching source documents from Supabase Storage..."
	uv run python scripts/sync_data.py pull $(ARGS)

run:
	@echo "🏈 Running the fantasy draft board..."
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
# Season defaults to the latest one with lines; snapshot says when the pull
# happened, and snapshots of the same game coexist (#58).
update-lines:
	@echo "📊 Updating market lines..."
	uv run python scripts/update_market_lines.py $(ARGS)

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

# The season being drafted for.
SEASON ?= 2026

ingest-fantasy:
	@echo "📥 Snapshotting fantasy projections to Supabase..."
	uv run python -m g_nfl.fantasy.ingest --season $(SEASON) $(ARGS)

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

case:
	@echo "📣 Building the case for the room..."
	uv run python -m g_nfl.picks.report $(ARGS)

predict:
	@echo "🔮 Predicting this week's slate..."
	uv run python -m g_nfl.ml.predict $(ARGS)

no-homers:
	@echo "🤖 Submitting the mechanical entry..."
	uv run python -m g_nfl.picks.nohomers $(ARGS)

backtest-guardrails:
	@echo "🚧 Replaying the entry with the No Homers guardrails..."
	uv run python -m g_nfl.picks.backtest $(ARGS)

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
	@echo "🎈 Alias for make run..."
	uv run streamlit run app/main.py
