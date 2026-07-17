import unittest

from backoff import backoff_delays


class TestBackoffPublic(unittest.TestCase):
    def test_crescita_felice(self):
        self.assertEqual(backoff_delays(3), [1.0, 2.0, 4.0])

    def test_base_custom(self):
        self.assertEqual(backoff_delays(2, base=0.5), [0.5, 1.0])

    def test_zero_tentativi(self):
        self.assertEqual(backoff_delays(0), [])
