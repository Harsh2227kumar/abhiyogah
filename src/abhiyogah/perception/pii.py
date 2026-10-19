"""PII masking before any model call, and re-identification only inside the engine.

``PiiMasker.mask`` finds personal data with recognisers and replaces each value with a stable
placeholder such as ``<AADHAAR_1>``. The model only ever sees the masked text. The placeholder to
value mapping stays in a ``PiiVault`` that never leaves the process and is never logged
(``repr`` hides it); ``PiiVault.unmask`` restores values when the engine needs them.

Custom recognisers cover Indian identifiers: Aadhaar (Verhoeff check digit), PAN, bank account
number (needs a nearby "account" keyword), IFSC, UPI VPA, card number (Luhn check), mobile number
and email. Transaction references (UTR/RRN) are kept, because fact extraction needs them and they
do not identify a person. Any other run of nine or more digits is masked as ``NUMBER``: masking too
much is safer than leaking. Names and addresses need NER, so ``PresidioRecognizer`` wraps a
Presidio ``AnalyzerEngine`` when one is installed (``default_masker``).
"""

import importlib
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

__all__ = [
    "DEFAULT_RECOGNIZERS",
    "MaskedText",
    "PiiEntity",
    "PiiFinding",
    "PiiMasker",
    "PiiVault",
    "PresidioRecognizer",
    "Recognizer",
    "RegexRecognizer",
    "default_masker",
    "luhn_valid",
    "verhoeff_valid",
]


class PiiEntity(StrEnum):
    """Kinds of personal data the masker replaces."""

    AADHAAR = "AADHAAR"
    PAN = "PAN"
    ACCOUNT_NUMBER = "ACCOUNT_NUMBER"
    IFSC = "IFSC"
    UPI_VPA = "UPI_VPA"
    CARD_NUMBER = "CARD_NUMBER"
    MOBILE = "MOBILE"
    EMAIL = "EMAIL"
    PERSON = "PERSON"
    LOCATION = "LOCATION"
    NUMBER = "NUMBER"


@dataclass(frozen=True)
class PiiFinding:
    """One recognised value: its kind, character span and confidence."""

    entity: PiiEntity | None
    """``None`` marks a protected span that must stay readable (e.g. a UTR)."""
    start: int
    end: int
    score: float


class Recognizer(Protocol):
    """Finds PII spans in a text."""

    def find(self, text: str) -> Iterable[PiiFinding]:
        """Return every finding in ``text``."""
        ...


_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 7, 6, 8, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


def verhoeff_valid(digits: str) -> bool:
    """Whether a digit string passes the Verhoeff check (Aadhaar's last digit)."""
    check = 0
    for i, ch in enumerate(reversed(digits)):
        check = _VERHOEFF_D[check][_VERHOEFF_P[i % 8][int(ch)]]
    return check == 0


def luhn_valid(digits: str) -> bool:
    """Whether a digit string passes the Luhn check (card numbers)."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


@dataclass(frozen=True)
class RegexRecognizer:
    """A regex, an optional validator on the match and an optional nearby keyword."""

    entity: PiiEntity | None
    pattern: re.Pattern[str]
    score: float
    validate: Callable[[str], bool] | None = None
    context: re.Pattern[str] | None = None
    """When set, the match counts only if this pattern occurs within ``context_window`` before."""
    context_window: int = 40
    group: int = 0
    """Which regex group is the value (the rest of the match is context)."""

    def find(self, text: str) -> Iterable[PiiFinding]:
        """Every match that passes the validator and the context check."""
        for m in self.pattern.finditer(text):
            value, start, end = m.group(self.group), m.start(self.group), m.end(self.group)
            if self.validate is not None and not self.validate(value):
                continue
            if self.context is not None:
                before = text[max(0, start - self.context_window) : start]
                if not self.context.search(before):
                    continue
            yield PiiFinding(self.entity, start, end, self.score)


def _aadhaar(value: str) -> bool:
    d = _digits(value)
    return len(d) == 12 and d[0] not in "01" and verhoeff_valid(d)


def _card(value: str) -> bool:
    d = _digits(value)
    return 13 <= len(d) <= 19 and luhn_valid(d)


_ND = r"(?<!\d)"  # not preceded by a digit
_NDA = r"(?!\d)"  # not followed by a digit
_NB = r"(?<![A-Za-z0-9])"  # not preceded by a letter or digit
_NA = r"(?![A-Za-z0-9])"  # not followed by a letter or digit

DEFAULT_RECOGNIZERS: tuple[Recognizer, ...] = (
    # Transaction references stay readable: extraction needs them (UTR/RRN are not personal data).
    # Checksum-valid Aadhaar and card numbers still win over this, so a mislabelled ID is masked.
    RegexRecognizer(
        None,
        re.compile(
            r"(?i)\b(?:utr|rrn|ref(?:erence)?|txn\s*id|transaction\s*id)"
            r"(?:\s*(?:no\.?|number|#))?[\s:.\-]{0,3}([A-Z0-9]{10,22})\b"
        ),
        0.85,
        group=1,
    ),
    RegexRecognizer(
        PiiEntity.AADHAAR,
        re.compile(_ND + r"[2-9]\d{3}[ \-]?\d{4}[ \-]?\d{4}" + _NDA),
        0.95,
        validate=_aadhaar,
    ),
    RegexRecognizer(
        PiiEntity.CARD_NUMBER,
        re.compile(_ND + r"\d{4}(?:[ \-]?\d{4}){2}[ \-]?\d{1,7}" + _NDA),
        0.9,
        validate=_card,
    ),
    RegexRecognizer(
        PiiEntity.PAN,
        re.compile(r"(?i)" + _NB + r"[A-Z]{3}[PCHFATBLJG][A-Z]\d{4}[A-Z]" + _NA),
        0.9,
    ),
    RegexRecognizer(
        PiiEntity.IFSC, re.compile(r"(?i)" + _NB + r"[A-Z]{4}0[A-Z0-9]{6}" + _NA), 0.85
    ),
    RegexRecognizer(
        PiiEntity.EMAIL,
        re.compile(r"[\w.+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+"),
        0.85,
    ),
    RegexRecognizer(
        PiiEntity.UPI_VPA,
        re.compile(r"[\w.\-]{2,256}@[A-Za-z][A-Za-z0-9]{1,63}" + r"(?![\w.\-]*\.[A-Za-z])"),
        0.8,
    ),
    RegexRecognizer(
        PiiEntity.MOBILE,
        re.compile(r"(?<![\d+])(?:\+91[ \-]?|0)?[6-9]\d{4}[ \-]?\d{5}" + _NDA),
        0.75,
    ),
    RegexRecognizer(
        PiiEntity.ACCOUNT_NUMBER,
        re.compile(_ND + r"\d{9,18}" + _NDA),
        0.7,
        context=re.compile(r"(?i)(?:account|a/c|acct|acc\.?|खाता|khata)"),
    ),
    RegexRecognizer(PiiEntity.NUMBER, re.compile(_ND + r"\d{9,}" + _NDA), 0.3),
)
"""Recognisers in priority order; overlaps resolve to the higher score, then the longer span."""


class _PresidioResult(Protocol):
    entity_type: str
    start: int
    end: int
    score: float


class _PresidioAnalyzer(Protocol):
    def analyze(self, *, text: str, language: str) -> Sequence[Any]:
        """Presidio ``AnalyzerEngine.analyze``."""
        ...


_PRESIDIO_ENTITIES: dict[str, PiiEntity] = {
    "PERSON": PiiEntity.PERSON,
    "LOCATION": PiiEntity.LOCATION,
    "EMAIL_ADDRESS": PiiEntity.EMAIL,
    "PHONE_NUMBER": PiiEntity.MOBILE,
    "CREDIT_CARD": PiiEntity.CARD_NUMBER,
    "IN_PAN": PiiEntity.PAN,
    "IN_AADHAAR": PiiEntity.AADHAAR,
}


@dataclass(frozen=True)
class PresidioRecognizer:
    """Adds Presidio's findings (names, places and its own recognisers) to the custom ones."""

    analyzer: _PresidioAnalyzer
    language: str = "en"
    min_score: float = 0.5

    def find(self, text: str) -> Iterable[PiiFinding]:
        """Presidio results of a known entity type above ``min_score``."""
        for r in self.analyzer.analyze(text=text, language=self.language):
            entity = _PRESIDIO_ENTITIES.get(str(r.entity_type))
            if entity is not None and float(r.score) >= self.min_score:
                yield PiiFinding(entity, int(r.start), int(r.end), float(r.score))


@dataclass
class PiiVault:
    """Placeholder to original value. Stays in the engine; never logged, stored or sent out."""

    _values: dict[str, str] = field(default_factory=dict)

    def __repr__(self) -> str:
        """Never show the values."""
        return f"PiiVault({len(self._values)} values)"

    def __len__(self) -> int:
        """How many values are held."""
        return len(self._values)

    def placeholders(self) -> list[str]:
        """The placeholders in this vault (safe to log)."""
        return list(self._values)

    def unmask(self, text: str) -> str:
        """Put the original values back into ``text`` (engine-internal use only)."""
        return re.sub(r"<[A-Z_]+_\d+>", lambda m: self._values.get(m.group(0), m.group(0)), text)

    def _put(self, placeholder: str, value: str) -> None:
        self._values[placeholder] = value


@dataclass(frozen=True)
class MaskedText:
    """Masked text that may be sent to a model, plus the vault to reverse it."""

    text: str
    vault: PiiVault = field(repr=False)
    entities: tuple[PiiEntity, ...]
    """Kinds found, in text order (safe to log)."""


class PiiMasker:
    """Applies recognisers and replaces every finding with a placeholder."""

    def __init__(self, recognizers: Sequence[Recognizer] = DEFAULT_RECOGNIZERS) -> None:
        """Use these recognisers (default: the custom Indian-identifier set)."""
        self._recognizers = tuple(recognizers)

    def mask(self, text: str) -> MaskedText:
        """Mask ``text``. The same value gets the same placeholder within one call."""
        findings = sorted(
            (f for r in self._recognizers for f in r.find(text)),
            key=lambda f: (-f.score, -(f.end - f.start), f.start),
        )
        chosen: list[PiiFinding] = []
        for f in findings:
            if all(f.end <= c.start or f.start >= c.end for c in chosen):
                chosen.append(f)
        chosen.sort(key=lambda f: f.start)

        vault = PiiVault()
        by_value: dict[tuple[PiiEntity, str], str] = {}
        counters: dict[PiiEntity, int] = {}
        out: list[str] = []
        entities: list[PiiEntity] = []
        pos = 0
        for f in chosen:
            if f.entity is None:
                continue
            value = text[f.start : f.end]
            key = (f.entity, value)
            placeholder = by_value.get(key)
            if placeholder is None:
                counters[f.entity] = counters.get(f.entity, 0) + 1
                placeholder = f"<{f.entity.value}_{counters[f.entity]}>"
                by_value[key] = placeholder
                vault._put(placeholder, value)
            out.append(text[pos : f.start])
            out.append(placeholder)
            entities.append(f.entity)
            pos = f.end
        out.append(text[pos:])
        return MaskedText(text="".join(out), vault=vault, entities=tuple(entities))


def default_masker(use_presidio: bool = True) -> PiiMasker:
    """The custom recognisers, plus Presidio's NER when ``presidio_analyzer`` is installed."""
    recognizers: list[Recognizer] = list(DEFAULT_RECOGNIZERS)
    if use_presidio:
        try:
            presidio = importlib.import_module("presidio_analyzer")
        except ImportError:
            presidio = None
        if presidio is not None:
            recognizers.append(PresidioRecognizer(presidio.AnalyzerEngine()))
    return PiiMasker(recognizers)
