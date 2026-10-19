"""Trigger conditions over ``ComplaintFacts``: a deliberately tiny grammar, no ``eval``.

The grammar and its semantics follow ``rules/obligations/_conventions.md`` (rule-pack stream). A
condition is clauses joined by `` and `` and `` or `` (``and`` binds tighter), with parentheses for
grouping, e.g. ``outcome is set and (exclusion_category is not set or exclusion_category not in
[14_5_c])``. Every clause is evaluated and traced; none is skipped. Each clause names a
``ComplaintFacts`` field and one of these tests::

    outcome in [PARTIALLY_RESOLVED, WHOLLY_REJECTED]
    channel not in [ATM, MICRO_ATM]
    entity_type == COMMERCIAL_BANK
    channel != OTHER
    amount_paise >= 100000          (also >, <, <=; integer facts only)
    external_tat_days is set        (also: is known)
    external_tat_days is not set    (also: is unknown)

Values compare by their YAML/JSON spelling: enum values, ISO dates, integers. A clause on an unknown
fact (other than the set/known tests) is false: the fact never defaults to a value, and the trace
says it was unknown. Anything outside this grammar raises ``ConditionSyntaxError``.
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
    r"(?:(?P<known>is\s+(?:not\s+set|set|known|unknown))"
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
    """Whether the condition holds, its trace, the facts read and those that were unknown."""

    result: bool
    trace: tuple[ConditionTrace, ...]
    facts_read: tuple[str, ...]
    missing: tuple[str, ...]


def _check_clause(clause: str, facts: ComplaintFacts) -> tuple[bool | None, str, str]:
    """Evaluate one clause: (result or None if the fact is unknown, field name, detail)."""
    m = _CLAUSE.match(clause.strip())
    if m is None:
        raise ConditionSyntaxError(f"unsupported condition clause: {clause!r}")
    field = m["field"]
    if field not in _FIELDS:
        raise ConditionSyntaxError(f"{field!r} is not a ComplaintFacts field")
    fact: Fact[object] | None = getattr(facts, field)
    if m["known"]:
        want_known = m["known"].split()[-1] in ("known", "set") and "not" not in m["known"]
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


def _tokens(condition: str) -> list[str]:
    """Split into ``(``, ``)``, ``and``, ``or`` and clause strings; ``[...]`` lists stay whole."""
    tokens: list[str] = []
    words: list[str] = []
    word = ""
    depth = 0

    def flush_word() -> None:
        nonlocal word
        if word:
            words.append(word)
            word = ""

    def flush_clause() -> None:
        flush_word()
        if words:
            tokens.append(" ".join(words))
            words.clear()

    for ch in condition:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if depth == 0 and ch in "()":
            flush_clause()
            tokens.append(ch)
        elif depth == 0 and ch.isspace():
            flush_word()
            if words and words[-1] in ("and", "or"):
                op = words.pop()
                flush_clause()
                tokens.append(op)
        else:
            word += ch
    flush_word()
    if words and words[-1] in ("and", "or"):
        raise ConditionSyntaxError(f"condition ends with an operator: {condition!r}")
    flush_clause()
    if depth != 0:
        raise ConditionSyntaxError(f"unbalanced [ ] in condition: {condition!r}")
    return tokens


class _Parser:
    """Recursive descent: ``expr := term (or term)*``, ``term := factor (and factor)*``."""

    def __init__(self, tokens: list[str], facts: ComplaintFacts) -> None:
        self.tokens = tokens
        self.pos = 0
        self.facts = facts
        self.trace: list[ConditionTrace] = []
        self.read: list[str] = []
        self.missing: list[str] = []

    def _peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def parse(self) -> bool:
        """Parse the whole condition; every clause is evaluated and traced, none short-circuited."""
        result = self._expr()
        if self._peek() is not None:
            raise ConditionSyntaxError(f"unexpected {self._peek()!r} in condition")
        return result

    def _expr(self) -> bool:
        results = [self._term()]
        while self._peek() == "or":
            self.pos += 1
            results.append(self._term())
        return any(results)

    def _term(self) -> bool:
        results = [self._factor()]
        while self._peek() == "and":
            self.pos += 1
            results.append(self._factor())
        return all(results)

    def _factor(self) -> bool:
        tok = self._peek()
        if tok is None or tok in ("and", "or", ")"):
            raise ConditionSyntaxError(f"expected a clause, got {tok!r}")
        self.pos += 1
        if tok == "(":
            result = self._expr()
            if self._peek() != ")":
                raise ConditionSyntaxError("missing ')' in condition")
            self.pos += 1
            return result
        clause_result, field, detail = _check_clause(tok, self.facts)
        self.read.append(field)
        if clause_result is None:
            self.missing.append(field)
        self.trace.append(ConditionTrace(condition=tok, result=bool(clause_result), detail=detail))
        return bool(clause_result)


def evaluate_condition(condition: str | None, facts: ComplaintFacts) -> ConditionOutcome:
    """Evaluate a trigger condition; ``None`` (no condition) is true."""
    if condition is None or not condition.strip():
        return ConditionOutcome(True, (), (), ())
    parser = _Parser(_tokens(condition.strip()), facts)
    result = parser.parse()
    if not parser.trace:
        raise ConditionSyntaxError(f"condition has no clause: {condition!r}")
    return ConditionOutcome(result, tuple(parser.trace), tuple(parser.read), tuple(parser.missing))
