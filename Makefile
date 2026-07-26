.PHONY: sync test lint validate check

sync:
	python tools/sync_shared.py

test:
	pytest -q

lint:
	ruff check .

validate:
	python tools/validate_release.py

check: sync lint test validate
