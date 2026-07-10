import unittest

from dedup import dedup_rows


class TestDedupHidden(unittest.TestCase):
    def test_first_occurrence_wins(self):
        rows = [{"id": "a", "v": 1}, {"id": "a", "v": 99}]
        self.assertEqual(dedup_rows(rows, "id"), [{"id": "a", "v": 1}])

    def test_key_comparison_is_casefold(self):
        rows = [{"id": "Alpha", "v": 1}, {"id": "alpha", "v": 2}, {"id": "ALPHA", "v": 3}]
        self.assertEqual(dedup_rows(rows, "id"), [{"id": "Alpha", "v": 1}])

    def test_order_preserved_with_interleaved_duplicates(self):
        rows = [
            {"id": "x", "v": 1},
            {"id": "y", "v": 2},
            {"id": "x", "v": 3},
            {"id": "z", "v": 4},
            {"id": "y", "v": 5},
        ]
        self.assertEqual(
            dedup_rows(rows, "id"),
            [{"id": "x", "v": 1}, {"id": "y", "v": 2}, {"id": "z", "v": 4}],
        )

    def test_empty_input(self):
        self.assertEqual(dedup_rows([], "id"), [])

    def test_non_string_keys_compared_by_value(self):
        rows = [{"n": 1, "v": "a"}, {"n": 2, "v": "b"}, {"n": 1, "v": "c"}]
        self.assertEqual(dedup_rows(rows, "n"), [{"n": 1, "v": "a"}, {"n": 2, "v": "b"}])


if __name__ == "__main__":
    unittest.main()
