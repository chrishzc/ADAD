"""Canonical helpers for normalizing architecture source references."""


def normalize_markdown_source(value: str) -> str:
    """Remove one complete pair of surrounding Markdown backticks."""
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value
