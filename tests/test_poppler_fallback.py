"""poppler is the free second chance at a broken text layer -- and on Windows
and macOS it is usually absent. Reporting "not installed" as "recovery failed"
would hide the fix from the user, so the two must stay distinguishable."""
import subprocess

import pdfread


class FakeCompleted:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def test_missing_binary_is_reported_as_missing():
    def runner(*a, **kw):
        raise FileNotFoundError("pdftotext")

    assert pdfread.try_poppler("x.pdf", runner=runner) == ("missing", None)


def test_nonzero_exit_is_reported_as_failed():
    assert pdfread.try_poppler("x.pdf", runner=lambda *a, **k: FakeCompleted(1)) == ("failed", None)


def test_timeout_is_reported_as_failed():
    def runner(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="pdftotext", timeout=60)

    assert pdfread.try_poppler("x.pdf", runner=runner) == ("failed", None)


def test_success_returns_stdout():
    status, text = pdfread.try_poppler("x.pdf", runner=lambda *a, **k: FakeCompleted(0, "hello"))
    assert (status, text) == ("ok", "hello")


def test_page_range_is_passed_to_poppler():
    seen = {}

    def runner(cmd, **kw):
        seen["cmd"] = cmd
        return FakeCompleted(0, "")

    pdfread.try_poppler("x.pdf", pages=[3, 7], runner=runner)
    assert "-f" in seen["cmd"] and seen["cmd"][seen["cmd"].index("-f") + 1] == "3"
    assert "-l" in seen["cmd"] and seen["cmd"][seen["cmd"].index("-l") + 1] == "7"


def test_missing_binary_note_tells_the_user_how_to_fix_it():
    note = pdfread.recovery_note("missing", 0.0, 0)
    assert "not installed" in note and "poppler" in note
    assert "unusable" not in note      # the old bug: blaming the output


def test_bad_output_note_reports_the_score():
    note = pdfread.recovery_note("ok", 0.67, 33)
    assert "0.67" in note and "33" in note
