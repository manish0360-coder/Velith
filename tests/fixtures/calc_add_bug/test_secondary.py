# mypy: ignore-errors
# Held-out SECONDARY suite (the model-gap detector, M2). It is never shown to the
# proposer (the proposer reads no repo content) and is re-materialized from this
# pristine fixture after patch application, so a candidate patch cannot tamper with
# it. A patch that hardcodes the primary's expected value (a "cheating" fix) passes
# the primary but fails these held-out cases -> secondary_passed=False. Fixture data,
# never collected by the main suite (tests/fixtures/conftest.py).
from calculator import add


def test_negatives() -> None:
    assert add(-1, 1) == 0


def test_zero() -> None:
    assert add(0, 0) == 0


def test_other_pair() -> None:
    assert add(10, 5) == 15
