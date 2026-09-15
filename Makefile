.PHONY: setup data warehouse analyze models readme notebooks report test lint ci all

UV ?= uv
PYTHON := .venv/bin/python
PYTHON_ENV_STAMP := .venv/.pulse-ready
TECTONIC ?= tectonic
PROFILE ?= full
export PYTHONPATH := src
export MPLCONFIGDIR ?= /tmp/pulse-matplotlib
export IPYTHONDIR ?= /tmp/pulse-ipython
export JUPYTER_CONFIG_DIR ?= /tmp/pulse-jupyter
export LOKY_MAX_CPU_COUNT ?= 8

PROJECT_SOURCES := $(shell find src sql config -type f)
REPORT_TABLES := $(wildcard artifacts/tables/*.csv)

setup: $(PYTHON_ENV_STAMP)

$(PYTHON_ENV_STAMP): pyproject.toml uv.lock
	$(UV) sync --extra dev --locked
	@touch $(PYTHON_ENV_STAMP)

data: $(PYTHON_ENV_STAMP)
	$(PYTHON) -m pulse.simulation.generator --profile $(PROFILE) --output data/generated

warehouse: data
	$(PYTHON) -m pulse.warehouse.build --profile $(PROFILE) --data-dir data/generated --output data/pulse.duckdb

artifacts/results.json: $(PYTHON_ENV_STAMP) $(PROJECT_SOURCES) pyproject.toml
	$(PYTHON) -m pulse.pipeline --profile $(PROFILE)

analyze: artifacts/results.json

# Model training and evaluation are part of the single leakage-safe pipeline.
models: artifacts/results.json

readme: artifacts/results.json scripts/update_readme.py
	$(PYTHON) scripts/update_readme.py

notebooks: artifacts/results.json scripts/build_notebooks.py
	$(PYTHON) scripts/build_notebooks.py

reports/pulse_case_study_inputs.tex: artifacts/results.json $(REPORT_TABLES) config/external_benchmarks.yml config/economics.yml scripts/build_latex_inputs.py
	$(PYTHON) scripts/build_latex_inputs.py

reports/pulse_case_study.pdf: reports/pulse_case_study.tex reports/pulse_case_study_inputs.tex
	$(TECTONIC) -X compile --keep-logs --outdir reports reports/pulse_case_study.tex

report: reports/pulse_case_study.pdf

test: $(PYTHON_ENV_STAMP)
	$(PYTHON) -m pytest -q

lint: $(PYTHON_ENV_STAMP)
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

ci: lint
	$(PYTHON) -m pulse.pipeline --profile ci
	$(PYTHON) -m pytest -q

all: analyze readme notebooks report lint test
