# Abhiyogah — RBI Compliance Engine: Product Plan

_Status: planning only (not started). Created 2026-10-17. Standalone product, unrelated to CustomerPulse._

## Context
The research report (`reports/RBI compliance engine gap analysis 2.md`, kept in the CustomerPulse repo as reference only) found a real market gap. RBI's complaint rules are now a set of dated, deadline-based obligations:
- 30-day bank reply under RB-IOS 2026
- automatic escalation to the Internal Ombudsman (IO) within 20 days, or by the network TAT minus 10 days
- 90-day window for the customer to file with the RBI Ombudsman
- ₹100/day compensation for late failed-transaction reversals
- 10-working-day temporary credit (shadow credit) and a 90-day liability decision for unauthorised transactions

RBI's penalties fall on exactly these clocks (SBI ₹1.73 cr, Central Bank twice, Union Bank ₹95 lakh). No commercial product or open-source repo runs these as dated rules on individual complaints, each citing its clause. Of the 59 capabilities in the report, 25 had no counterpart anywhere.

The user wants a **new, standalone product with no connection to CustomerPulse**. It is a real startup product, built solo in 1–3 months, by someone strong in Python and TypeScript, with deployment (SaaS or on-prem) still undecided. This plan answers: is it worth building, a website or agents, which language, microservices or not, how to stay current with RBI, and what to build first.

## 1. Will it be useful, impactful and beneficial?

**Yes, if positioned correctly.** It is useful as *proof that every complaint met every RBI deadline*. It is not useful as "an AI complaint chatbot", which every CRM vendor already sells.

| Parameter | Assessment |
|---|---|
| Problem severity | High. 13.34 lakh Ombudsman complaints in FY25 (+13.55%). 37.8% were non-maintainable, which banks could have prevented. Penalties of ₹20 lakh to ₹2.27 cr. Governor and Deputy Governor publicly name IO bypass and misclassification. |
| Timing | Very good. The IO Directions (Jan 2026) and RB-IOS 2026 (Jul 2026) are new. The fraud-liability regime starts 1 Jan 2027. The DPDP rules start ~May 2027. Vendors haven't packaged any of this. |
| Differentiation | Date arithmetic with provenance: which clause version applied, which calendar, when the clock started and stopped, what money is owed. Packaged as an "RBI rule pack", like Pega's US Reg E packs. |
| Buyers | Bank/NBFC Heads of Customer Service, Principal Nodal Officers, Internal Ombudsman offices, compliance heads. NBFCs, small finance banks, payments banks and co-op banks are faster to sell to than large public sector banks. |
| Risks | Long enterprise sales cycles. Banks require on-prem deployment or India data residency. Legal liability if a rule is wrong. You need a design partner early. |
| Mitigation | Ship as an engine that *complements* the bank's CRM (CRMNext, Salesforce, etc.) through an API, not as a CRM replacement. Every rule carries a verification grade, and nothing unverified can be activated. |

## 2. Website only, or agents too?

**Neither alone.** The recommended shape is a **headless engine at the core, with three surfaces on top**:

1. **Engine API (the product).** Banks send complaint events. The engine returns deadlines, breaches, compensation, required actions and a traceable decision record. It plugs into the bank's existing CRM, which is how it gets adopted.
2. **Web console (TypeScript).** Used by the Internal Ombudsman, compliance officers and auditors: deadline boards, breach forecasts, rule registry browser, decision replay, reports for the board committee and the IO.
3. **Agents layer.** Agents *perceive, gather and draft*. They **never decide** breach, escalation or compensation; the report showed LLMs alone are unreliable at this (F1 0.31 vs 1.00 for the hybrid approach).
   - **Triage agent:** decides complaint vs query (with high recall, and every "not a complaint" decision audited), assigns the RBI category, handles Hinglish/regional languages, and extracts facts (₹ amount, UTR, transaction date T, channel).
   - **Regulatory Watch agent:** watches RBI notifications, drafts proposed rule changes for human legal sign-off.
   - **Reply QA agent:** checks the final reply contains the content the IO Directions require, and blocks sending if it doesn't.
   - **Investigator agent (later):** uses tools to pull transaction and reversal data from bank systems as evidence.
   - **Reporting agent (later):** drafts the board committee/IO quarterly reports from stored decision records.
4. **MCP server.** Exposes the engine as tools (`evaluate_complaint`, `get_deadlines`, `explain_decision`, `check_reply`). Any bank-built agent (Copilot, Claude, in-house) can then call RBI-correct logic. This is a cheap, distinctive feature.

Build order: engine → console → agents/MCP. The engine is what's valuable; agents make it easy to use.

## 3. Language choice

**Python for the engine and agents, TypeScript for the console.** No Rust, Go or Java for now.

| Option | Verdict | Why |
|---|---|---|
| **Python** (core) | ✅ Primary | Your strength; fastest for solo work. Best ecosystem for this domain: `holidays` (India state calendars, MIT), Presidio (Aadhaar/PAN masking, MIT), PDF parsing of RBI circulars, Pydantic for typed rule schemas, LLM/agent SDKs, MCP Python SDK. Correctness comes from typed models, `mypy --strict` and scenario tests, not from the language. |
| **TypeScript** (console) | ✅ Secondary | Next.js + React for the console; a typed client generated from the OpenAPI spec keeps frontend and backend in sync. |
| Rust | ❌ Not now | Speed is irrelevant: complaint volumes are a few million a year, and the work is date arithmetic. Rust would slow a solo builder 2–3×. You can still get Rust performance by using **GoRules Zen** (Rust core, Python bindings, MIT) for decision tables if needed. |
| JavaScript (untyped) | ❌ | Use TypeScript instead. |
| Java/Go | ❌ for now | Java is what banks run internally, but an API plus a container image is enough for integration. Revisit only if a bank demands a Java SDK. |

## 4. Microservices or not?

**A modular monolith**: one deployable Python service with strict internal module boundaries, plus two separate worker processes. Microservices would add ops cost a solo founder can't carry, and banks deploying on-prem prefer few containers.

```
apps/
  engine-api/        FastAPI: REST + webhook intake + MCP server
  worker/            scheduler ticks (deadline re-evaluation), LLM perception jobs
  regwatch/          RBI crawler + change-detection pipeline
  console/           Next.js (TypeScript)
packages/ (Python modules inside one repo)
  registry/          obligation YAML loader, dated parameter resolver, linter
  calendar/          Indian bank working-day calendar (holidays + bank overlay)
  clocks/            start/pause/stop clock engine, day basis, IST, rounding
  evaluator/         runs obligations on events -> decision records
  calculators/       ₹100/day failed-txn, limited liability, service-event compensation
  workflow/          three-state outcome gate, IO auto-escalation, senior review
  perception/        LLM gateway, triage/extraction, PII masking
  ledger/            append-only, hash-chained decision records
  reporting/         board committee / IO / disclosure reports, decision replay
rules/               the RBI rule pack: obligation YAML files + scenario tests (versioned in Git)
```

- **Storage:** a single PostgreSQL:
  - append-only `events` table (records both when something happened and when it was recorded)
  - `decision_records` table, hash-chained
  - pgvector for the regulatory text corpus

  No Kafka or Redis at first.
- **Job queue:** `procrastinate`, which runs on Postgres and supports periodic tasks, for scheduler ticks and LLM jobs. Temporal stays a later option if clocks multiply.
- **LLM gateway:** a thin adapter for Bedrock (Mumbai region) / Azure OpenAI (India regions) / a self-hosted model via vLLM, so it also works on-prem. Text is masked before any model sees it.
- **Deployment:** Docker Compose for the demo and SaaS, a Helm chart later for a bank's own servers. The same images serve both, which keeps the "not sure yet" deployment choice open.

## 5. Keeping current with RBI guidelines

A **regulatory change pipeline** where humans approve every rule change:

1. **Watch:** daily crawl of the RBI Notifications, Master Directions and Press Releases pages and RSS feeds, plus NPCI circulars and CERT-In. RBI's site has bot checks (the research hit one), so crawl politely and record the source URL and checksum.
2. **Store raw text immutably:** PDF + SHA-256 + circular number (regex `RBI/\d{4}-\d{2,4}/\d+`) + date, with text extracted keeping paragraph anchors, including clean Devanagari.
3. **Classify relevance:** is it about complaints, customer service, fraud, KYC, payments TAT or IO? A cheap model plus keyword rules.
4. **Detect what it changes:** link it to existing obligations through amends/supersedes links ("which of our rules does this change?").
5. **LLM drafts a proposed change** to the obligation YAML, with clause citations, and opens a pull request.
6. **Human legal sign-off.** CI runs the scenario tests and the linter, which blocks unverified or overlapping rules. Merge publishes a new rule-pack version with its effective date.
7. **Re-evaluation:** complaints in flight are re-checked under the correct version, based on bank-receipt or RBI-receipt dates.

This is also a sellable "RBI rule pack subscription", which is the recurring revenue.

## 6. Rule representation (core design)
- One YAML file per obligation, with: deontic type (must / must not / may), clause, URL, verification grade, applicability (entity type), trigger, clock (start/stop/day basis), dated parameter history, `overridden_by`, status lifecycle (draft / future-dated / in force / superseded / repealed-but-saved), and linked scenario tests. Example shape is in report §"A deterministic core".
- A small set of Python **clock and condition building blocks** that obligations reference. No custom DSL in v1.
- **Scenario-first:** write every timeline from catalogue tables A–C as a scenario file (event sequence → expected deadlines, breaches and ₹ amounts) *before* writing the evaluator.
- Every evaluation writes a **decision record**: obligation version, anchor date, input facts with where each came from (human, system, or LLM with model and prompt version), comparison, computed deadline, calendar version, result. Explanations are rendered from these records, never regenerated.

## 7. Solo MVP roadmap (12 weeks; aim for a pilot before 1 Jan 2027)

| Weeks | Deliverable |
|---|---|
| 1–2 | New repo; RBI-native complaint data dictionary; event store; obligation YAML schema, loader and linter; bank calendar (`holidays` + 2nd/4th Saturday + state holiday overlay) |
| 3–5 | Clock engine and evaluator. Rule pack v0.1: RB-IOS 2026 / IO Directions 2026 (30-day reply, 20-day / TAT−10 IO escalation, 90-day filing, scheme router 2021 vs 2026), failed-transaction TAT + ₹100/day, limited liability (3/4–7 working days, 10-working-day shadow credit, 90 days). All scenario tests pass. |
| 6–8 | Workflow gates (three-state outcome, IO auto-escalation, no closing a complaint without senior review); hash-chained ledger; REST + webhook intake; Next.js console (deadline board, decision replay, rule browser) |
| 9–10 | Triage agent (complaint vs query, category, Hinglish, fact extraction) with PII masking; Reply QA gate; MCP server |
| 11–12 | Regulatory Watch pipeline end-to-end on one real circular; auth/RBAC; Docker Compose packaging; gold evaluation sets; design-partner demo |

**Deferred:** CMS reconciliation, fraud-reporting deadline bridge, KYC/recovery-agent guardrails, Helm/on-prem packaging, board-committee report generator, the 2027 fraud regime (encode as future-dated, parameters marked unverified).

## 8. Key risks
- **Rule accuracy and liability:** verification grades are mandatory, rules only activate after sign-off, and contracts position the product as decision support with a bank-owned final decision.
- **Open regulatory questions:** clock pause rules, the RB-IOS 2026 circular number, the NBFC/CIC variants of the IO Directions, and the 2027 parameters stay configurable and flagged, never assumed.
- **No Indian complaint dataset:** start with synthetic data and design-partner data; measure triage recall separately per language.

## Verification
- **Scenario test suite:** one or more timeline files per obligation; CI fails on any deadline or ₹ mismatch.
- **Property tests** (`hypothesis`) for the calendar and clocks: working-day counts, receipt day excluded, IST boundaries, leap years.
- **Ledger integrity check:** a hash-chain verifier job; replaying a past decision must reproduce the same result at the same rule version.
- **End-to-end demo script:** post a UPI fraud complaint event → engine returns IO deadline, shadow-credit deadline and liability tier → time-travel the clock past day 20 → auto-escalation fires → console shows the clause-cited decision trace → MCP tool returns the same result to an agent.

## Project facts
- **Name:** Abhiyogah
- **Location:** `F:\Projects\abhiyogah`
- **Status:** plan only; no code yet. Next step when starting: the Weeks 1–2 foundation (section 7).
- **Research basis:** `reports/RBI compliance engine gap analysis 2.md` and `research_notes/RBI compliance engine gap analysis/` in the CustomerPulse repo, branch `research/rbi-compliance-engine`. These are reference material only; there is no code dependency.
