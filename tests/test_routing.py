"""decide_route turns a classification into the one decision that matters:
extract cheaply, or spend context looking at pixels."""
import pytest

import pdfread


def route(*args, **kw):
    return pdfread.decide_route(*args, **kw)[0]


def test_clean_document_routes_to_text():
    assert route(3, [], False) == "TEXT"


def test_every_page_needing_ocr_routes_to_visual():
    r, visual, scope = pdfread.decide_route(2, [1, 2], False)
    assert r == "VISUAL"
    assert visual == [1, 2]


def test_some_pages_needing_ocr_routes_to_mixed():
    r, visual, _ = pdfread.decide_route(3, [2], False)
    assert r == "MIXED"
    assert visual == [2]


def test_encoding_issue_outranks_the_per_page_list():
    """pdf-inspector can report a broken encoding while still calling the
    document text_based with full confidence. When it does, no page of its
    text is trustworthy, whatever pages_needing_ocr says."""
    r, visual, _ = pdfread.decide_route(2, [], True)
    assert r == "VISUAL"
    assert visual == [1, 2]


def test_page_subset_that_avoids_the_bad_page_is_still_text():
    assert route(5, [4], False, [1, 2]) == "TEXT"


def test_page_subset_that_includes_the_bad_page_is_mixed():
    r, visual, _ = pdfread.decide_route(5, [4], False, [3, 4])
    assert r == "MIXED"
    assert visual == [4]


def test_page_subset_consisting_only_of_bad_pages_is_visual():
    assert route(5, [4], False, [4]) == "VISUAL"


def test_scope_follows_the_requested_pages():
    _, _, scope = pdfread.decide_route(9, [], False, [2, 5])
    assert scope == [2, 5]


def test_document_with_no_pages_does_not_claim_visual():
    r, visual, scope = pdfread.decide_route(0, [], False)
    assert (r, visual, scope) == ("TEXT", [], [])


@pytest.mark.parametrize("ocr", [None, ()])
def test_missing_ocr_list_is_treated_as_empty(ocr):
    assert route(2, ocr, False) == "TEXT"
