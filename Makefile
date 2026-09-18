.PHONY: setup run demo eval test

setup:
	python -m pip install -e .

run:
	uvicorn harbormaster.api.main:app --reload

demo:
	python scripts/run_pipeline.py --dry-run

eval:
	python eval/run_eval.py

test:
	pytest -q
