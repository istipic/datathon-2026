"""OIB (Croatian personal/company identification number) validation: ISO 7064, MOD 11,10."""

from __future__ import annotations

import re

_OIB_RE = re.compile(r"^\d{11}$")


def oib_check_digit(first10: str) -> int:
    """Check digit for the first ten digits of an OIB (ISO 7064 MOD 11,10)."""
    a = 10
    for ch in first10:
        a = (a + int(ch)) % 10
        if a == 0:
            a = 10
        a = (a * 2) % 11
    check = 11 - a
    return 0 if check == 10 else check


def is_valid_oib(value: str) -> bool:
    """True for an 11-digit string whose last digit is the correct check digit."""
    if not isinstance(value, str) or not _OIB_RE.match(value):
        return False
    return oib_check_digit(value[:10]) == int(value[10])


def normalise_oib(value: str | int) -> str:
    """OIB as an 11-character string: numbers lose leading zeros in the Sudreg API, so pad them."""
    return str(value).strip().zfill(11)
