"""Build the behaviour matrix.

One cell = (parser, behaviour, document). Each cell records three things:
  occurred   - did the behaviour happen
  signalled  - did the parser tell the caller, and through which channel
  cost       - wall time against the matched clean twin

A behaviour class only earns a place in the matrix if it SPLITS the parsers.
Classes where every parser behaves alike carry no information and are dropped
by `discriminability()`; that gate is the whole reason this is a matrix and not
a list of anecdotes.
"""
from __future__ import annotations
import json, platform, sys, time
from dataclasses import asdict
from pathlib import Path

from . import parsers  # module, not names: the registry must stay swappable
                       # (subset runs, injected fakes in tests, week-3 additions)
from .fixtures import PAYLOAD, VISIBLE

SCHEMA = "ingest-audit/1"


def leak_cells(control_dir: Path) -> list[dict]:
    cells = []
    for payload_pdf in sorted(control_dir.glob("*.payload.pdf")):
        technique = payload_pdf.name.split(".")[0]
        clean_pdf = payload_pdf.with_name(f"{technique}.clean.pdf")
        pay = {r.parser: r for r in parsers.parse_all(payload_pdf)}
        cln = {r.parser: r for r in parsers.parse_all(clean_pdf)}
        for name in parsers.REGISTRY:
            p, c = pay[name], cln[name]
            # A message that also appears on the clean twin is a CONFIGURATION
            # BANNER, not a behaviour signal: it reports what the library has
            # installed, not what it did to this document. Only messages unique
            # to the payload run count as "it told the caller".
            banner_signals = [s for s in p.signals if s in set(c.signals)]
            behaviour_signals = [s for s in p.signals if s not in set(c.signals)]
            occurred = PAYLOAD.split(".")[0] in p.text
            cells.append({
                "parser": name,
                "parser_version": p.version,
                "behaviour": f"hidden_text.{technique}",
                "doc_id": f"control/{technique}",
                "doc_kind": "control",
                "occurred": occurred,
                "occurred_evidence": "payload span present in extracted text"
                                     if occurred else "payload span absent",
                "signalled": bool(behaviour_signals),
                "signal_channels": sorted({s.split(":")[0] for s in behaviour_signals}),
                "signal_excerpt": (behaviour_signals[0][:160] if behaviour_signals else None),
                "config_banner": sorted({s.split(":")[0] for s in banner_signals}) or None,
                "false_positive": PAYLOAD.split(".")[0] in c.text,
                "control_text_intact": VISIBLE.split(".")[0] in p.text,
                "cost": {"wall_s": round(p.wall_s, 4),
                         "wall_s_clean": round(c.wall_s, 4),
                         "ratio": round(p.wall_s / c.wall_s, 2) if c.wall_s else None},
                "error": p.error,
            })
    return cells


def discriminability(cells: list[dict]) -> dict[str, dict]:
    """Per behaviour: does it split the parsers? Non-splitting classes are noise.

    Cells that errored are EXCLUDED, never counted as occurred=False. A parser
    that is not installed (poppler on Windows, say) would otherwise read as
    "did not leak", which is the worst kind of false negative: a missing tool
    silently becomes a safety result.
    """
    out = {}
    for b in sorted({c["behaviour"] for c in cells}):
        sub = [c for c in cells if c["behaviour"] == b]
        ok = [c for c in sub if not c["error"]]
        bad = [c for c in sub if c["error"]]
        hit = sum(c["occurred"] for c in ok)
        n = len(ok)
        out[b] = {
            "n_parsers": n, "n_occurred": hit,
            "n_signalled": sum(c["signalled"] for c in ok),
            "n_false_positive": sum(c["false_positive"] for c in ok),
            "n_error": len(bad),
            "errored_parsers": sorted(c["parser"] for c in bad),
            "discriminative": 0 < hit < n,
            "verdict": ("keep" if 0 < hit < n else "DROP: does not split parsers")
                       + (f"  [{len(bad)} parser(s) unavailable, excluded]" if bad else ""),
        }
    return out


def build(control_dir: Path) -> dict:
    cells = leak_cells(control_dir)
    return {
        "schema": SCHEMA,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "parsers": {n: v for n, (v, _) in parsers.REGISTRY.items()},
        },
        "behaviours": discriminability(cells),
        "cells": cells,
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    m = build(root / "corpus" / "control")
    (root.parent / "results").mkdir(exist_ok=True)
    out = root.parent / "results" / "matrix.json"
    out.write_text(json.dumps(m, indent=2))

    print(f"\n{'behaviour':28} {'occurred':>10} {'signalled':>10} {'FP':>4} {'err':>4}  verdict")
    for b, st in m["behaviours"].items():
        print(f"{b:28} {st['n_occurred']:>4}/{st['n_parsers']:<5} "
              f"{st['n_signalled']:>4}/{st['n_parsers']:<5} {st['n_false_positive']:>4} "
              f"{st['n_error']:>4}  {st['verdict']}")
    if any(st["n_error"] for st in m["behaviours"].values()):
        print("\nNOTE: unavailable parsers were excluded, not counted as clean.")
    print(f"\nwrote {out}  ({len(m['cells'])} cells)")
