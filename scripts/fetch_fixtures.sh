#!/usr/bin/env bash
# Fetch the eval fixtures from the upstream pdf-inspector test corpus.
#
# The fixture PDFs are NOT vendored in this repository: they are third-party
# documents (a car price list, a municipal noise report) whose own copyright is
# separate from pdf-inspector's MIT license. Pull them at test time instead.
set -euo pipefail
DEST="$(cd "$(dirname "$0")/.." && pwd)/evals/fixtures"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git clone --depth 1 https://github.com/firecrawl/pdf-inspector.git "$TMP/src"
SRC="$TMP/src/tests/fixtures"

mkdir -p "$DEST/batch" "$DEST/single"
cp "$SRC/shannon-entropy-p1-2.pdf"        "$DEST/batch/shannon_1948.pdf"
cp "$SRC/firecrawl_docs_tagged.pdf"       "$DEST/batch/docs_tagged.pdf"
cp "$SRC/scan_with_native_header_text.pdf" "$DEST/batch/scanned_form.pdf"
cp "$SRC/shinagawa_identity_h.pdf"        "$DEST/batch/shinagawa_notice.pdf"
cp "$SRC/nexo-price-en.pdf"               "$DEST/single/price_table.pdf"
cp "$SRC/shinagawa_identity_h.pdf"        "$DEST/single/shinagawa_notice.pdf"

echo "Fixtures written to $DEST"
