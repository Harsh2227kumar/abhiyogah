# 06 — Perception: triage, PII masking, reply QA

- **Issue:** #8 (sub-issue of #1)
- **Branch:** `agent/perception`
- **Phase:** 3
- **Depends on:** 04-platform merged
- **Owns:** `src/abhiyogah/perception/`, `tests/perception/`, `data/gold/`
- **Goal:** LLM-assisted perception that produces facts with provenance and never makes a regulatory decision.

## Checklist

- [ ] LLM gateway interface with adapters: a deterministic fake (default in tests), Anthropic, AWS Bedrock
      (ap-south-1) and an OpenAI-compatible endpoint (for self-hosted vLLM). Region and model come
      from config; refuse non-India regions unless explicitly allowed.
- [ ] PII masking before any model call: Presidio + custom recognisers for Aadhaar, PAN, account number,
      IFSC, UPI VPA, card number, mobile. Re-identification only inside the engine.
- [ ] Triage: complaint vs query (high-recall gate; every "not a complaint" goes to human review), RBI
      category, language, schema-constrained output with confidence.
- [ ] Fact extraction: amount, UTR, transaction date T, channel, account type. Output becomes
      `ComplaintEvent`s with source LLM, model, prompt version and text span.
- [ ] Reply QA gate (A18): checks a draft reply for every required element; blocks sending if any are
      missing; never flags the required Ombudsman wording as a risk.
- [ ] Synthetic gold sets in `data/gold/` (English, Hindi, Hinglish), clearly synthetic; an eval script
      reporting recall per language. A TF-IDF baseline for comparison.
- [ ] Rules-only fallback when no LLM is configured: everything goes to the manual queue.
- [ ] Write `STREAM COMPLETE`.

## Requests

## Log
