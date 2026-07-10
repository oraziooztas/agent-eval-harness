"""Reference solution: traslittera, collassa non-alfanumerici, trim dei trattini."""

import re
import unicodedata


def slugify(text):
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text)
    return text.strip("-").lower()
