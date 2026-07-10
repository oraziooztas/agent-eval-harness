import unittest

from slugify import slugify


class TestSlugifyHidden(unittest.TestCase):
    def test_accents_transliterated(self):
        self.assertEqual(slugify("Città di Torino"), "citta-di-torino")

    def test_multiple_spaces_collapse(self):
        self.assertEqual(slugify("a  b   c"), "a-b-c")

    def test_punctuation_becomes_single_dash(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")

    def test_no_leading_trailing_dashes(self):
        self.assertEqual(slugify("--ciao--"), "ciao")

    def test_empty_string(self):
        self.assertEqual(slugify(""), "")


if __name__ == "__main__":
    unittest.main()
