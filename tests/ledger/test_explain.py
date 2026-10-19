"""Explanations are rendered from the stored record only."""

from abhiyogah.ledger import render_explanation
from tests.domain.test_decision import make_record


def test_explanation_cites_every_part_of_the_record() -> None:
    """Clause, result, parameters, facts, checks, deadline, breach, compensation, actions, hash."""
    record = make_record().seal()
    text = "\n".join(render_explanation(record))
    assert "IO-CB-2026-14-1-b" in text
    assert "clause 14(1)(b)" in text
    assert "Result: BREACHED" in text
    assert "Parameter max_days = 20" in text
    assert "cl. 14(1)(b)" in text
    assert "from event EV-1" in text
    assert "Check 1:" in text
    for part in ("Deadline ", "Breach:", "Compensation ₹", "Required action:"):
        assert part in text
    assert record.hash is not None
    assert record.hash in text


def test_explanation_is_deterministic() -> None:
    """The same record always renders the same lines."""
    record = make_record().seal()
    assert render_explanation(record) == render_explanation(record.model_copy())
