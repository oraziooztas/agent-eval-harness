"""Ritardi di retry con backoff esponenziale."""


def backoff_delays(attempts, base=1.0, cap=30.0):
    """Ritardi in secondi per `attempts` tentativi: base*2^i, mai oltre cap."""
    if attempts < 0:
        raise ValueError("attempts deve essere >= 0")
    if base <= 0 or cap <= 0:
        raise ValueError("base e cap devono essere > 0")
    delays = []
    delay = float(base)
    for _ in range(attempts):
        delays.append(min(delay, float(cap)))
        if delay < cap:
            delay *= 2
    return delays
