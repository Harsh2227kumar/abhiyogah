"""Clearly synthetic identifiers that still pass the recognisers' format and checksum tests.

None of these belong to a real person. The Aadhaar values sit in the all-nines prefix UIDAI
uses for test residents; the card is the standard Visa test number; the rest are placeholders.
"""

from abhiyogah.perception.pii import verhoeff_valid


def _with_verhoeff(prefix: str) -> str:
    """``prefix`` plus the Verhoeff check digit that makes it valid."""
    return next(prefix + d for d in "0123456789" if verhoeff_valid(prefix + d))


FAKE_AADHAAR = _with_verhoeff("99999999001")
FAKE_AADHAAR_SPACED = f"{FAKE_AADHAAR[:4]} {FAKE_AADHAAR[4:8]} {FAKE_AADHAAR[8:]}"
FAKE_PAN = "ZZZPZ9999Z"
FAKE_ACCOUNT = "000011112222"
FAKE_IFSC = "ZZZZ0999999"
FAKE_VPA = "synthetic.user@fakebank"
FAKE_CARD = "4111 1111 1111 1111"
FAKE_MOBILE = "+91 99999 00000"
FAKE_EMAIL = "synthetic.user@example.com"
FAKE_UTR = "SYNTH00000000001"
