"""Canonical helpers for normalizing architecture source references."""


def normalize_markdown_source(value: str) -> str:
    """Remove one or more complete pairs of surrounding Markdown backticks or code fences."""
    if not isinstance(value, str):
        return value

    val = value.strip()

    # Handle code fence (```...```)
    if val.startswith("```") and val.endswith("```") and len(val) >= 6:
        # Strip outer ```
        inner = val[3:-3].strip()
        # If inner starts with a language identifier (e.g., python\n)
        if "\n" in inner:
            first_line, rest = inner.split("\n", 1)
            # If the first line is alphanumeric (language name)
            if first_line.strip().isalnum():
                inner = rest.strip()
        return normalize_markdown_source(inner)

    # Handle single or multiple backticks (e.g., `file.py` or ``file.py``)
    if val.startswith("`") and val.endswith("`") and len(val) >= 2:
        return normalize_markdown_source(val[1:-1])

    return val
