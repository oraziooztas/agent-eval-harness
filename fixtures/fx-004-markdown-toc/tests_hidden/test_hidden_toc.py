import unittest

from mdtoc import make_toc


class TestTocHidden(unittest.TestCase):
    def test_header_dentro_code_fence_ignorato(self):
        doc = "# Vero\n```\n# commento shell\n```\n## Dopo"
        self.assertEqual(
            make_toc(doc),
            [(1, "Vero", "vero"), (2, "Dopo", "dopo")],
        )

    def test_hash_senza_spazio_non_e_header(self):
        self.assertEqual(make_toc("#hashtag\n#!/bin/sh"), [])

    def test_hash_di_chiusura_rimossi(self):
        self.assertEqual(make_toc("## Titolo ##"), [(2, "Titolo", "titolo")])

    def test_slug_pulisce_punteggiatura(self):
        self.assertEqual(
            make_toc("# Setup & Config!"), [(1, "Setup & Config!", "setup--config")]
        )

    def test_duplicati_suffisso(self):
        doc = "# Note\n## Note\n### Note"
        self.assertEqual(
            make_toc(doc),
            [(1, "Note", "note"), (2, "Note", "note-2"), (3, "Note", "note-3")],
        )

    def test_oltre_sei_hash_non_header(self):
        self.assertEqual(make_toc("####### Troppi"), [])
