"""Conservative versioned identifiers shared by PDF and official API projections."""

import re
import unicodedata

_CNJ_FULL = re.compile(r"\d{7}[-.]?\d{2}[.]?\d{4}[.]?\d[.]?\d{2}[.]?\d{4}")


def normalize_process_number(value: str | None) -> str | None:
    """Accept only a complete CNJ-shaped identifier; never guess missing digits."""
    if value is None:
        return None
    candidate = value.strip()
    if not _CNJ_FULL.fullmatch(candidate):
        return None
    return re.sub(r"\D", "", candidate)


def normalize_folder(value: str | None) -> str | None:
    """Keep internal characters untouched: only NFC and edge whitespace are allowed."""
    if value is None:
        return None
    candidate = unicodedata.normalize("NFC", value.strip())
    return candidate or None
