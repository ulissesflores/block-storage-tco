"""Every number printed in ``README.md`` is an assertion here.

The rule of the house is that a published number is a test case: if the model, the
prices or the code change, this file fails and the README is what gets corrected — never
the other way round. The numbers below are typed from the README on purpose; they are
compared against the CSV files that ``run_all.py`` regenerates from the frozen price
bodies.

The headline claim needs its own test. Saying that block storage *decides* which cloud
is cheaper is stronger than saying it is the largest line, and it is only true if
removing that single item reverses the ranking — so that counterfactual is computed,
not asserted in prose.
"""

from __future__ import annotations

import csv
import re
import unittest
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TABELAS = RAIZ / "output" / "tabelas"


def por_item() -> dict[tuple[str, str, str], float]:
    """Read the 36-month cost of every (phase, cloud, cost item) triple.

    Returns
    -------
    dict
        Mapping from ``(phase, cloud, item)`` to US dollars over 36 months.
    """
    with (TABELAS / "tco-por-item.csv").open(encoding="utf-8") as f:
        return {(l["fase"], l["nuvem"], l["item_custo"]): float(l["usd_36m"])
                for l in csv.DictReader(f)}


def total_por_nuvem() -> dict[tuple[str, str], float]:
    """Sum the per-item costs into a 36-month total per (phase, cloud).

    Returns
    -------
    dict
        Mapping from ``(phase, cloud)`` to US dollars over 36 months.
    """
    soma: dict[tuple[str, str], float] = defaultdict(float)
    for (fase, nuvem, _), valor in por_item().items():
        soma[(fase, nuvem)] += valor
    return dict(soma)


class TestManchete(unittest.TestCase):
    """The three numbers in the Finding callout."""

    def test_totais_de_36_meses(self) -> None:
        total = total_por_nuvem()
        self.assertAlmostEqual(total[("1", "ibm")], 384802.19, places=2)
        self.assertAlmostEqual(total[("1", "aws")], 286970.04, places=2)
        self.assertAlmostEqual(total[("2", "ibm")], 429733.13, places=2)
        self.assertAlmostEqual(total[("2", "aws")], 349419.27, places=2)

    def test_diferencas_publicadas(self) -> None:
        total = total_por_nuvem()
        f1 = total[("1", "ibm")] - total[("1", "aws")]
        f2 = total[("2", "ibm")] - total[("2", "aws")]
        self.assertAlmostEqual(f1, 97832.16, places=2)
        self.assertAlmostEqual(f2, 80313.87, places=2)
        self.assertAlmostEqual(100 * f1 / total[("1", "aws")], 34.1, places=1)
        self.assertAlmostEqual(100 * f2 / total[("2", "aws")], 23.0, places=1)

    def test_o_bloco_e_maior_que_a_diferenca_total(self) -> None:
        itens, total = por_item(), total_por_nuvem()
        bloco = itens[("1", "ibm", "bloco")] - itens[("1", "aws", "bloco")]
        self.assertAlmostEqual(bloco, 110506.60, places=2)
        self.assertGreater(bloco, total[("1", "ibm")] - total[("1", "aws")])

    def test_computacao_corre_na_direcao_contraria(self) -> None:
        itens = por_item()
        vantagem = itens[("1", "aws", "compute")] - itens[("1", "ibm", "compute")]
        self.assertAlmostEqual(vantagem, 3348.07, places=2)


class TestOBlocoDecideOVencedor(unittest.TestCase):
    """The counterfactual behind the title: take block storage out and the ranking flips."""

    def test_sem_bloco_a_ibm_fica_mais_barata_nas_duas_fases(self) -> None:
        itens, total = por_item(), total_por_nuvem()
        for fase, esperado in (("1", 12674.44), ("2", 42324.92)):
            ibm = total[(fase, "ibm")] - itens[(fase, "ibm", "bloco")]
            aws = total[(fase, "aws")] - itens[(fase, "aws", "bloco")]
            self.assertLess(ibm, aws, f"fase {fase}: sem bloco a IBM deveria ficar menor")
            self.assertAlmostEqual(aws - ibm, esperado, places=2)

    def test_com_bloco_a_aws_vence_nas_duas_fases(self) -> None:
        total = total_por_nuvem()
        for fase in ("1", "2"):
            self.assertLess(total[(fase, "aws")], total[(fase, "ibm")])


class TestVereditoEstavelNaGrade(unittest.TestCase):
    """The claim that the ranking never changes across the pre-registered sweep."""

    def test_vinte_e_quatro_pontos_e_um_so_vencedor(self) -> None:
        with (TABELAS / "ponto-de-virada.csv").open(encoding="utf-8") as f:
            linhas = list(csv.DictReader(f))
        self.assertEqual(len(linhas), 14)
        self.assertEqual({l["vencedor"] for l in linhas}, {"aws"})

    def test_nenhuma_virada_dentro_da_grade(self) -> None:
        with (TABELAS / "virada-sintese.csv").open(encoding="utf-8") as f:
            for l in csv.DictReader(f):
                self.assertEqual(l["existe"], "False")


class TestPontoDeOperacao(unittest.TestCase):
    """The iso-SLA multiplier is derived from the queueing model, not chosen."""

    def test_menor_multiplicador_que_cabe_no_alvo(self) -> None:
        with (TABELAS / "filas-ponto-iso-sla.csv").open(encoding="utf-8") as f:
            linhas = [l for l in csv.DictReader(f)
                      if l["atende"] == "True" and float(l["cv_servico"]) == 1.2]
        menor = min(linhas, key=lambda l: float(l["multiplicador"]))
        self.assertAlmostEqual(float(menor["multiplicador"]), 1.50, places=2)
        self.assertAlmostEqual(float(menor["resposta_p95_ms"]), 166.26, places=2)
        self.assertLess(float(menor["resposta_p95_ms"]), float(menor["alvo_ms"]))


class TestOReadmeNaoDivergeDosCSV(unittest.TestCase):
    """Guard against the README drifting away from the numbers it quotes."""

    def test_todo_valor_da_tabela_de_itens_aparece_no_readme(self) -> None:
        readme = (RAIZ / "README.md").read_text(encoding="utf-8")
        itens = por_item()
        for chave in (("1", "ibm", "bloco"), ("1", "aws", "bloco"),
                      ("1", "ibm", "compute"), ("1", "aws", "compute"),
                      ("1", "ibm", "objeto"), ("1", "aws", "objeto"),
                      ("1", "ibm", "egress"), ("1", "aws", "egress")):
            impresso = f"{itens[chave]:,.2f}"
            self.assertIn(impresso, readme,
                          f"{chave} vale {impresso} e não aparece no README")

    def test_a_contagem_de_testes_do_badge_confere(self) -> None:
        readme = (RAIZ / "README.md").read_text(encoding="utf-8")
        badge = re.search(r"tests-(\d+)_passing", readme)
        self.assertIsNotNone(badge)
        total = sum(len(re.findall(r"^    def test", p.read_text(encoding="utf-8"), re.M))
                    for p in sorted((RAIZ / "tests").glob("test_*.py")))
        self.assertEqual(int(badge.group(1)), total,
                         "o badge do README não bate com a contagem real de testes")


if __name__ == "__main__":
    unittest.main()
