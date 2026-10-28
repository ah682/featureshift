PYTHON := .venv/bin/python
UV_CACHE := .featureshift/uv-cache

.PHONY: setup demo seed serve test test-fast check evaluate reset

setup:
	uv venv --python python3.12 --allow-existing --no-project --cache-dir $(UV_CACHE) .venv
	uv pip sync --offline --python $(PYTHON) --cache-dir $(UV_CACHE) --require-hashes requirements/app.txt || uv pip sync --python $(PYTHON) --cache-dir $(UV_CACHE) --require-hashes requirements/app.txt
	$(PYTHON) scripts/setup_environments.py

demo: setup
	$(PYTHON) -m featureshift demo

seed:
	$(PYTHON) -m featureshift demo --seed-only

serve:
	$(PYTHON) -m featureshift serve

test:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest -q

test-fast:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON) -m pytest -q -m 'not integration'

check:
	.venv/bin/ruff check featureshift tests scripts examples benchmarks
	.venv/bin/mypy featureshift
	$(PYTHON) -m compileall -q featureshift examples benchmarks

evaluate:
	$(PYTHON) -m featureshift evaluate

reset:
	$(PYTHON) -m featureshift reset

