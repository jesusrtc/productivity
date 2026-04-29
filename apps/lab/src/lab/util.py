from __future__ import annotations


def split_csv(value: str | None) -> list[str]:
    """Parse a comma-separated string into a list of stripped non-empty values.

    Examples:
        split_csv("a,b,c")        -> ["a", "b", "c"]
        split_csv("  a , , b  ")  -> ["a", "b"]
        split_csv(None)           -> []
        split_csv("")             -> []
    """
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]
