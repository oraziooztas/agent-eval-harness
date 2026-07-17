import unittest

from backoff import backoff_delays


class TestBackoffHidden(unittest.TestCase):
    def test_cap_applicato(self):
        self.assertEqual(
            backoff_delays(6, base=1.0, cap=10.0), [1.0, 2.0, 4.0, 8.0, 10.0, 10.0]
        )

    def test_cap_sotto_base(self):
        self.assertEqual(backoff_delays(3, base=5.0, cap=2.0), [2.0, 2.0, 2.0])

    def test_molti_tentativi_niente_overflow(self):
        delays = backoff_delays(60, base=1.0, cap=30.0)
        self.assertEqual(len(delays), 60)
        self.assertTrue(all(d <= 30.0 for d in delays))

    def test_attempts_negativo(self):
        with self.assertRaises(ValueError):
            backoff_delays(-1)

    def test_base_non_positiva(self):
        with self.assertRaises(ValueError):
            backoff_delays(3, base=0)

    def test_cap_non_positivo(self):
        with self.assertRaises(ValueError):
            backoff_delays(3, cap=-1.0)
