"""Invariants of the behaviour matrix.

These assert properties that must hold no matter WHICH parsers are installed,
so they pass identically on a laptop without poppler and in CI with everything.
The matrix numbers are environment-dependent; these invariants are not, which
is why they -- not the numbers -- are what a local run should check.
"""
from __future__ import annotations

import pytest

from bench import fixtures, parsers
from bench.run import build


@pytest.fixture(scope="module")
def matrix(tmp_path_factory):
    d = tmp_path_factory.mktemp("control")
    fixtures.build(d)
    return build(d)


def test_no_false_positives_on_clean_twins(matrix):
    """The instrument never claims a behaviour on the payload-free twin.

    This is the credibility floor: a matrix that fires on clean documents
    measures nothing. Checked per cell so the failure names the parser.
    """
    offenders = [(c["parser"], c["behaviour"]) for c in matrix["cells"] if c["false_positive"]]
    assert offenders == [], f"false positives: {offenders}"


def test_visible_control_text_survives_everywhere(matrix):
    """Every parser that succeeded still returns the visible sentence.

    Guards the fixture itself. A fixture that is broken -- the trap of the
    abandoned failure-mode benchmark -- shows up here as a parser that
    returns nothing, rather than as an exciting all-parsers-fail result.
    """
    broken = [c["parser"] for c in matrix["cells"]
              if not c["error"] and not c["control_text_intact"]]
    assert broken == [], f"fixture or adapter broken for: {sorted(set(broken))}"


def test_every_kept_behaviour_actually_splits_parsers(matrix):
    """G2. A class every parser treats alike carries no information."""
    for name, stats in matrix["behaviours"].items():
        if stats["verdict"].startswith("keep"):
            assert 0 < stats["n_occurred"] < stats["n_parsers"], (
                f"{name} kept but not discriminative: "
                f"{stats['n_occurred']}/{stats['n_parsers']}"
            )


def test_unavailable_parser_is_excluded_not_counted_clean(tmp_path, monkeypatch):
    """A parser that cannot run must raise n_error, never lower n_occurred.

    Without this, 'poppler is not installed' silently reads as
    'pdftotext does not leak' -- an environment defect wearing the costume
    of a safety result.
    """
    def unavailable(path):
        raise FileNotFoundError("simulated: binary not on PATH")

    reg = dict(parsers.REGISTRY)
    reg["ghost"] = ("unavailable", unavailable)
    monkeypatch.setattr(parsers, "REGISTRY", reg)

    fixtures.build(tmp_path)
    m = build(tmp_path)

    for name, stats in m["behaviours"].items():
        assert "ghost" in stats["errored_parsers"], f"{name} lost the errored parser"
        # Relative, not absolute: this machine may legitimately be missing
        # poppler too. The invariant is that errored cells leave the parser
        # count, not that exactly one parser failed.
        assert stats["n_parsers"] == len(reg) - stats["n_error"], (
            f"{name}: {stats['n_error']} errored but n_parsers={stats['n_parsers']} "
            f"of {len(reg)}"
        )
    ghost_cells = [c for c in m["cells"] if c["parser"] == "ghost"]
    assert ghost_cells and all(c["error"] and not c["occurred"] for c in ghost_cells)


def test_config_banner_is_not_a_behaviour_signal(tmp_path, monkeypatch):
    """A message emitted on BOTH arms reports installation, not this document.

    pymupdf4llm announces its OCR backend on every call, clean files included.
    Counting that as 'the parser told the caller' inverts the headline result.
    """
    import sys

    def chatty(path):
        print("backend: tesseract available", file=sys.stderr)   # same on both arms
        return "Quarterly revenue rose"

    reg = dict(parsers.REGISTRY)
    reg["chatty"] = ("0.0", chatty)
    monkeypatch.setattr(parsers, "REGISTRY", reg)

    fixtures.build(tmp_path)
    m = build(tmp_path)

    cells = [c for c in m["cells"] if c["parser"] == "chatty"]
    assert cells, "chatty parser missing from matrix"
    for c in cells:
        assert c["config_banner"] == ["stderr"], "banner should be recorded separately"
        assert c["signalled"] is False, "identical message on both arms is not a signal"
