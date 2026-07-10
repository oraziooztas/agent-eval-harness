"""Dedup di righe (list[dict]) sulla colonna `key`.

Contratto: prima occorrenza vince, ordine preservato,
confronto case-insensitive per chiavi stringa (str.casefold).
"""


def dedup_rows(rows, key):
    seen = {}
    for row in rows:
        seen[row[key]] = row
    return list(seen.values())
