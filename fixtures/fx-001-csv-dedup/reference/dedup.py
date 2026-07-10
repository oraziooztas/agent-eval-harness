"""Reference solution: prima occorrenza vince, ordine preservato, casefold sulle stringhe."""


def dedup_rows(rows, key):
    seen = set()
    out = []
    for row in rows:
        value = row[key]
        norm = value.casefold() if isinstance(value, str) else value
        if norm in seen:
            continue
        seen.add(norm)
        out.append(row)
    return out
