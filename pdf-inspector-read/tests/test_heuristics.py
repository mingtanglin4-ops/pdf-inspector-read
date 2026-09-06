"""The mojibake detector is the load-bearing heuristic: if it says a broken
text layer is fine, the agent quotes nonsense to the user."""
import pdfread

# Captured from pdf_inspector.extract_text() on a real PDF whose CJK font has
# no /ToUnicode map. This is what "looks like text but is not" actually is.
MOJIBAKE = "7G 7    ‹        ˝ 7G 7    ‹        ˝D                  D `      " * 4

ENGLISH = (
    "The fundamental problem of communication is that of reproducing at one point "
    "either exactly or approximately a message selected at another point. Frequently "
    "the messages have meaning, that is they refer to or are correlated according to "
    "some system with certain physical or conceptual entities."
)

JAPANESE = "".join([
    "羽田空港新飛行経路に係る航空機騒音の測定結果 立会小学校 台場小学校 ",
    "測定日 最大騒音レベル 騒音発生回数 南風運用の有無 最大値 最小値 平均値 ",
]) * 6


def test_empty_and_none_are_not_text():
    assert pdfread.looks_like_text("") == (False, 0.0, 0)
    assert pdfread.looks_like_text(None) == (False, 0.0, 0)
    assert pdfread.looks_like_text("   \n\t  ") == (False, 0.0, 0)


def test_mojibake_is_rejected():
    usable, ratio, words = pdfread.looks_like_text(MOJIBAKE)
    assert not usable
    assert ratio < pdfread.MIN_LETTER_RATIO


def test_english_prose_is_accepted():
    usable, ratio, words = pdfread.looks_like_text(ENGLISH)
    assert usable
    assert ratio > 0.9 and words >= pdfread.MIN_WORDS


def test_japanese_prose_is_accepted():
    """CJK must not be mistaken for mojibake just because it is not Latin."""
    usable, ratio, words = pdfread.looks_like_text(JAPANESE)
    assert usable


def test_scanned_page_is_rejected_despite_clean_ratio():
    """An image-only page yields a title-sized crumb of text: high ratio, no
    words. Ratio alone would wrongly accept it."""
    usable, ratio, words = pdfread.looks_like_text("Order Detail Report by Account")
    assert not usable
    assert ratio > pdfread.MIN_LETTER_RATIO   # the ratio test alone passes
    assert words < pdfread.MIN_WORDS          # the word count is what saves us


def test_ratio_and_word_count_are_both_required():
    many_symbols = "§§§ " * 200
    assert not pdfread.looks_like_text(many_symbols)[0]


def test_image_token_estimate_clamps_the_long_edge():
    """The benchmark's headline ratio depends on modelling the API's downscale;
    an A4 page at 200 dpi is 1654x2339 before clamping, not after."""
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location(
        "token_economics",
        pathlib.Path(__file__).resolve().parents[1] / "bench" / "token_economics.py")
    te = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(te)

    tokens, (w, h) = te.image_tokens(1654, 2339)
    assert max(w, h) == te.MAX_EDGE
    assert 2000 < tokens < 2600

    small_tokens, dims = te.image_tokens(800, 600)
    assert dims == (800, 600)          # already small enough, not upscaled
    assert small_tokens == round(800 * 600 / te.PIXELS_PER_TOKEN)
