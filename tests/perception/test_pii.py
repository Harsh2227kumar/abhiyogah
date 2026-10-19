"""PII masking: every recogniser, placeholder stability, re-identification and Presidio hook."""

from dataclasses import dataclass

import pytest

from abhiyogah.perception.pii import (
    DEFAULT_RECOGNIZERS,
    PiiEntity,
    PiiMasker,
    PresidioRecognizer,
    default_masker,
    luhn_valid,
    verhoeff_valid,
)
from tests.perception.synthetic import (
    FAKE_AADHAAR,
    FAKE_AADHAAR_SPACED,
    FAKE_ACCOUNT,
    FAKE_CARD,
    FAKE_EMAIL,
    FAKE_IFSC,
    FAKE_MOBILE,
    FAKE_PAN,
    FAKE_UTR,
    FAKE_VPA,
)

MASKER = PiiMasker()


def test_checksums() -> None:
    assert verhoeff_valid(FAKE_AADHAAR)
    assert not verhoeff_valid(FAKE_AADHAAR[:-1] + str((int(FAKE_AADHAAR[-1]) + 1) % 10))
    assert luhn_valid("4111111111111111")
    assert not luhn_valid("4111111111111112")


@pytest.mark.parametrize(
    ("text", "entity"),
    [
        (f"My Aadhaar is {FAKE_AADHAAR}.", PiiEntity.AADHAAR),
        (f"Aadhaar {FAKE_AADHAAR_SPACED} linked", PiiEntity.AADHAAR),
        (f"PAN: {FAKE_PAN}", PiiEntity.PAN),
        (f"debited from account no. {FAKE_ACCOUNT} yesterday", PiiEntity.ACCOUNT_NUMBER),
        (f"मेरे खाता {FAKE_ACCOUNT} से पैसे कटे", PiiEntity.ACCOUNT_NUMBER),
        (f"branch IFSC {FAKE_IFSC}", PiiEntity.IFSC),
        (f"sent to {FAKE_VPA} via UPI", PiiEntity.UPI_VPA),
        (f"card {FAKE_CARD} was charged", PiiEntity.CARD_NUMBER),
        (f"call me on {FAKE_MOBILE}", PiiEntity.MOBILE),
        ("call me on 9999900000", PiiEntity.MOBILE),
        (f"mail {FAKE_EMAIL}", PiiEntity.EMAIL),
        ("number 123456789012345 is mine", PiiEntity.NUMBER),
    ],
)
def test_each_recogniser_masks_its_value(text: str, entity: PiiEntity) -> None:
    masked = MASKER.mask(text)
    assert masked.entities == (entity,)
    assert f"<{entity.value}_1>" in masked.text
    assert masked.vault.unmask(masked.text) == text


def test_no_raw_value_survives_in_a_mixed_text() -> None:
    values = [FAKE_AADHAAR, FAKE_PAN, FAKE_ACCOUNT, FAKE_IFSC, FAKE_VPA, FAKE_CARD, FAKE_EMAIL]
    text = (
        f"Aadhaar {FAKE_AADHAAR}, PAN {FAKE_PAN}, a/c {FAKE_ACCOUNT}, IFSC {FAKE_IFSC}, "
        f"VPA {FAKE_VPA}, card {FAKE_CARD}, email {FAKE_EMAIL}, mobile {FAKE_MOBILE}."
    )
    masked = MASKER.mask(text)
    for value in [*values, FAKE_MOBILE]:
        assert value not in masked.text
    assert masked.vault.unmask(masked.text) == text


def test_utr_and_amounts_and_dates_stay_readable() -> None:
    text = f"Rs 15,000 debited on 03/10/2026, UTR {FAKE_UTR}, RRN: 123412345678 not credited."
    masked = MASKER.mask(text)
    assert FAKE_UTR in masked.text
    assert "123412345678" in masked.text
    assert "15,000" in masked.text
    assert "03/10/2026" in masked.text


def test_checksum_valid_aadhaar_wins_over_a_reference_label() -> None:
    masked = MASKER.mask(f"ref {FAKE_AADHAAR}")
    assert FAKE_AADHAAR not in masked.text


def test_same_value_gets_the_same_placeholder() -> None:
    masked = MASKER.mask(f"{FAKE_PAN} and again {FAKE_PAN}; other ZZZPY8888Y")
    assert masked.text == "<PAN_1> and again <PAN_1>; other <PAN_2>"
    assert len(masked.vault) == 2


def test_vault_repr_hides_values() -> None:
    masked = MASKER.mask(f"PAN {FAKE_PAN}")
    assert FAKE_PAN not in repr(masked.vault)
    assert FAKE_PAN not in repr(masked)
    assert masked.vault.placeholders() == ["<PAN_1>"]


def test_unknown_placeholder_is_left_alone() -> None:
    masked = MASKER.mask("nothing here")
    assert masked.text == "nothing here"
    assert masked.vault.unmask("<PAN_9>") == "<PAN_9>"


@dataclass
class _Result:
    entity_type: str
    start: int
    end: int
    score: float


class _FakeAnalyzer:
    def analyze(self, *, text: str, language: str) -> list[_Result]:
        start = text.index("Synthetic Person")
        return [
            _Result("PERSON", start, start + len("Synthetic Person"), 0.85),
            _Result("PERSON", 0, 2, 0.1),  # below min_score
            _Result("NRP", 0, 2, 0.9),  # unmapped type
        ]


def test_presidio_findings_are_added() -> None:
    masker = PiiMasker([*DEFAULT_RECOGNIZERS, PresidioRecognizer(_FakeAnalyzer())])
    masked = masker.mask(f"I am Synthetic Person, PAN {FAKE_PAN}")
    assert masked.text == "I am <PERSON_1>, PAN <PAN_1>"


def test_default_masker_without_presidio_masks() -> None:
    assert default_masker(use_presidio=False).mask(f"PAN {FAKE_PAN}").text == "PAN <PAN_1>"
