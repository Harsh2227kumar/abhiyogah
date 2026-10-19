"""LLM gateway for triage, fact extraction, PII masking and reply QA.

Perception only perceives and drafts; it never decides breach, escalation, liability or
compensation (CLAUDE.md hard rule 4). Every model output carries provenance (model, prompt version,
span), text is PII-masked before any model call, and every "not a complaint" result opens a human
review task.

- ``gateway`` / ``adapters``: provider-neutral LLM interface, India-region check, adapters.
- ``pii``: masking and in-process re-identification.
- ``triage``: complaint vs query with a high-recall gate.
- ``extraction``: grounded facts as ``FACTS_RECORDED`` events.
- ``reply_qa``: the A18 reply gate, driven by the rule pack.
- ``service``: one entry point; rules-only (manual queue) when no model is configured.
- ``eval``: recall per language on the synthetic gold sets.
"""
