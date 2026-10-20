# Abhiyogah developer commands. See CLAUDE.md "Commands".
# Every target lives in scripts/dev.py, so it behaves the same on Windows (make.cmd), macOS and Linux.
TARGETS := setup check format-check format lint typecheck imports test rules console-check openapi up demo
.PHONY: $(TARGETS)

UV ?= uv

$(TARGETS):
	UV=$(UV) $(UV) run --no-project python scripts/dev.py $@
