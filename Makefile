.PHONY: install install-backend install-frontend dev-backend dev-frontend dev clean venv tiles precompute docker-up docker-down \
	prefect-server prefect-deploy prefect-worker dask-scheduler dask-worker \
	pipeline-backfill pipeline-nrt pipeline-status help \
	test test-unit test-integration test-cov test-pipeline test-stac test-api test-azure \
	azurite-start azurite-stop \
	ssh-control ssh-worker logs-prefect logs-dask-scheduler logs-dask-worker logs-backfill

VENV := .venv
PYTHON := $(VENV)/bin/python3
PIP := $(VENV)/bin/pip

# Prefect/Dask settings
PREFECT_API_URL ?= http://localhost:4200/api
DASK_SCHEDULER_ADDRESS ?= tcp://localhost:8786
DASK_N_WORKERS ?= 4
DASK_MEMORY_LIMIT ?= 6GB

# Azure VM settings
CONTROL_VM_IP ?= 20.224.212.147
WORKER_VM_IP ?= 20.61.206.18
SSH_KEY := infra/keys/deploy_rsa

# Default target
.DEFAULT_GOAL := help

help:
	@echo "ARCO-3D Development & Pipeline Targets"
	@echo ""
	@echo "Development:"
	@echo "  make dev-backend      - Start FastAPI server (port 8847)"
	@echo "  make dev-frontend     - Start Vite dev server"
	@echo "  make install          - Install all dependencies"
	@echo ""
	@echo "Azure VMs:"
	@echo "  make ssh-control      - SSH to Control VM ($(CONTROL_VM_IP))"
	@echo "  make ssh-worker       - SSH to Worker VM ($(WORKER_VM_IP))"
	@echo "  make logs-prefect     - Tail Prefect server logs"
	@echo "  make logs-dask-scheduler - Tail Dask scheduler logs"
	@echo "  make logs-dask-worker - Tail Dask worker logs"
	@echo "  make logs-backfill    - Tail current backfill log"
	@echo ""
	@echo "Testing:"
	@echo "  make test             - Run all unit tests"
	@echo "  make test-pipeline    - Run pipeline/earthkit tests"
	@echo "  make test-stac        - Run STAC catalog tests"
	@echo "  make test-api         - Run API endpoint tests"
	@echo "  make test-azure       - Run Azure storage tests (requires Azurite)"
	@echo "  make test-integration - Run integration tests (requires data)"
	@echo "  make test-cov         - Run tests with coverage report"
	@echo "  make azurite-start    - Start Azurite (Azure Storage emulator)"
	@echo "  make azurite-stop     - Stop Azurite"
	@echo ""
	@echo "Prefect (orchestration):"
	@echo "  make prefect-server   - Start Prefect server (control VM)"
	@echo "  make prefect-deploy   - Serve Prefect deployments (control VM)"
	@echo "  make prefect-worker   - Start Prefect worker (worker VM)"
	@echo ""
	@echo "Dask (parallel processing):"
	@echo "  make dask-scheduler   - Start Dask scheduler (control VM)"
	@echo "  make dask-worker      - Start Dask worker (worker VM)"
	@echo "  make dask-local       - Start local Dask cluster (dev)"
	@echo ""
	@echo "Pipeline:"
	@echo "  make pipeline-backfill VAR=sst START=2022-01-01  - Backfill variable"
	@echo "  make pipeline-backfill-all START=2022-01-01     - Backfill all variables"
	@echo "  make pipeline-nrt                                - Run NRT ingestion"
	@echo "  make pipeline-ingest VAR=sst DATE=2024-01-15    - Ingest single date"
	@echo "  make pipeline-status                             - Show pipeline config"
	@echo "  make pipeline-catalog                            - Show catalog contents"
	@echo ""
	@echo "Tiles:"
	@echo "  make tiles            - Generate tiles (last 12 months)"
	@echo "  make tiles-recent     - Generate tiles (last 5 years)"
	@echo "  make precompute       - Precompute time metadata"
	@echo ""

# Create virtual environment
venv:
	python3 -m venv $(VENV)

# Install all dependencies
install: install-backend install-frontend

# Install Python dependencies (requires venv)
install-backend: venv
	$(PIP) install -r requirements.txt

# Install Node dependencies
install-frontend:
	npm install

# Load .env file for local development (exports all variables)
-include .env
export

# Run FastAPI backend in development mode
dev-backend:
	@if [ -f .env ]; then set -a && . ./.env && set +a; fi && \
	$(VENV)/bin/uvicorn server.main:app --reload --host 0.0.0.0 --port 8847

# Run Vite frontend in development mode
dev-frontend:
	npm run dev

# Run both backend and frontend (requires two terminals or use with &)
dev:
	@echo "Run 'make dev-backend' and 'make dev-frontend' in separate terminals"

# Precompute time metadata from ARCO dataset
precompute:
	$(PYTHON) -m server.precompute_metadata

# Generate SST tiles (default: last 12 months)
tiles:
	$(PYTHON) -m server.generate_tiles --months 12 --resolution 1024

# Generate all SST tiles (warning: ~1000 months, takes hours)
tiles-all:
	$(PYTHON) -m server.generate_tiles --all --resolution 1024

# Generate tiles for specific year range
tiles-recent:
	$(PYTHON) -m server.generate_tiles --months 60 --resolution 1024

# Docker commands
docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

# =============================================================================
# Azure VM Access
# =============================================================================

# SSH to Control VM (Prefect server, Dask scheduler)
ssh-control:
	ssh -i $(SSH_KEY) ubuntu@$(CONTROL_VM_IP)

# SSH to Worker VM (Dask workers)
ssh-worker:
	ssh -i $(SSH_KEY) ubuntu@$(WORKER_VM_IP)

# Tail Prefect server logs (Control VM)
logs-prefect:
	ssh -i $(SSH_KEY) ubuntu@$(CONTROL_VM_IP) 'journalctl -u prefect-server -f'

# Tail Dask scheduler logs (Control VM)
logs-dask-scheduler:
	ssh -i $(SSH_KEY) ubuntu@$(CONTROL_VM_IP) 'journalctl -u dask-scheduler -f'

# Tail Dask worker logs (Worker VM)
logs-dask-worker:
	ssh -i $(SSH_KEY) ubuntu@$(WORKER_VM_IP) 'journalctl -u dask-worker -f'

# Tail current backfill log (Control VM)
logs-backfill:
	ssh -i $(SSH_KEY) ubuntu@$(CONTROL_VM_IP) 'tail -f /tmp/backfill_*.log 2>/dev/null || echo "No backfill running"'

# Clean build artifacts
clean:
	rm -rf node_modules dist $(VENV) __pycache__ server/__pycache__

# Clean tiles
clean-tiles:
	rm -rf server/tiles/*.tif

# =============================================================================
# Test Targets
# =============================================================================

# Run all unit tests (excludes integration tests)
test:
	$(PYTHON) -m pytest tests/ -v --tb=short -m "not integration"

# Run pipeline and earthkit tests
test-pipeline:
	$(PYTHON) -m pytest tests/test_pipeline.py -v --tb=short -m "not integration"

# Run STAC catalog tests
test-stac:
	$(PYTHON) -m pytest tests/test_stac.py -v --tb=short -m "not integration"

# Run API endpoint tests
test-api:
	$(PYTHON) -m pytest tests/test_api.py -v --tb=short -m "not integration"

# Run integration tests (requires actual data in server/products/)
test-integration:
	$(PYTHON) -m pytest tests/ -v --tb=short -m "integration"

# Run tests with coverage report
test-cov:
	$(PYTHON) -m pytest tests/ -v --tb=short -m "not integration" \
		--cov=server --cov-report=term-missing --cov-report=html

# Run Azure storage tests (requires Azurite running)
test-azure:
	$(PYTHON) -m pytest tests/test_azure_storage.py -v --tb=short

# Start Azurite (Azure Storage Emulator) via npm
azurite-start:
	@mkdir -p /tmp/azurite
	@pgrep -f "azurite" > /dev/null && echo "Azurite already running" || \
		(npm run azurite &) && sleep 2 && echo "Azurite started on ports 10000-10002"

# Stop Azurite
azurite-stop:
	@pkill -f "azurite" 2>/dev/null && echo "Azurite stopped" || echo "Azurite not running"

# Run all Azure tests with Azurite (start, test, stop)
test-azure-ci:
	@$(MAKE) azurite-start
	@sleep 2
	@$(MAKE) test-azure || ($(MAKE) azurite-stop && exit 1)
	@$(MAKE) azurite-stop

# =============================================================================
# Prefect Targets
# =============================================================================

# Start Prefect server (control VM)
prefect-server:
	$(VENV)/bin/prefect server start --host 0.0.0.0 --port 4200

# Deploy Prefect flows (serve mode - blocking)
prefect-deploy:
	PREFECT_API_URL=$(PREFECT_API_URL) $(PYTHON) -m server.pipeline.deployments --serve

# Start Prefect worker (worker VM - connects to control VM)
prefect-worker:
	PREFECT_API_URL=$(PREFECT_API_URL) $(VENV)/bin/prefect worker start --pool default-agent-pool

# =============================================================================
# Dask Targets
# =============================================================================

# Start Dask scheduler (control VM)
dask-scheduler:
	$(VENV)/bin/dask scheduler --host 0.0.0.0 --port 8786 --dashboard-address :8787

# Start Dask worker (worker VM - connects to control VM scheduler)
dask-worker:
	$(VENV)/bin/dask worker $(DASK_SCHEDULER_ADDRESS) \
		--nworkers $(DASK_N_WORKERS) \
		--nthreads 2 \
		--memory-limit $(DASK_MEMORY_LIMIT)

# Start local Dask cluster (development)
dask-local:
	$(PYTHON) -c "from dask.distributed import LocalCluster, Client; \
		cluster = LocalCluster(n_workers=4, threads_per_worker=2, memory_limit='6GB'); \
		client = Client(cluster); \
		print(f'Dashboard: {client.dashboard_link}'); \
		input('Press Enter to stop...')"

# =============================================================================
# Pipeline Targets
# =============================================================================

# Run backfill for a variable (usage: make pipeline-backfill VAR=sst START=2022-01-01)
VAR ?= sst
START ?= 2022-01-01
END ?= $(shell date +%Y-%m-%d)
CONCURRENT ?= 4

pipeline-backfill:
	PREFECT_API_URL=$(PREFECT_API_URL) DASK_SCHEDULER_ADDRESS=$(DASK_SCHEDULER_ADDRESS) \
		$(PYTHON) -m server.pipeline.cli backfill \
		--variable $(VAR) --start $(START) --end $(END) --concurrent $(CONCURRENT)

# Backfill all variables
pipeline-backfill-all:
	PREFECT_API_URL=$(PREFECT_API_URL) DASK_SCHEDULER_ADDRESS=$(DASK_SCHEDULER_ADDRESS) \
		$(PYTHON) -m server.pipeline.cli backfill \
		--variable all --start $(START) --end $(END) --concurrent $(CONCURRENT)

# Run NRT ingestion (last 3 days)
pipeline-nrt:
	PREFECT_API_URL=$(PREFECT_API_URL) DASK_SCHEDULER_ADDRESS=$(DASK_SCHEDULER_ADDRESS) \
		$(PYTHON) -m server.pipeline.cli nrt --lookback 3

# Show pipeline status
pipeline-status:
	$(PYTHON) -m server.pipeline.cli status

# Show catalog contents
pipeline-catalog:
	$(PYTHON) -m server.pipeline.cli catalog

# Ingest single date (usage: make pipeline-ingest VAR=sst DATE=2024-01-15)
DATE ?= $(shell date -v-1d +%Y-%m-%d)

pipeline-ingest:
	PREFECT_API_URL=$(PREFECT_API_URL) DASK_SCHEDULER_ADDRESS=$(DASK_SCHEDULER_ADDRESS) \
		$(PYTHON) -m server.pipeline.cli ingest --variable $(VAR) --date $(DATE)
