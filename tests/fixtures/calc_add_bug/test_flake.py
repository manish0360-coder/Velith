# mypy: ignore-errors
# A deliberately FLAKY hidden test: it alternates pass/fail across reruns by
# persisting a counter in the workspace, so the verifier's flake loop (M2-C3) sees
# the primary's reruns disagree -> flaky=True. It is fixture data, never collected by
# the main suite (tests/fixtures/conftest.py), and only run by the flake-detection
# test, which targets it explicitly.
from pathlib import Path

_counter = Path("_flake_counter")
_n = int(_counter.read_text()) + 1 if _counter.exists() else 1
_counter.write_text(str(_n))


def test_alternating() -> None:
    assert _n % 2 == 0
