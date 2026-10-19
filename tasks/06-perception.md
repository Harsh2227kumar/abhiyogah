# 06 — Perception: triage, PII masking, reply QA

- **Issue:** #8 (sub-issue of #1)
- **Branch:** `agent/perception`
- **Phase:** 3
- **Depends on:** 04-platform merged
- **Owns:** `src/abhiyogah/perception/`, `tests/perception/`, `data/gold/`
- **Goal:** LLM-assisted perception that produces facts with provenance and never makes a regulatory decision.

## Checklist

- [x] LLM gateway interface with adapters: a deterministic fake (default in tests), Anthropic, AWS Bedrock
      (ap-south-1) and an OpenAI-compatible endpoint (for self-hosted vLLM). Region and model come
      from config; refuse non-India regions unless explicitly allowed.
- [x] PII masking before any model call: Presidio + custom recognisers for Aadhaar, PAN, account number,
      IFSC, UPI VPA, card number, mobile. Re-identification only inside the engine.
- [x] Triage: complaint vs query (high-recall gate; every "not a complaint" goes to human review), RBI
      category, language, schema-constrained output with confidence.
- [x] Fact extraction: amount, UTR, transaction date T, channel, account type. Output becomes
      `ComplaintEvent`s with source LLM, model, prompt version and text span.
- [ ] Reply QA gate (A18): checks a draft reply for every required element; blocks sending if any are
      missing; never flags the required Ombudsman wording as a risk.
- [ ] Synthetic gold sets in `data/gold/` (English, Hindi, Hinglish), clearly synthetic; an eval script
      reporting recall per language. A TF-IDF baseline for comparison.
- [ ] Rules-only fallback when no LLM is configured: everything goes to the manual queue.
- [ ] Write `STREAM COMPLETE`.

## Requests

- `pyproject.toml` (foundation): add an optional extra, e.g. `llm = ["anthropic", "boto3", "presidio-analyzer"]`.
  Perception loads these lazily (`importlib`) and tests inject fakes, so nothing breaks without them.
- `.env.example` (foundation/platform): add `LLM_MODEL=`, `LLM_REGION=` (India region, e.g. `ap-south-1`)
  and `LLM_ALLOW_NON_INDIA_REGION=false` next to the existing `LLM_*` placeholders.
- `docs/open-questions.md` (rule pack): add the RBI complaint category list as the next Q (issue #35).
  Until answered, triage categories come from configuration and default to none.

## Log
- 2026-10-19 · item 1 done · `perception.gateway` (config, India-region check, LlmRequest/Response) + `perception.adapters` (FakeModel, Anthropic, Bedrock Converse, OpenAI-compatible; SDKs injected/lazy) · next: item 2 PII masking
- 2026-10-19 · item 2 done · `perception.pii`: Aadhaar (Verhoeff), PAN, account (keyword), IFSC, VPA, card (Luhn), mobile, email, catch-all 9+ digits; UTR/RRN kept; `PiiVault` re-identifies in-process only; optional Presidio NER hook · next: item 3 triage
- 2026-10-19 · item 3 done · `perception.triage`: schema-constrained answer (label, confidence, issue type, category, language, evidence span); gate keeps anything unsure or with a deficiency cue as a complaint; every NOT_A_COMPLAINT opens a review task; model failure → manual queue; categories configurable (#35) · next: item 4 fact extraction
- 2026-10-19 · item 4 done · `perception.extraction`: amount/UTR/T/channel/account type with spans; grounding checks (value in span, no placeholders, no future dates, enum members), conflicts dropped; one FACTS_RECORDED event per fact with LLM provenance; folds into ComplaintFacts · next: item 5 reply QA gate
