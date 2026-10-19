"""Gold-set evaluation: the gold file is valid and synthetic, scores are per language."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import JsonValue

from abhiyogah.perception.adapters import FakeModel
from abhiyogah.perception.eval import (
    GoldRecord,
    TfidfCentroid,
    cue_classifier,
    evaluate,
    llm_classifier,
    load_gold,
    main,
    tfidf_leave_one_out,
)
from abhiyogah.perception.gateway import LlmRequest
from abhiyogah.perception.pii import PiiMasker, verhoeff_valid
from abhiyogah.perception.triage import Language, TriageLabel

GOLD = Path("data/gold/triage.jsonl")


def test_gold_set_is_synthetic_balanced_and_unique() -> None:
    records = load_gold(GOLD)
    assert len({r.id for r in records}) == len(records)
    for lang in Language:
        if lang is Language.OTHER:
            continue
        subset = [r for r in records if r.language is lang]
        assert len(subset) >= 20
        assert any(r.is_complaint for r in subset)
        assert any(not r.is_complaint for r in subset)


def test_gold_set_holds_no_identifiers() -> None:
    masker = PiiMasker()
    for record in load_gold(GOLD):
        assert masker.mask(record.text).entities == (), record.id
        assert not any(
            len(w) == 12 and w.isdigit() and verhoeff_valid(w) for w in record.text.split()
        )


def test_non_synthetic_record_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "gold.jsonl"
    path.write_text(
        '{"id": "X", "language": "ENGLISH", "label": "QUERY", "text": "t", "synthetic": false}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="synthetic"):
        load_gold(path)


def _rec(rid: str, lang: Language, label: TriageLabel, text: str) -> GoldRecord:
    return GoldRecord(id=rid, language=lang, label=label, text=text, synthetic=True)


def test_scores_are_per_language_then_all() -> None:
    records = [
        _rec("E1", Language.ENGLISH, TriageLabel.COMPLAINT, "a"),
        _rec("E2", Language.ENGLISH, TriageLabel.COMPLAINT, "b"),
        _rec("E3", Language.ENGLISH, TriageLabel.QUERY, "c"),
        _rec("H1", Language.HINDI, TriageLabel.COMPLAINT, "d"),
    ]
    scores = evaluate(records, lambda rs: [True, False, True, True])
    assert [s.language for s in scores] == ["ENGLISH", "HINDI", "ALL"]
    english, hindi, total = scores
    assert english.recall == 0.5
    assert english.precision == 0.5
    assert english.missed == ["E2"]
    assert hindi.recall == 1.0
    assert total.recall == pytest.approx(2 / 3)


def test_recall_is_none_without_complaints() -> None:
    records = [_rec("Q", Language.ENGLISH, TriageLabel.QUERY, "q")]
    score = evaluate(records, lambda rs: [False])[0]
    assert score.recall is None
    assert score.precision is None


def test_tfidf_separates_obvious_examples() -> None:
    model = TfidfCentroid(
        ["money debited not credited", "card fraud debited", "what is the rate", "branch timings"],
        [True, True, False, False],
    )
    assert model.predict("amount debited but not credited")
    assert not model.predict("what are the branch timings")


def test_baselines_run_on_the_gold_set() -> None:
    records = load_gold(GOLD)
    assert len(tfidf_leave_one_out(records)) == len(records)
    assert len(cue_classifier(records)) == len(records)


def test_llm_classifier_uses_triage_with_the_fake_model() -> None:
    def respond(request: LlmRequest) -> dict[str, JsonValue]:
        return {
            "label": "QUERY",
            "confidence": 0.99,
            "issue_type": "OTHER",
            "category": None,
            "language": "ENGLISH",
            "evidence_start": 0,
            "evidence_end": 1,
        }

    records = [
        _rec("C", Language.ENGLISH, TriageLabel.COMPLAINT, "Money debited but not credited"),
        _rec("Q", Language.ENGLISH, TriageLabel.QUERY, "What is the FD rate?"),
    ]
    classify = llm_classifier(
        FakeModel({"triage": respond}), PiiMasker(), datetime(2026, 10, 19, tzinfo=UTC)
    )
    # The gate keeps the cue-bearing complaint even though the model said QUERY.
    assert classify(records) == [True, False]


def test_main_prints_scores(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert main([str(GOLD)]) == 0
    out = capsys.readouterr().out
    assert "tfidf (leave-one-out)" in out
    assert "HINGLISH" in out
    assert "llm: not run" in out
