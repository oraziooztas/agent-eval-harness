"""Slug URL-safe da testo libero. Contratto completo in PROMPT.md / task.json."""


def slugify(text):
    return text.strip().lower().replace(" ", "-")
