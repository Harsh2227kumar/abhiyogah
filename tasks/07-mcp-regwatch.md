# 07 — MCP server and Regulatory Watch

- **Issue:** #9 (sub-issue of #1)
- **Branch:** `agent/mcp-regwatch`
- **Phase:** 3
- **Depends on:** 04-platform merged
- **Owns:** `src/abhiyogah/mcp/`, `src/abhiyogah/regwatch/`, `tests/mcp/`, `tests/regwatch/`, `data/regwatch/`
- **Goal:** expose the engine to any agent via MCP, and watch RBI for changes that a human then turns
  into rule updates.

## Checklist

### MCP
- [x] MCP server (official Python SDK) with tools `evaluate_complaint`, `get_deadlines`,
      `explain_decision`, `check_reply`, `list_obligations`. They call the same service layer as the
      API; there is no separate logic path. Read-only by default.
- [x] Test that the MCP `evaluate_complaint` result equals the API result for the demo complaint.

### Regulatory Watch
- [x] Polite fetcher for RBI notifications, Master Directions and press releases (and their RSS feeds):
      rate limit, user agent, retries, and handling of bot checks without circumventing them.
- [ ] Immutable raw store: PDF/HTML + SHA-256 + circular number (regex `RBI/\d{4}-\d{2,4}/\d+`) + date + URL.
- [ ] Text extraction that keeps paragraph anchors.
- [ ] Relevance classifier (keywords first, LLM optional) for complaints, customer service, fraud, KYC,
      payment TATs and IO.
- [ ] Change-impact linking: which obligation IDs a new circular amends or supersedes.
- [ ] Draft generator: proposes a changed obligation YAML (status DRAFT) plus a summary for human legal
      review. It never edits `rules/` on `main` directly.
- [ ] Offline tests using saved fixture files; no live network calls in CI.
- [ ] Write `STREAM COMPLETE`.

## Requests

- **foundation / integrator (`pyproject.toml`, `uv.lock`):** add the MCP Python SDK as a runtime
  dependency, `mcp>=2.2,<3`. Until then `abhiyogah.mcp.server` imports it at build time and raises
  `McpUnavailableError`; `tests/mcp/test_server.py` skips without it. The tools themselves
  (`abhiyogah.mcp.tools`) need only `httpx` and run in CI.
- **platform (`src/abhiyogah/api/`):** the route bodies in `api/app.py` (`detail`, `list_complaints`,
  `explain_decision`, ...) are closures inside `_routes`, so there is no service layer another
  front end can call. Please extract them into a service module (e.g. `api/service.py`: plain
  functions over `Store` + `EngineContext` + principal + `as_of`, raising typed errors that the
  routes map to HTTP). Until then the MCP tools call the API routes in-process over ASGI (or over
  HTTP), which keeps one logic path; once the service exists they can call it directly.

## Log

- 2026-10-19 · item 1 done · mcp/tools.py (EngineTools: five read-only tools over the API routes via in-process ASGI or HTTP; non-GET refused client-side; API errors as ToolCallError), mcp/server.py (MCPServer registration, read-only annotations, stdio main, SDK loaded lazily), tests/mcp; Requests for the mcp dependency and an API service layer · next: item 2 MCP == API equality test
- 2026-10-19 · item 2 done · tests/mcp/test_api_parity.py: tool result and MCP protocol (SDK in-process Client) structured content both equal GET /complaints/{id} for the UPI demo complaint, now and time-travelled past both breaches; API refusals reach the agent as tool errors (server maps them to the SDK's ToolError) · next: item 3 polite RBI fetcher
- 2026-10-19 · item 3 done · regwatch/fetcher.py: honest UA with contact, robots.txt obeyed (incl. Crawl-delay; unreadable robots stops), per-host rate limit, bounded retries with backoff + Retry-After, bot checks raise BotCheckError with no retry/bypass, 50 MB cap, RSS parsing refusing DOCTYPE/entities; SOURCES flagged unverified (sandbox proxy blocks rbi.org.in); synthetic fixtures in data/regwatch/fixtures · next: item 4 immutable raw store
