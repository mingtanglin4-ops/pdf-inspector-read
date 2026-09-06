"""Test fixtures.

The PDFs used by the integration tests are generated here at test time rather
than committed. Two reasons: the upstream corpus documents carry their own
third-party copyright, and a generated file lets a test state exactly which
property of the PDF it depends on.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

reportlab = pytest.importorskip("reportlab", reason="reportlab builds the sample PDFs")
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

PROSE = (
    "The fundamental problem of communication is that of reproducing at one point "
    "either exactly or approximately a message selected at another point. Frequently "
    "the messages have meaning, that is they refer to or are correlated according to "
    "some system with certain physical or conceptual entities. These semantic aspects "
    "of communication are irrelevant to the engineering problem. The significant "
    "aspect is that the actual message is one selected from a set of possible messages."
)


@pytest.fixture(scope="session")
def clean_pdf(tmp_path_factory):
    """A plain text-layer PDF: standard font, real prose, several pages."""
    path = tmp_path_factory.mktemp("pdfs") / "clean.pdf"
    c = canvas.Canvas(str(path))
    for page in range(2):
        c.setFont("Helvetica-Bold", 18)
        c.drawString(60, 780, f"Section {page + 1}: A Mathematical Theory")
        c.setFont("Helvetica", 11)
        y = 740
        for chunk in [PROSE[i:i + 90] for i in range(0, len(PROSE), 90)]:
            c.drawString(60, y, chunk)
            y -= 16
        c.showPage()
    c.save()
    return path


@pytest.fixture(scope="session")
def broken_cid_pdf(tmp_path_factory):
    """A PDF whose CJK font carries no usable /ToUnicode mapping.

    This is the failure this skill exists to catch: the document looks
    text-based and reports full confidence, but the extracted characters are
    meaningless.
    """
    path = tmp_path_factory.mktemp("pdfs") / "broken_cid.pdf"
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    c = canvas.Canvas(str(path))
    c.setFont("STSong-Light", 16)
    c.drawString(60, 760, "透明物体深度估计与分割")
    c.setFont("STSong-Light", 11)
    for i, line in enumerate([
        "摘要：本文提出一种边缘感知的融合网络，用于透明物体的深度补全。",
        "在两个公开数据集上，均方根误差分别下降百分之十二和百分之九。",
        "关键词：透明物体；深度估计；非模态分割；机械臂抓取",
    ]):
        c.drawString(60, 720 - i * 22, line)
    c.save()
    return path


@pytest.fixture(scope="session")
def blank_pdf(tmp_path_factory):
    """A page with no text at all — the image-only shape, without an image."""
    path = tmp_path_factory.mktemp("pdfs") / "blank.pdf"
    c = canvas.Canvas(str(path))
    c.rect(60, 600, 400, 150)          # rules only, no glyphs
    c.save()
    return path
