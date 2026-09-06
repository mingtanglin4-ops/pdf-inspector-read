"""Parser adapters under a single interface.

Every adapter returns the same triple so that cells are comparable:
  text      - what the caller would feed to the model
  wall_s    - cost
  signals   - EVERYTHING the parser surfaced to a normal caller during the call:
              warnings.warn, logging records at >=WARNING, anything written to
              stdout or stderr, and the exception if it raised. This is the operational
              definition of "did it tell you"; a parser that changes behaviour
              silently produces an empty list here.
"""
from __future__ import annotations
import contextlib, io, logging, subprocess, sys, time, warnings
from dataclasses import dataclass, field
from pathlib import Path
from ._capture import capture_fds


@dataclass
class ParseResult:
    parser: str
    version: str
    text: str
    wall_s: float
    signals: list[str] = field(default_factory=list)
    error: str | None = None


class _Capture(logging.Handler):
    def __init__(self): super().__init__(logging.WARNING); self.records = []
    def emit(self, r): self.records.append(f"log:{r.name}:{r.getMessage()[:200]}")


@contextlib.contextmanager
def _watch():
    """Collect every channel a library could use to tell the caller something."""
    box = {"signals": []}
    handler = _Capture()
    root = logging.getLogger(); root.addHandler(handler)
    prev_level = root.level; root.setLevel(logging.WARNING)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with capture_fds() as fds:
            yield box
    box["signals"] += [f"warn:{w.category.__name__}:{str(w.message)[:200]}" for w in caught]
    box["signals"] += handler.records
    for chan in ("stdout", "stderr"):
        if fds[chan].strip():
            box["signals"].append(f"{chan}:{fds[chan].strip()[:200]}")
    root.removeHandler(handler); root.setLevel(prev_level)


def _run(name, version, fn, path: Path) -> ParseResult:
    t0 = time.perf_counter(); text, error = "", None
    with _watch() as box:
        try:
            text = fn(path)
        except Exception as e:                       # an exception IS a signal
            error = f"{type(e).__name__}: {e}"[:300]
    wall = time.perf_counter() - t0
    sig = list(box["signals"])
    if error:
        sig.append(f"raise:{error}")
    return ParseResult(name, version, text, wall, sig, error)


# ---- adapters -------------------------------------------------------------
def _pdftotext(p):
    return subprocess.run(["pdftotext", "-q", str(p), "-"],
                          capture_output=True, text=True, check=True).stdout

def _pdftotext_layout(p):
    return subprocess.run(["pdftotext", "-layout", "-q", str(p), "-"],
                          capture_output=True, text=True, check=True).stdout

def _pdfplumber(p):
    import pdfplumber
    with pdfplumber.open(p) as d:
        return "\n".join((pg.extract_text() or "") for pg in d.pages)

def _pypdf(p):
    import pypdf
    return "\n".join(pg.extract_text() or "" for pg in pypdf.PdfReader(str(p)).pages)

def _pymupdf(p):
    import pymupdf
    with pymupdf.open(p) as d:
        return "\n".join(pg.get_text() for pg in d)

def _pymupdf4llm(p):
    import pymupdf4llm
    return pymupdf4llm.to_markdown(str(p), show_progress=False)

def _markitdown(p):
    from markitdown import MarkItDown
    return MarkItDown().convert(str(p)).text_content


def _v(mod, attr="__version__", default="?"):
    try:
        m = __import__(mod); return getattr(m, attr, default)
    except Exception:
        return "unavailable"

def _poppler_version():
    try:
        out = subprocess.run(["pdftotext", "-v"], capture_output=True, text=True).stderr
        return out.splitlines()[0].split()[-1]
    except Exception:
        return "?"


REGISTRY = {
    "pdftotext":        (_poppler_version(),                _pdftotext),
    "pdftotext-layout": (_poppler_version(),                _pdftotext_layout),
    "pdfplumber":       (_v("pdfplumber"),                  _pdfplumber),
    "pypdf":            (_v("pypdf"),                       _pypdf),
    "pymupdf":          (_v("pymupdf"),                     _pymupdf),
    "pymupdf4llm":      (_v("pymupdf4llm"),                 _pymupdf4llm),
    "markitdown":       (_v("markitdown"),                  _markitdown),
}


def parse_all(path: Path) -> list[ParseResult]:
    return [_run(n, ver, fn, path) for n, (ver, fn) in REGISTRY.items()]
