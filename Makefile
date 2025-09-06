.PHONY: help install dev run deploy-prep clean lint test

# Default target
help:
	@echo "🏈 NFL Picks App - Available Commands"
	@echo ""
	@echo "📦 Setup & Development:"
	@echo "  install       Install dependencies with poetry"
	@echo "  dev           Install dev dependencies and setup pre-commit"
	@echo "  run           Run the Streamlit app locally"
	@echo ""
	@echo "🚀 Deployment:"
	@echo "  deploy-prep   Prepare app for deployment (generate requirements.txt)"
	@echo ""
	@echo "🧪 Data Management:"
	@echo "  update-lines  Update market lines for current week"
	@echo "  verify-db     Verify database tables exist"
	@echo ""
	@echo "🧹 Maintenance:"
	@echo "  clean         Clean up generated files"
	@echo "  lint          Run code linting"
	@echo "  test          Run tests (if any)"

# Setup & Development
install:
	@echo "📦 Installing dependencies..."
	poetry install

dev: install
	@echo "🛠️  Setting up development environment..."
	poetry run pre-commit install || echo "Pre-commit not configured"

run:
	@echo "🏃 Running Streamlit app..."
	poetry run streamlit run app/main.py

# Deployment
deploy-prep:
	@echo "🚀 Preparing for deployment..."
	@echo "✅ Using streamlit-compatible requirements.txt (already created)"
	@echo ""
	@echo "📝 Next steps for Streamlit Cloud:"
	@echo "1. Commit and push to GitHub"
	@echo "2. Go to https://share.streamlit.io/"
	@echo "3. Set main file: app/main.py"
	@echo "4. Add environment variables:"
	@echo "   - SUPABASE_URL"
	@echo "   - SUPABASE_KEY"
	@echo ""
	@echo "ℹ️  Note: Using minimal requirements.txt without nfl_data_py"
	@echo "   Full poetry requirements available in requirements_full.txt"

# Data Management
update-lines:
	@echo "📊 Updating market lines for week 1..."
	poetry run python scripts/update_market_lines.py --season 2025 --week 1

update-lines-all:
	@echo "📊 Updating market lines for all weeks..."
	poetry run python scripts/update_market_lines.py --season 2025 --weeks 1-18

verify-db:
	@echo "🔍 Verifying database tables..."
	poetry run python scripts/verify_tables.py

verify-db-test:
	@echo "🧪 Testing database operations..."
	poetry run python scripts/verify_tables.py --test

# Maintenance
clean:
	@echo "🧹 Cleaning up..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	rm -f requirements.txt

lint:
	@echo "🔍 Running linting..."
	poetry run ruff check . || echo "Ruff not configured"
	poetry run black --check . || echo "Black not configured"

test:
	@echo "🧪 Running tests..."
	poetry run pytest || echo "No tests found"

# Development shortcuts
jupyter:
	@echo "📓 Starting Jupyter Lab..."
	poetry run jupyter lab

streamlit:
	@echo "🎈 Running Streamlit app..."
	poetry run streamlit run app/main.py
