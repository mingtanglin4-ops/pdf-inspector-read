"""The blank-render check exists because poppler silently draws CJK pages with
no glyphs, and 'the form is empty' is a believable wrong answer."""
import pytest

pytest.importorskip("pypdfium2", reason="renderer under test")

import render_pages


def test_page_with_text_is_not_flagged_blank(clean_pdf, tmp_path):
    (path, ink), = render_pages.render(clean_pdf, pages=[1], dpi=100, out_dir=str(tmp_path))
    assert ink > render_pages.BLANK_INK_THRESHOLD
    assert not render_pages.is_probably_blank(ink)


def test_page_with_only_rules_is_flagged_blank(blank_pdf, tmp_path):
    """A rectangle outline and nothing else -- the exact shape of a font
    failure. It must be flagged, not returned as a readable page."""
    (path, ink), = render_pages.render(blank_pdf, pages=[1], dpi=100, out_dir=str(tmp_path))
    assert render_pages.is_probably_blank(ink)


def test_render_writes_one_png_per_requested_page(clean_pdf, tmp_path):
    results = render_pages.render(clean_pdf, pages=[1, 2], dpi=72, out_dir=str(tmp_path))
    assert len(results) == 2
    assert all(p.endswith(".png") for p, _ in results)
    assert len(list(tmp_path.glob("*.png"))) == 2
