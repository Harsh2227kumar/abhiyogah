"""Trigger conditions over ``ComplaintFacts``: a deliberately tiny grammar, no ``eval``.

A condition is one or more clauses joined by `` and ``. Each clause names a ``ComplaintFacts`` field
and one of these tests::

    outcome in [PARTIALLY_RESOLVED, WHOLLY_REJECTED]
    channel not in [ATM, MICRO_ATM]
    entity_type == COMMERCIAL_BANK
    channel != OTHER
    amount_paise >= 100000          (also >, <, <=; integer facts only)
    external_tat_days is known
    external_tat_days is unknown

Values compare by their YAML/JSON spelling: enum values, ISO dates, integers. A clause on an unknown
fact (other than ``is known`` / ``is unknown``) cannot be decided, so the condition is undecided and
the evaluator reports ``INSUFFICIENT_FACTS``. Nothing is assumed. Anything outside this grammar
raises ``ConditionSyntaxError``.
"""

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum

from abhiyogah.domain.complaint import ComplaintFacts, Fact
from abhiyogah.domain.decision import ConditionTrace
from abhiyogah.evaluator.errors import ConditionSyntaxError

__all__ = ["ConditionOutcome", "evaluate_condition", "fact_spelling"]

_FIELDS = frozenset(name for name in ComplaintFacts.model_fields if name != "complaint_id")
_CLAUSE = re.compile(
    r"^(?P<field>[a-z][a-z0-9_]*)\s+"
    r"(?:(?P<known>is\s+(?:known|unknown))"
    r"|(?P<setop>not\s+in|in)\s*\[(?P<items>[^\]]*)\]"
    r"|(?P<cmp>==|!=|>=|<=|>|<)\s*(?P<value>\S+))$"
)


def fact_spelling(value: object) -> str:
    """The YAML/JSON spelling of a fact value, used for comparisons and traces."""
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _unquote(s: str) -> str:
    """Strip whitespace and one pair of matching quotes."""
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1]
    return s


@dataclass(frozen=True, slots=True)
class ConditionOutcome:
    """``result`` is True/False, or None when a needed fact is unknown."""

    result: bool | None
    trace: tuple[ConditionTrace, ...]
    facts_read: tuple[str, ...]
    missing: tuple[str, ...]


def _check_clause(clause: str, facts: ComplaintFacts) -> tuple[bool | None, str, str]:
    """Evaluate one clause: (result, field name, detail)."""
    m = _CLAUSE.match(clause.strip())
    if m is None:
        raise ConditionSyntaxError(f"unsupported condition clause: {clause!r}")
    field = m["field"]
    if field not in _FIELDS:
        raise ConditionSyntaxError(f"{field!r} is not a ComplaintFacts field")
    fact: Fact[object] | None = getattr(facts, field)
    if m["known"]:
        want_known = m["known"].split()[-1] == "known"
        return (fact is not None) == want_known, field, f"{field} is {_shown(fact)}"
    if fact is None:
        return None, field, f"{field} is unknown"
    actual = fact_spelling(fact.value)
    if m["setop"]:
        items = [_unquote(i) for i in m["items"].split(",") if i.strip()]
        inside = actual in items
        result = inside if m["setop"] == "in" else not inside
        return result, field, f"{field} = {actual}"
    op, value = m["cmp"], _unquote(m["value"])
    if op in ("==", "!="):
        return (actual == value) == (op == "=="), field, f"{field} = {actual}"
    if not isinstance(fact.value, int) or isinstance(fact.value, bool):
        raise ConditionSyntaxError(f"{op!r} needs an integer fact, {field!r} is not one")
    try:
        bound = int(value)
    except ValueError as exc:
        raise ConditionSyntaxError(f"{op!r} needs an integer, got {value!r}") from exc
    results = {
        ">": fact.value > bound,
        "<": fact.value < bound,
        ">=": fact.value >= bound,
        "<=": fact.value <= bound,
    }
    return results[op], field, f"{field} = {actual}"


def _shown(fact: Fact[object] | None) -> str:
    """Trace text for a fact that may be unknown."""
    return "unknown" if fact is None else f"known ({fact_spelling(fact.value)})"


def evaluate_condition(condition: str | None, facts: ComplaintFacts) -> ConditionOutcome:
    """Evaluate a trigger condition; ``None`` (no condition) is true."""
    if condition is None or not condition.strip():
        return ConditionOutcome(True, (), (), ())
    trace: list[ConditionTrace] = []
    read: list[str] = []
    missing: list[str] = []
    overall: bool | None = True
    for clause in re.split(r"\s+and\s+", condition.strip()):
        result, field, detail = _check_clause(clause, facts)
        read.append(field)
        if result is None:
            missing.append(field)
            overall = None if overall is not False else False
        elif not result:
            overall = False
        trace.append(ConditionTrace(condition=clause.strip(), result=bool(result), detail=detail))
    return ConditionOutcome(overall, tuple(trace), tuple(read), tuple(missing))
