import unittest

from slugify import slugify


class TestSlugifyPublic(unittest.TestCase):
    def test_two_words(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_already_clean(self):
        self.assertEqual(slugify("ciao"), "ciao")

    def test_padded(self):
        self.assertEqual(slugify("  Ciao Mondo  "), "ciao-mondo")


if __name__ == "__main__":
    unittest.main()
