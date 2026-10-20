"""Developer commands, the same on Windows, macOS and Linux. Stdlib only.

``make <target>`` (Makefile, POSIX) and ``make.cmd <target>`` (Windows, no GNU make needed) both
call this file, so there is one implementation of every target. Run it directly with
``uv run --no-project python scripts/dev.py <target>``. See CLAUDE.md "Commands".

Set ``UV`` to use a different uv binary.
"""

import os
import secrets
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSOLE = ROOT / "console"
DEMO_COMPOSE = ["-f", "docker-compose.yml", "-f", "scripts/demo.compose.yml"]


class TaskError(Exception):
    """A step failed; carries the exit code to return."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def which(name: str) -> str | None:
    """Full path of ``name`` on PATH (resolves ``.exe``/``.cmd`` shims on Windows), or None."""
    return shutil.which(name)


def need(name: str) -> str:
    """Full path of a required tool, or a clear error."""
    path = which(name)
    if path is None:
        raise TaskError(f"{name} is required but was not found on PATH")
    return path


def run(args: Sequence[str], *, cwd: Path = ROOT, env: Mapping[str, str] | None = None) -> None:
    """Run one command, echoing it; raise TaskError if it fails."""
    print("$ " + subprocess.list2cmdline(args), flush=True)
    code = subprocess.call(list(args), cwd=cwd, env=None if env is None else dict(env))  # noqa: S603
    if code != 0:
        raise TaskError(f"command failed with exit code {code}", code)


def uv(*args: str) -> None:
    """Run ``uv <args>`` from the repository root."""
    run([need(os.environ.get("UV", "uv")), *args])


def uv_run(*args: str) -> None:
    """Run a tool inside the project environment."""
    uv("run", *args)


def setup() -> None:
    """Install the Python environment, and the console's packages where pnpm exists."""
    uv("sync")
    pnpm = which("pnpm")
    if pnpm and (CONSOLE / "package.json").is_file():
        run([pnpm, "install"], cwd=CONSOLE)


def format_check() -> None:
    """ruff format --check."""
    uv_run("ruff", "format", "--check", ".")


def format_() -> None:
    """ruff format (rewrites files)."""
    uv_run("ruff", "format", ".")


def lint() -> None:
    """ruff check."""
    uv_run("ruff", "check", ".")


def typecheck() -> None:
    """mypy --strict (configured in pyproject.toml)."""
    uv_run("mypy")


def imports() -> None:
    """import-linter contracts (the pure core imports no I/O)."""
    uv_run("lint-imports")


def test() -> None:
    """pytest."""
    uv_run("pytest")


def rules() -> None:
    """Lint rules/ and run the scenario suite."""
    if (ROOT / "src" / "abhiyogah" / "registry" / "lint.py").is_file():
        uv_run("python", "-m", "abhiyogah.registry.lint", "rules")
    else:
        print("rules: registry linter not implemented yet")
    if (ROOT / "tests" / "scenarios").is_dir():
        uv_run("pytest", "tests/scenarios")
    else:
        print("rules: scenario runner not implemented yet")


def console_check() -> None:
    """Console lint, typecheck and tests; skipped where pnpm is not installed."""
    pnpm = which("pnpm")
    if pnpm is None:
        print("console-check: pnpm not installed, skipping")
    elif (CONSOLE / "package.json").is_file():
        run([pnpm, "install", "--frozen-lockfile", "--silent"], cwd=CONSOLE)
        run([pnpm, "check"], cwd=CONSOLE)


def check() -> None:
    """The full gate: format, lint, mypy strict, import contracts, tests, rule pack, console."""
    for step in (format_check, lint, typecheck, imports, test, rules, console_check):
        step()


def openapi() -> None:
    """Export openapi.json; regenerate the console client where pnpm is installed."""
    uv_run("python", "-m", "abhiyogah.api.openapi", "openapi.json")
    pnpm = which("pnpm")
    if pnpm and (CONSOLE / "package.json").is_file():
        run([pnpm, "openapi"], cwd=CONSOLE)
    else:
        print("openapi: pnpm not installed, console client not regenerated")


def up() -> None:
    """docker compose up (Postgres, migrations, API, worker)."""
    run([need("docker"), "compose", "up", "--build"])


def demo() -> None:
    """The plan's end-to-end demo against docker compose (docs/plan.md, "End-to-end demo script").

    Starts Postgres, the migrations, the API and the worker with the demo overrides
    (scripts/demo.compose.yml) and fresh per-run API keys, then runs scripts/demo.py. Synthetic data
    only. Stop the stack with: docker compose -f docker-compose.yml -f scripts/demo.compose.yml down
    """
    if not (ROOT / ".env").is_file():
        raise TaskError("No .env found. Copy .env.example to .env first (and set a password).")
    docker = need("docker")
    # Fresh keys for this run only; the API reads them from the environment, nothing is on disk.
    writer_key = f"demo-writer-{secrets.token_hex(16)}"
    admin_key = f"demo-admin-{secrets.token_hex(16)}"
    env = {
        **os.environ,
        "ABHIYOGAH_DEMO_API_KEYS": (
            f"officer-demo:writer:{writer_key};admin-demo:admin:{admin_key}"
        ),
    }
    print(
        "==> Starting Postgres, migrations, API and worker (recreated to pick up this run's keys)"
    )
    run(
        [docker, "compose", *DEMO_COMPOSE, "up", "-d", "--force-recreate", "api", "worker"], env=env
    )
    run(
        [sys.executable, str(ROOT / "scripts" / "demo.py")],
        env={
            **env,
            "ABHIYOGAH_DEMO_API_URL": os.environ.get(
                "ABHIYOGAH_DEMO_API_URL", "http://localhost:8000"
            ),
            "ABHIYOGAH_DEMO_WRITER_KEY": writer_key,
            "ABHIYOGAH_DEMO_ADMIN_KEY": admin_key,
        },
    )


TASKS: dict[str, Callable[[], None]] = {
    "setup": setup,
    "check": check,
    "format-check": format_check,
    "format": format_,
    "lint": lint,
    "typecheck": typecheck,
    "imports": imports,
    "test": test,
    "rules": rules,
    "console-check": console_check,
    "openapi": openapi,
    "up": up,
    "demo": demo,
}


def main(argv: Sequence[str]) -> int:
    """Run each named task in order; print usage when none or an unknown one is given."""
    unknown = [name for name in argv if name not in TASKS]
    if not argv or unknown:
        if unknown:
            print(f"unknown target(s): {', '.join(unknown)}", file=sys.stderr)
        width = max(map(len, TASKS))
        print("usage: dev.py <target> [<target> ...]\n", file=sys.stderr)
        for name, fn in TASKS.items():
            summary = (fn.__doc__ or "").strip().splitlines()[0]
            print(f"  {name:<{width}}  {summary}", file=sys.stderr)
        return 2
    try:
        for name in argv:
            TASKS[name]()
    except TaskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
