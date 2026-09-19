.PHONY: setup run demo eval test lint reset matrix ritual discipline

PYTHON ?= python
PIP ?= $(PYTHON) -m pip

setup:
	$(PIP) install -e ".[dev]"
	$(PYTHON) scripts/seed_locodes.py
	@echo "Harbormaster ready. Copy .env.example → .env and set OPENAI_API_KEY."

run:
	$(PYTHON) -m uvicorn harbormaster.api.main:app --reload --host 0.0.0.0 --port 8000

demo: reset
	$(PYTHON) scripts/run_pipeline.py --demo
	@echo "Open http://localhost:8000"

eval:
	$(PYTHON) eval/run_eval.py

full:
	$(PYTHON) scripts/run_pipeline.py --full --rules-only

submit:
	$(PYTHON) scripts/run_pipeline.py --full --submit

backup:
	$(PYTHON) scripts/backup_db.py

test:
	$(PYTHON) -m pytest -q

matrix:
	$(PYTHON) scripts/run_discipline.py

ritual:
	$(PYTHON) scripts/full_corpus_ritual.py

discipline: matrix
	$(PYTHON) -m pytest -q tests/test_format_matrix.py tests/test_official_spec.py

lint:
	ruff check src tests

reset:
	$(PYTHON) scripts/demo_reset.py
