"""End-to-end runs against PDFs built in conftest, checking the routing
decision the rest of the skill depends on."""
import json

import pytest

import pdfread

pytest.importorskip("pdf_inspector", reason="the skill's own dependency")


def test_clean_pdf_routes_to_text_and_prints_markdown(clean_pdf, capsys):
    code = pdfread.main([str(clean_pdf)])
    out = capsys.readouterr().out
    assert code == 0
    assert "route: TEXT" in out
    assert "=== MARKDOWN ===" in out
    assert "Mathematical Theory" in out


def test_detect_only_stops_before_extraction(clean_pdf, capsys):
    code = pdfread.main([str(clean_pdf), "--detect-only"])
    out = capsys.readouterr().out
    assert code == 0
    assert "=== VERDICT ===" in out
    assert "=== MARKDOWN ===" not in out


def test_json_verdict_is_machine_readable(clean_pdf, capsys):
    pdfread.main([str(clean_pdf), "--detect-only", "--json"])
    verdict = json.loads(capsys.readouterr().out.strip())
    assert verdict["route"] == "TEXT"
    assert verdict["page_count"] == 2
    assert verdict["pages_needing_visual_read"] == []


def test_page_subset_is_honoured(clean_pdf, capsys):
    pdfread.main([str(clean_pdf), "--pages", "2", "--detect-only", "--json"])
    assert json.loads(capsys.readouterr().out.strip())["route"] == "TEXT"


def test_broken_cid_font_is_not_passed_off_as_text(broken_cid_pdf, capsys):
    """The whole point of the skill: a PDF that reports itself text-based with
    full confidence, but whose characters are meaningless, must not reach the
    caller as content."""
    code = pdfread.main([str(broken_cid_pdf), "--no-fallback"])
    out = capsys.readouterr().out
    assert code == 2
    assert "render_pages.py" in out
    assert "透明物体" not in out


def test_no_fallback_says_so_rather_than_blaming_poppler(broken_cid_pdf, capsys):
    pdfread.main([str(broken_cid_pdf), "--no-fallback"])
    out = capsys.readouterr().out
    assert "--no-fallback" in out
    assert "not installed" not in out


def test_blank_page_does_not_route_to_text(blank_pdf, capsys):
    pdfread.main([str(blank_pdf), "--detect-only", "--json"])
    assert json.loads(capsys.readouterr().out.strip())["route"] != "TEXT"
