# Gold sets (synthetic)

Every record here is **synthetic**: written for testing, not taken from any customer, complaint or
bank. There are no names, account numbers or identifiers. RBI publishes no complaint narratives
(research report, line 174), so these sets only show whether the pipeline behaves sensibly. They
are not evidence of real-world accuracy, and design-partner data must replace them before any claim
is made.

- `triage.jsonl`: one JSON object per line: `id`, `language` (`ENGLISH`, `HINDI`, `HINGLISH`),
  `label` (`COMPLAINT`, `QUERY`, `REQUEST`), `text`, `synthetic: true`. 20 per language.

Run the evaluation (recall per language for the cue rules, a TF-IDF baseline and, when an LLM is
configured, the triage pipeline):

```
uv run python -m abhiyogah.perception.eval data/gold/triage.jsonl
```
