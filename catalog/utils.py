import re


def normalize_mpn(mpn: str) -> str:
    """Uppercase, remove spaces, dashes, dots."""
    return re.sub(r'[\s\-\.]', '', mpn).upper()


def normalize_name(name: str) -> str:
    """Uppercase, collapse whitespace, strip punctuation except spaces."""
    name = re.sub(r'[^\w\s]', '', name)
    return re.sub(r'\s+', ' ', name).strip().upper()
