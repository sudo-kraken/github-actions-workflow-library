PYTHON ?= python3
UV ?= uv
PY_YAML_VERSION ?= 6.0.2

.PHONY: check

check:
	@if $(PYTHON) -c 'import yaml' >/dev/null 2>&1; then \
		$(PYTHON) scripts/check_templates.py; \
	else \
		$(UV) run --with PyYAML==$(PY_YAML_VERSION) python scripts/check_templates.py; \
	fi
