"""Indice (TOC) da documenti markdown."""


def make_toc(markdown):
    """Lista di (livello, titolo, slug) dagli header ATX del documento."""
    toc = []
    for line in markdown.splitlines():
        if line.startswith("#"):
            stripped = line.lstrip("#")
            level = len(line) - len(stripped)
            title = stripped.strip()
            toc.append((level, title, title.lower().replace(" ", "-")))
    return toc
