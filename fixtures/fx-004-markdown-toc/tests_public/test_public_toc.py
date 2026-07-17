import unittest

from mdtoc import make_toc


class TestTocPublic(unittest.TestCase):
    def test_header_singolo(self):
        self.assertEqual(make_toc("# Introduzione"), [(1, "Introduzione", "introduzione")])

    def test_livelli_e_ordine(self):
        doc = "# Guida\n\ntesto\n\n## Setup rapido\n"
        self.assertEqual(
            make_toc(doc),
            [(1, "Guida", "guida"), (2, "Setup rapido", "setup-rapido")],
        )

    def test_documento_senza_header(self):
        self.assertEqual(make_toc("solo testo\nsu due righe"), [])
