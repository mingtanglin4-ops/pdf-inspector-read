# pdf-inspector-read

[![tests](https://github.com/mingtanglin4-ops/pdf-inspector-read/actions/workflows/ci.yml/badge.svg)](https://github.com/mingtanglin4-ops/pdf-inspector-read/actions/workflows/ci.yml)

An [Agent Skill](https://code.claude.com/docs/en/skills) that makes an AI agent read PDFs
the cheap way when it can, and the reliable way when it must — by classifying the text
layer *before* committing to a strategy.

## Why this exists

Reading a PDF fails in two opposite directions.

Rasterizing every page and reading the images is always safe, but an image costs a flat
~2,300 tokens per page whatever that page holds. Extracting text is cheaper — how much
cheaper depends entirely on the document — but a PDF whose fonts carry no `/ToUnicode`
map returns confident-looking mojibake, and a scanned page returns nothing at all,
failures easily mistaken for "the document is empty".

[`pdf-inspector`](https://github.com/firecrawl/pdf-inspector) answers *"is this text layer
trustworthy?"* in 1–50 ms. This skill turns that answer into a routing decision, plus the
things that turned out to matter once the routing was actually tested.

## Related: what parsers do without telling you

[`docs/silent-behaviours.md`](docs/silent-behaviours.md) measures three things
PDF parsers do silently — escalating to OCR (9x slower, same return type),
dropping rotated content with no missing-content signal, and passing through
text no reader can see. That last one matters if a model reads your extracted
text: white-on-white and render-mode-3 strings carrying
`ignore all previous instructions` reach four of five parsers' output unmarked.
[`docs/detect_hidden.py`](docs/detect_hidden.py) catches them by reading the
drawing instructions, and exits non-zero so it can gate a pipeline.

## What the routing is worth, measured

`bench/token_economics.py` builds documents at a chosen text density, extracts them, renders
them, and counts both. No agent in the loop — this is a property of the two representations,
so it is measured directly rather than inferred:

```
40-page document, images rendered at 200 dpi

 density (chars/page) |  text tok |  image tok |  ratio
-------------------------------------------------------
    600 slide / cover |     6,389 |     92,640 |  14.5x
   1600 sparse report |    16,205 |     92,640 |   5.7x
   3200 journal page  |    32,890 |     92,640 |   2.8x
   5000 dense two-column |  49,576 |     92,640 |   1.9x
```

Reproduce with `python3 bench/token_economics.py --pages 40 --sweep`.

Two honest readings of that table. The saving is real but **not** the order of magnitude
this README used to claim: for a dense technical paper it is under 2x. And the saving is
largest for sparse pages — which are also the pages most likely to be worth looking at,
because what makes them sparse is usually a figure or a layout.

What actually justifies always classifying first is the other column: detection costs
**~5 ms and zero tokens**. The downside is bounded at nothing, and the upside is not
mainly the tokens — it is not quoting mojibake to someone as if it were their document.

## What's in the box

```
SKILL.md                    the routing policy and known limits
scripts/pdfread.py          classify → route → emit Markdown or a verdict
scripts/render_pages.py     rasterize for a visual read, and refuse to return a blank page
scripts/fetch_fixtures.sh   pull the eval fixtures from upstream
tests/                      pytest suite (44 tests, no network, no fixture downloads)
bench/token_economics.py    measures what the routing decision is actually worth
evals/evals.json            three agent-level eval prompts
```

```bash
python3 scripts/pdfread.py document.pdf              # verdict, then Markdown
python3 scripts/pdfread.py document.pdf --detect-only --json
python3 scripts/pdfread.py document.pdf --pages 3,7-9 --per-page
python3 scripts/render_pages.py document.pdf --pages 3 --dpi 200
```

`pdfread.py` prints a verdict block, then routes:

| route | meaning |
|---|---|
| `TEXT` | the Markdown that follows is the document |
| `RECOVERED` | pdf-inspector could not decode the font, but poppler could — text follows |
| `MIXED` | Markdown covers the sound pages; the listed pages still need eyes |
| `VISUAL` | nothing usable; render the listed pages and read the images |

## Three things found by testing, not by reading docs

**A broken text layer is often recoverable for free.** On a Japanese municipal PDF whose
font carries no `/ToUnicode` map, pdf-inspector returns 824 bytes of mojibake — and
`pdftotext -layout` returns the full 5,208-byte document, because poppler reconstructs
Unicode from the font's embedded CMap. `pdfread.py` now tries that automatically before
declaring a page unreadable, scoring the result with a letter-ratio/word-count heuristic
that cleanly separates the three cases (mojibake 0.67, real Japanese 0.98, empty scan
0.85 but only 5 words). Be aware that `MIN_LETTER_RATIO = 0.85` and `MIN_WORDS = 40`
were tuned by hand on a handful of documents, not fitted on a corpus; they are
module-level constants precisely so you can raise or lower them for yours. Very
short documents are the obvious failure case — 40 words is a low bar for a report
and an impossible one for a cover page.

**The renderer is a hidden failure mode.** poppler's `pdftoppm` needs the Adobe-Japan1
language pack to draw CJK. Without it, it emits a page containing the table rules and no
glyphs — indistinguishable from a genuinely blank form, and a completely plausible wrong
answer. `render_pages.py` uses pypdfium2 and prints an ink fraction per page, flagging a
near-blank render so the failure is visible instead of silent.

**Embedding is not the problem; the Unicode map is.** The font in that PDF is fully
embedded and subsetted (`emb=yes sub=yes uni=no`). "Non-embedded fonts break extraction"
is a plausible and wrong diagnosis — SKILL.md says so explicitly, because an agent that
believes it will mis-explain the failure to the user.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

44 tests, about a second, no network and no downloaded fixtures: the sample PDFs
are generated by reportlab at test time, including one whose CJK font carries no
`/ToUnicode` map — the exact failure this skill exists to catch. The routing
decision, the mojibake heuristic and the poppler fallback are pure or
dependency-injected functions, so they are tested without touching a PDF at all.

CI runs the suite on Linux, macOS and Windows. **poppler is deliberately
installed only on the Linux runner**, so every build proves the skill degrades
honestly on the two platforms where `pdftotext` is normally absent, rather than
reporting "recovery failed" when the truth is "recovery was never attempted".

The Windows job has already paid for itself: the first green-on-Linux build
failed there with `PermissionError [WinError 32]`, because the renderer never
closed its `PdfDocument` and Windows will not delete a file that still has an
open handle. Linux and macOS unlink open files happily, so three green runs said
nothing about it. `test_source_pdf_can_be_deleted_after_rendering` now guards
that — an assertion that is free on Unix and load-bearing on Windows.

## Install

```bash
git clone https://github.com/mingtanglin4-ops/pdf-inspector-read.git
```

Then place the folder where your agent looks for skills (for Claude Code, `.claude/skills/`
in a project, or `~/.claude/skills/` for all projects). The scripts are plain Python and
work standalone too — `pdfread.py` installs `pdf-inspector` on first run if it is missing.

Requires Python 3.9+ (tested on 3.9–3.13). `pypdfium2` is installed on demand by
`render_pages.py`; `pdftotext` (poppler-utils) is optional, and enables the
recovery path described above — on Windows and macOS it is not present by
default, and the tool says so explicitly rather than pretending recovery failed.

## Running the evals

```bash
bash scripts/fetch_fixtures.sh      # fixtures are not vendored, see below
```

Then run the three prompts in `evals/evals.json` against an agent with and without the
skill and compare. The fixture PDFs are third-party documents from the upstream test
corpus (a car price list, a municipal noise report); their own copyright is separate from
pdf-inspector's MIT license, so this repository fetches them rather than redistributing
them.

## Credits

This skill wraps [firecrawl/pdf-inspector](https://github.com/firecrawl/pdf-inspector)
(MIT License, © 2026 Firecrawl), a Rust library for PDF classification and text
extraction. It is installed as a dependency (`pip install pdf-inspector`); no upstream
code is vendored here.

The routing policy, the bundled scripts and this documentation are original work.

## License

MIT — see [LICENSE](LICENSE).
