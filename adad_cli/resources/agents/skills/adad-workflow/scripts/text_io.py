# -*- coding: utf-8 -*-
import os
import tempfile

def read_utf8_text_strict(file_path: str) -> str:
    """
    ponytail: stdlib open() does strict UTF-8 naturally. We just reject BOM explicitly.
    """
    with open(file_path, "r", encoding="utf-8", errors="strict") as f:
        text = f.read()
    if text.startswith("\ufeff"):
        raise ValueError(f"Strict UTF-8 text boundary violated: {file_path} contains a BOM.")
    return text

def write_utf8_text_atomic(file_path: str, text: str) -> str:
    """
    ponytail: atomic file write with explicit utf-8, LF newline.
    """
    dirname, basename = os.path.split(os.path.abspath(file_path))
    os.makedirs(dirname, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=dirname, prefix=f".{basename}.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp_path, file_path)
    except Exception:
        os.remove(tmp_path)
        raise
    return file_path
