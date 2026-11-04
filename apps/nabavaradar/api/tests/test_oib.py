"""OIB checksum (ISO 7064 MOD 11,10). Valid cases are real OIBs from the recorded sources."""

from __future__ import annotations

import pytest

from nabavaradar_api.oib import is_valid_oib, normalise_oib, oib_check_digit

# real OIBs: Sudreg subjects (2026-11-04 snapshot) and winners in TED result notices
VALID = ["92803032010", "76860791838", "65605433360", "70869514300", "49733628869", "61817894937"]


@pytest.mark.parametrize("oib", VALID)
def test_valid_oibs(oib: str) -> None:
    assert is_valid_oib(oib)


@pytest.mark.parametrize("oib", VALID)
def test_changing_the_check_digit_invalidates(oib: str) -> None:
    wrong = str((int(oib[10]) + 1) % 10)
    assert not is_valid_oib(oib[:10] + wrong)


@pytest.mark.parametrize("oib", VALID)
def test_changing_any_other_digit_invalidates(oib: str) -> None:
    # MOD 11,10 detects every single-digit substitution
    for i in range(10):
        bad = oib[:i] + str((int(oib[i]) + 3) % 10) + oib[i + 1 :]
        assert not is_valid_oib(bad), (oib, i)


@pytest.mark.parametrize(
    "value",
    ["", "123", "9280303201", "928030320100", "9280303201a", "abcdefghijk", " 92803032010", "12345678901", "00000000000"],
)
def test_malformed_or_wrong_oibs(value: str) -> None:
    assert not is_valid_oib(value)


def test_check_digit_of_ten_maps_to_zero() -> None:
    # 10 digits whose raw result is 10 must yield 0: 92803032010 ends in 0 and is valid
    assert oib_check_digit("9280303201") == 0


def test_non_string_is_invalid() -> None:
    assert not is_valid_oib(92803032010)  # type: ignore[arg-type]


def test_normalise_pads_numbers_that_lost_leading_zeros() -> None:
    assert normalise_oib(1234567890) == "01234567890"
    assert normalise_oib("92803032010") == "92803032010"
    assert normalise_oib(92803032010) == "92803032010"
