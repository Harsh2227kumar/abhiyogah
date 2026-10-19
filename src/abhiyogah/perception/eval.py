"""Triage evaluation on the synthetic gold sets: complaint recall per language.

Compares up to three classifiers on ``data/gold/triage.jsonl``:

- ``cues``: the deterministic deficiency-cue rules alone (``triage.has_deficiency_cue``);
- ``tfidf``: a TF-IDF baseline (character 2-4-grams, so Devanagari and Latin both work,
  nearest-centroid by cosine), scored leave-one-out: no record is classified by a model that saw it;
- ``llm``: the full triage pipeline (masking, model, gate) when ``LLM_PROVIDER`` is configured.

Recall on complaints is the headline: a missed complaint is the failure that matters. The sets are
synthetic, so the numbers show behaviour, not real-world accuracy (``data/gold/README.md``).

    uv run python -m abhiyogah.perception.eval data/gold/triage.jsonl
"""

import math
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from abhiyogah.perception.adapters import build_gateway
from abhiyogah.perception.gateway import GatewayConfig, LlmGateway
from abhiyogah.perception.pii import PiiMasker, default_masker
from abhiyogah.perception.triage import Language, TriageLabel, has_deficiency_cue, triage

__all__ = [
    "GoldRecord",
    "LanguageScore",
    "TfidfCentroid",
    "cue_classifier",
    "evaluate",
    "llm_classifier",
    "load_gold",
    "main",
    "tfidf_leave_one_out",
]

Classifier = Callable[[Sequence["GoldRecord"]], list[bool]]
"""Predicts ``is_complaint`` for every record, in order."""


class GoldRecord(BaseModel):
    """One synthetic gold example."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    language: Language
    label: TriageLabel
    text: str
    synthetic: bool

    @property
    def is_complaint(self) -> bool:
        """Whether the gold label is a complaint."""
        return self.label is TriageLabel.COMPLAINT


class LanguageScore(BaseModel):
    """Scores for one language (or ``ALL``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    language: str
    records: int
    complaints: int
    recall: float | None
    """Complaints predicted as complaints / all complaints."""
    precision: float | None
    missed: list[str]
    """IDs of complaints predicted as not a complaint."""


def load_gold(path: Path) -> list[GoldRecord]:
    """Read a gold JSONL file; every record must be marked synthetic."""
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = GoldRecord.model_validate_json(line)
            if not record.synthetic:
                raise ValueError(f"{record.id}: gold records must be synthetic")
            records.append(record)
    return records


def _score(name: str, records: Sequence[GoldRecord], predicted: Sequence[bool]) -> LanguageScore:
    tp = sum(r.is_complaint and p for r, p in zip(records, predicted, strict=True))
    fp = sum(not r.is_complaint and p for r, p in zip(records, predicted, strict=True))
    complaints = sum(r.is_complaint for r in records)
    return LanguageScore(
        language=name,
        records=len(records),
        complaints=complaints,
        recall=tp / complaints if complaints else None,
        precision=tp / (tp + fp) if tp + fp else None,
        missed=[r.id for r, p in zip(records, predicted, strict=True) if r.is_complaint and not p],
    )


def evaluate(records: Sequence[GoldRecord], classifier: Classifier) -> list[LanguageScore]:
    """Scores per language (in ``Language`` order) and then ``ALL``."""
    predicted = classifier(records)
    scores = []
    for lang in Language:
        idx = [i for i, r in enumerate(records) if r.language is lang]
        if idx:
            scores.append(
                _score(lang.value, [records[i] for i in idx], [predicted[i] for i in idx])
            )
    scores.append(_score("ALL", records, predicted))
    return scores


def cue_classifier(records: Sequence[GoldRecord]) -> list[bool]:
    """Deficiency-cue rules alone."""
    return [has_deficiency_cue(r.text) for r in records]


def _ngrams(text: str, low: int = 2, high: int = 4) -> Counter[str]:
    t = f" {' '.join(text.lower().split())} "
    return Counter(t[i : i + n] for n in range(low, high + 1) for i in range(len(t) - n + 1))


class TfidfCentroid:
    """TF-IDF over character n-grams with a nearest-centroid classifier (cosine similarity)."""

    def __init__(self, texts: Sequence[str], labels: Sequence[bool]) -> None:
        """Fit on ``texts`` with ``labels`` (``True`` = complaint)."""
        docs = [_ngrams(t) for t in texts]
        df: Counter[str] = Counter(g for d in docs for g in d)
        n = len(docs)
        self._idf = {g: math.log((1 + n) / (1 + c)) + 1 for g, c in df.items()}
        self._centroids: dict[bool, dict[str, float]] = {}
        for label in (True, False):
            vecs = [self._vector(d) for d, lab in zip(docs, labels, strict=True) if lab is label]
            total: Counter[str] = Counter()
            for v in vecs:
                total.update(v)
            self._centroids[label] = _normalise(
                {g: w / max(len(vecs), 1) for g, w in total.items()}
            )

    def _vector(self, grams: Counter[str]) -> dict[str, float]:
        return _normalise({g: c * self._idf.get(g, 0.0) for g, c in grams.items()})

    def predict(self, text: str) -> bool:
        """Whether ``text`` is closer to the complaint centroid. Ties go to complaint."""
        v = self._vector(_ngrams(text))
        sims = {k: sum(w * c.get(g, 0.0) for g, w in v.items()) for k, c in self._centroids.items()}
        return sims[True] >= sims[False]


def _normalise(v: dict[str, float]) -> dict[str, float]:
    norm = math.sqrt(sum(w * w for w in v.values()))
    return {g: w / norm for g, w in v.items()} if norm else v


def tfidf_leave_one_out(records: Sequence[GoldRecord]) -> list[bool]:
    """Each record classified by a TF-IDF model fitted on all the others."""
    out = []
    for i, r in enumerate(records):
        rest = [x for j, x in enumerate(records) if j != i]
        model = TfidfCentroid([x.text for x in rest], [x.is_complaint for x in rest])
        out.append(model.predict(r.text))
    return out


def llm_classifier(gateway: LlmGateway, masker: PiiMasker, as_of: datetime) -> Classifier:
    """The full triage pipeline (masking, model, high-recall gate)."""

    def classify(records: Sequence[GoldRecord]) -> list[bool]:
        return [
            triage(
                r.text,
                complaint_id=r.id,
                document_ref=r.id,
                gateway=gateway,
                masker=masker,
                as_of=as_of,
            ).is_complaint
            for r in records
        ]

    return classify


def format_scores(name: str, scores: Iterable[LanguageScore]) -> str:
    """A plain-text table of one classifier's scores."""

    def pct(x: float | None) -> str:
        return "  n/a" if x is None else f"{x:5.1%}"

    lines = [
        f"{name}",
        f"  {'language':<9} {'n':>3} {'compl':>5} {'recall':>6} {'prec':>6}  missed",
    ]
    for s in scores:
        missed = ", ".join(s.missed) or "-"
        lines.append(
            f"  {s.language:<9} {s.records:>3} {s.complaints:>5} {pct(s.recall):>6} "
            f"{pct(s.precision):>6}  {missed}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Print recall per language for each available classifier."""
    args = list(sys.argv[1:] if argv is None else argv)
    path = Path(args[0] if args else "data/gold/triage.jsonl")
    records = load_gold(path)
    print(f"{len(records)} synthetic records from {path}\n")
    print(format_scores("cues (deterministic rules)", evaluate(records, cue_classifier)))
    print()
    print(format_scores("tfidf (leave-one-out)", evaluate(records, tfidf_leave_one_out)))
    print()
    gateway = build_gateway(GatewayConfig.from_env())
    if gateway is None:
        print("llm: not run (no LLM_PROVIDER configured)")
    else:
        classify = llm_classifier(gateway, default_masker(), datetime.now(UTC))
        print(format_scores(f"llm triage ({gateway.model})", evaluate(records, classify)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
