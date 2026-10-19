# Abhiyogah developer commands. See CLAUDE.md "Commands".
.PHONY: setup check format-check format lint typecheck imports test rules console-check openapi up

UV ?= uv
RUN := $(UV) run

setup:
	$(UV) sync
	@if [ -f console/package.json ] && command -v pnpm >/dev/null 2>&1; then cd console && pnpm install; fi

## Full gate: format check, lint, mypy strict, import contracts, tests, rule pack.
check: format-check lint typecheck imports test rules console-check

format-check:
	$(RUN) ruff format --check .

format:
	$(RUN) ruff format .

lint:
	$(RUN) ruff check .

typecheck:
	$(RUN) mypy

imports:
	$(RUN) lint-imports

test:
	$(RUN) pytest

## Lints rules/ and runs the scenario suite once the rule-pack and engine streams add them.
rules:
	@if [ -f src/abhiyogah/registry/lint.py ]; then \
		$(RUN) python -m abhiyogah.registry.lint rules; \
	else \
		echo "rules: registry linter not implemented yet"; \
	fi
	@if [ -d tests/scenarios ]; then \
		$(RUN) pytest tests/scenarios; \
	else \
		echo "rules: scenario runner not implemented yet"; \
	fi

## Console lint, typecheck and tests; skipped where pnpm is not installed.
console-check:
	@if ! command -v pnpm >/dev/null 2>&1; then \
		echo "console-check: pnpm not installed, skipping"; \
	elif [ -f console/package.json ]; then \
		cd console && pnpm install --frozen-lockfile --silent && pnpm check; \
	fi

openapi:
	@echo "openapi: not implemented yet"

up:
	docker compose up --build
