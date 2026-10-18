# 07 — MCP server and Regulatory Watch

- **Branch:** `agent/mcp-regwatch`
- **Phase:** 3
- **Depends on:** 04-platform merged
- **Owns:** `src/abhiyogah/mcp/`, `src/abhiyogah/regwatch/`, `tests/mcp/`, `tests/regwatch/`, `data/regwatch/`
- **Goal:** expose the engine to any agent via MCP, and watch RBI for changes that a human then turns
  into rule updates.

## Checklist

### MCP
- [ ] MCP server (official Python SDK) with tools `evaluate_complaint`, `get_deadlines`,
      `explain_decision`, `check_reply`, `list_obligations`. They call the same service layer as the
      API; there is no separate logic path. Read-only by default.
- [ ] Test that the MCP `evaluate_complaint` result equals the API result for the demo complaint.

### Regulatory Watch
- [ ] Polite fetcher for RBI notifications, Master Directions and press releases (and their RSS feeds):
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

## Log
