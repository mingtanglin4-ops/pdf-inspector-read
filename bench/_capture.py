"""File-descriptor level capture.

Python-level contextlib.redirect_stdout misses anything a native extension
writes straight to fd 1/2 (MuPDF and Tesseract both do). Signal accounting is
only honest if it captures at the fd layer.
"""
from __future__ import annotations
import os, contextlib, tempfile


@contextlib.contextmanager
def capture_fds():
    out = {"stdout": "", "stderr": ""}
    with tempfile.TemporaryFile(mode="w+b") as fo, tempfile.TemporaryFile(mode="w+b") as fe:
        so, se = os.dup(1), os.dup(2)
        os.dup2(fo.fileno(), 1); os.dup2(fe.fileno(), 2)
        try:
            yield out
        finally:
            os.fsync(1) if False else None
            os.dup2(so, 1); os.dup2(se, 2); os.close(so); os.close(se)
            for f, k in ((fo, "stdout"), (fe, "stderr")):
                f.seek(0); out[k] = f.read().decode("utf-8", "replace")
