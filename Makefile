# Warrant — build targets
#
# The reproducibility contract from 04 §7:
#
#     make setup
#     make dataset SEED=1337
#     make eval
#
# Change the seed and re-run. If the numbers move materially, the result isn't
# real and I'd want to know.

PYTHON ?= python
SEED   ?= 1337
SIZE   ?= 800

.DEFAULT_GOAL := help
.PHONY: help setup dataset catalog pairs baseline categories rules report eval test lint clean

help:
	@echo "setup     install dependencies"
	@echo "dataset   build the catalog and (later) the labelled pairs"
	@echo "baseline  run the AP2 reference baseline (kill criterion K1)"
	@echo "eval      run the evaluation and rewrite eval/REPORT.md"
	@echo "test      run the test suite"
	@echo "report    catalog mapping coverage and composition"
	@echo "clean     remove generated artefacts (never data/raw)"
	@echo ""
	@echo "vars: SEED=$(SEED) SIZE=$(SIZE)"

setup:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

# --- dataset ---------------------------------------------------------------
# Milestone 1 builds the catalog. intents, carts and violation injectors land
# in Milestone 2 and hang off this same target.

dataset: catalog pairs

catalog:
	$(PYTHON) data/generator/catalog.py --build --seed $(SEED) --size $(SIZE)

pairs:
	$(PYTHON) data/generator/make_dataset.py --build --seed $(SEED)

baseline:
	$(PYTHON) eval/run_baseline.py --seed $(SEED)

categories:
	$(PYTHON) eval/run_categories.py

rules:
	$(PYTHON) eval/run_rules.py --seed $(SEED)

report:
	$(PYTHON) data/generator/catalog.py --report --seed $(SEED)

sample:
	$(PYTHON) data/generator/catalog.py --sample 40 --seed $(SEED)

# --- evaluation ------------------------------------------------------------

eval:
	@if [ -f eval/run_eval.py ]; then \
		$(PYTHON) eval/run_eval.py --seed $(SEED); \
	else \
		echo "eval/run_eval.py not built yet — Milestone 2 onward."; \
		echo "Available now: make test, make report, make sample"; \
		exit 1; \
	fi

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check warrant data eval tests || true

clean:
	rm -rf data/catalog/*.jsonl data/gold/*.jsonl eval/REPORT.md
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
