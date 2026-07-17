"""Indice (TOC) da documenti markdown."""

import re

_HEADER = re.compile(r"^(#{1,6}) (.*)$")


def _slugify(title):
    return re.sub(r"[^a-z0-9-]", "", title.lower().replace(" ", "-"))


def make_toc(markdown):
    """Lista di (livello, titolo, slug) dagli header ATX del documento."""
    toc = []
    seen = {}
    in_fence = False
    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADER.match(line)
        if not match:
            continue
        hashes, rest = match.groups()
        title = re.sub(r"\s+#+\s*$", "", rest).strip()
        if not title:
            continue
        slug = _slugify(title)
        seen[slug] = seen.get(slug, 0) + 1
        if seen[slug] > 1:
            slug = f"{slug}-{seen[slug]}"
        toc.append((len(hashes), title, slug))
    return toc
