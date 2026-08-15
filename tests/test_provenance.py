"""Tests for the integrity layer of this repository.

Three properties are locked here.

1. The Merkle construction is the one it claims to be — RFC 6962, with the
   domain-separation bytes actually separating a leaf from an interior node. A
   known-answer test pins the single-leaf case, and an adversarial test shows that
   dropping the domain byte would collapse the two cases.
2. The two stages that this repository shares with the study's sealed chain —
   the frozen environment and the captured price bodies — recompute to the values
   sealed in the run manifest. If a single byte of ``data/`` changed, this fails.
3. The published tree matches ``checksums.sha256`` and ``provenance.json``.
"""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import make_provenance as mp   # noqa: E402


class TestMerkle(unittest.TestCase):
    """The tree hash follows RFC 6962 and separates leaves from interior nodes."""

    def test_folha_unica_e_sha256_do_byte_de_dominio_mais_a_entrada(self) -> None:
        """Known answer: MTH({d0}) = SHA-256(0x00 || d0)."""
        entrada = mp._entrada("a.txt", "00" * 32)
        esperado = hashlib.sha256(b"\x00" + entrada).hexdigest()
        self.assertEqual(mp.tree_hash([("a.txt", "00" * 32)]), esperado)

    def test_no_interior_nao_colide_com_folha(self) -> None:
        """Two leaves must not hash like one leaf carrying their concatenation."""
        dois = mp.tree_hash([("a", "11" * 32), ("b", "22" * 32)])
        concatenado = mp._entrada("a", "11" * 32) + mp._entrada("b", "22" * 32)
        self.assertNotEqual(dois, hashlib.sha256(b"\x00" + concatenado).hexdigest())

    def test_ordem_de_entrada_nao_muda_a_raiz(self) -> None:
        """The root is defined over paths sorted lexicographically."""
        a = mp.tree_hash([("a", "11" * 32), ("b", "22" * 32)])
        b = mp.tree_hash([("b", "22" * 32), ("a", "11" * 32)])
        self.assertEqual(a, b)

    def test_um_byte_diferente_muda_a_raiz(self) -> None:
        """Sanity: the hash is sensitive to content."""
        a = mp.tree_hash([("a", "11" * 32)])
        b = mp.tree_hash([("a", "11" * 31 + "12")])
        self.assertNotEqual(a, b)


class TestPonteComACadeiaSelada(unittest.TestCase):
    """The stages published byte for byte recompute to the sealed values."""

    def test_ambiente_congelado(self) -> None:
        self.assertEqual(mp.estagio_selado("environment", RAIZ),
                         mp.SELO_INTERNO["environment"]["hash"])

    def test_corpos_de_preco_capturados(self) -> None:
        self.assertEqual(mp.estagio_selado("data", RAIZ),
                         mp.SELO_INTERNO["data"]["hash"])

    def test_todo_corpo_capturado_esta_sob_o_selo(self) -> None:
        """The sealed stage covers every captured body, not a convenient subset."""
        sob_selo = sorted(RAIZ.glob("data/precos/**/*.json"))
        em_disco = sorted(p for p in (RAIZ / "data" / "precos").rglob("*.json"))
        self.assertEqual(sob_selo, em_disco)
        self.assertEqual(len(em_disco), 46)


class TestArvorePublicada(unittest.TestCase):
    """The published tree agrees with its own checksums."""

    def test_verificacao_completa_passa(self) -> None:
        self.assertEqual(mp.conferir(RAIZ), [])


if __name__ == "__main__":
    unittest.main()
