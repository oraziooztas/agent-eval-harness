import unittest

from dedup import dedup_rows


class TestDedupPublic(unittest.TestCase):
    def test_no_duplicates_unchanged(self):
        rows = [{"id": "a", "v": 1}, {"id": "b", "v": 2}]
        self.assertEqual(dedup_rows(rows, "id"), rows)

    def test_identical_duplicate_removed(self):
        rows = [{"id": "a", "v": 1}, {"id": "b", "v": 2}, {"id": "a", "v": 1}]
        self.assertEqual(dedup_rows(rows, "id"), [{"id": "a", "v": 1}, {"id": "b", "v": 2}])


if __name__ == "__main__":
    unittest.main()
