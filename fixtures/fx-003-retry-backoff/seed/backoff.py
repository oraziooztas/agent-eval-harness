"""Ritardi di retry con backoff esponenziale."""


def backoff_delays(attempts, base=1.0, cap=30.0):
    """Ritardi in secondi per `attempts` tentativi: base*2^i, mai oltre cap."""
    delays = []
    for i in range(attempts):
        delays.append(base * (2 ** i))
    return delays
