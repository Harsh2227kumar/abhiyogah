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
- [x] Reply QA gate (A18): checks a draft reply for every required element; blocks sending if any are
      missing; never flags the required Ombudsman wording as a risk.
- [x] Synthetic gold sets in `data/gold/` (English, Hindi, Hinglish), clearly synthetic; an eval script
      reporting recall per language. A TF-IDF baseline for comparison.
- [x] Rules-only fallback when no LLM is configured: everything goes to the manual queue.
- [x] Write `STREAM COMPLETE`.
- [x] (Owner request, 2026-10-20) Sarvam AI provider: `LLM_PROVIDER=SARVAM`, default endpoint,
      `api-subscription-key` + Bearer headers, `in-attested` region only once the owner confirms India-only processing.
- [x] (Owner request, 2026-10-20) `LLM_MAX_OUTPUT_TOKENS` and `LLM_REASONING_EFFORT` from `.env`; Sarvam
      sends `reasoning_effort: low` by default, since its reasoning tokens count against `max_tokens`.

## Requests

- `pyproject.toml` (foundation): add an optional extra, e.g. `llm = ["anthropic", "boto3", "presidio-analyzer"]`.
  Perception loads these lazily (`importlib`) and tests inject fakes, so nothing breaks without them.
- `.env.example` (foundation/platform): add `LLM_MODEL=`, `LLM_REGION=` (India region, e.g. `ap-south-1`)
  and `LLM_ALLOW_NON_INDIA_REGION=false` next to the existing `LLM_*` placeholders.
- `.env.example` (integrator): mention `LLM_PROVIDER=SARVAM` (endpoint optional) and that `LLM_REGION=in-attested`
  is set only after Sarvam confirms India-only processing.
- `.env.example` (integrator): add `LLM_MAX_OUTPUT_TOKENS=` (default 2048) and `LLM_REASONING_EFFORT=`
  (empty: `low` for Sarvam, nothing for other endpoints; `none` turns reasoning off).
- `docs/open-questions.md` (rule pack): add the RBI complaint category list as the next Q (issue #35).
  Until answered, triage categories come from configuration and default to none.
- `workflow/review.py` (platform): consider a `ReviewKind.MANUAL_PERCEPTION` so perception's
  `ManualTask`s (rules-only mode or model failure) can share the review queue. Until then
  `perception.service.ManualTask` is a separate queue entry.
- `worker/` (platform): call `PerceptionService.perceive` for inbound complaint text and append its
  `events`, `review_tasks` and `manual_tasks`; build it with `PerceptionService.from_config(GatewayConfig.from_env())`.

## Log
- 2026-10-19 · item 1 done · `perception.gateway` (config, India-region check, LlmRequest/Response) + `perception.adapters` (FakeModel, Anthropic, Bedrock Converse, OpenAI-compatible; SDKs injected/lazy) · next: item 2 PII masking
- 2026-10-19 · item 2 done · `perception.pii`: Aadhaar (Verhoeff), PAN, account (keyword), IFSC, VPA, card (Luhn), mobile, email, catch-all 9+ digits; UTR/RRN kept; `PiiVault` re-identifies in-process only; optional Presidio NER hook · next: item 3 triage
- 2026-10-19 · item 3 done · `perception.triage`: schema-constrained answer (label, confidence, issue type, category, language, evidence span); gate keeps anything unsure or with a deficiency cue as a complaint; every NOT_A_COMPLAINT opens a review task; model failure → manual queue; categories configurable (#35) · next: item 4 fact extraction
- 2026-10-19 · item 4 done · `perception.extraction`: amount/UTR/T/channel/account type with spans; grounding checks (value in span, no placeholders, no future dates, enum members), conflicts dropped; one FACTS_RECORDED event per fact with LLM provenance; folds into ComplaintFacts · next: item 5 reply QA gate
- 2026-10-19 · item 5 done · `perception.reply_qa`: required codes from IO-CB-2026-14-11-12 params (+ IO codes when upheld or unknown), trigger condition via evaluator (fails closed on unknown facts); model only reports grounded element spans and risks; missing element or model failure blocks; risks overlapping required spans dropped; test fixture copied from PR #16 · next: item 6 gold sets + eval
- 2026-10-19 · item 6 done · `data/gold/triage.jsonl` (20 synthetic each EN/HI/Hinglish, no identifiers) + `perception.eval`: recall/precision per language for cue rules, TF-IDF char-n-gram baseline (leave-one-out) and the LLM pipeline when configured · next: item 7 rules-only fallback
- 2026-10-19 · item 7 done · `perception.service.PerceptionService`: from_config builds the gateway; with no provider it is rules-only (no model calls, untriaged text stays a complaint, ManualTask per step); model failures fall back per step · next: item 8 STREAM COMPLETE
- 2026-10-19 · item 8 done · merged origin/main; all items checked; final PR #36 (Closes #8) · next: none
- 2026-10-20 · owner request done · Sarvam provider; OpenAI-compatible adapter retries without `response_format` on 400/422 and tolerates fenced/`<think>` answers · next: none
STREAM COMPLETE
- 2026-10-20 · owner request done · LLM_MAX_OUTPUT_TOKENS / LLM_REASONING_EFFORT read from env; Sarvam defaults to reasoning_effort low; a reply cut off at max_tokens names both settings · next: none
