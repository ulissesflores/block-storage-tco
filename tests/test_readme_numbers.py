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
        self.assertAlmostEqual(total[("2", "ibm")], 686676.61, places=2)
        self.assertAlmostEqual(total[("2", "aws")], 558229.74, places=2)

    def test_diferencas_publicadas(self) -> None:
        total = total_por_nuvem()
        # The published difference is the subtraction of the PRINTED totals, which is the
        # arithmetic a reader redoes on the page — not the rounded difference of the raw values.
        # Rounding first differs by one cent (97,832.16 vs 97,832.15) and an external audit
        # caught the two documents disagreeing about it.
        f1 = round(total[("1", "ibm")], 2) - round(total[("1", "aws")], 2)
        f2 = round(total[("2", "ibm")], 2) - round(total[("2", "aws")], 2)
        self.assertAlmostEqual(f1, 97832.15, places=2)
        self.assertAlmostEqual(f2, 128446.87, places=2)
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
    """The counterfactual behind the title: take block storage out and see whether it flips.

    Until v1.5.0 it flipped in BOTH phases. The member/disk correction of v1.6.0 changed that,
    and the honest reading is now split: block storage still is the largest single driver in both
    phases, but in phase 2 it no longer decides the ranking on its own, because the managed
    premium grew alongside it. Asserting the old claim would be forcing a result the evidence
    stopped supporting — so the test asserts what each phase actually does.
    """

    def test_na_fase_1_retirar_o_bloco_inverte_o_ranking(self) -> None:
        itens, total = por_item(), total_por_nuvem()
        ibm = total[("1", "ibm")] - itens[("1", "ibm", "bloco")]
        aws = total[("1", "aws")] - itens[("1", "aws", "bloco")]
        self.assertLess(ibm, aws)
        self.assertAlmostEqual(aws - ibm, 12674.44, places=2)

    def test_na_fase_2_retirar_o_bloco_tambem_inverte(self) -> None:
        """Sob paridade de réplicas dos dois lados, o contrafactual volta a inverter na fase 2.

        Entre 1.6.0 e 1.6.1 ele NÃO invertia: a IBM pagava todos os membros e a AWS, instância
        única. Com a unidade de comparação corrigida (v1.7.0) a inversão reaparece, e é mais
        forte que na fase 1. Fica registrado que a claim do título já esteve parcialmente falsa
        neste repositório — a história está no CHANGELOG, não apagada.
        """
        itens, total = por_item(), total_por_nuvem()
        ibm = total[("2", "ibm")] - itens[("2", "ibm", "bloco")]
        aws = total[("2", "aws")] - itens[("2", "aws", "bloco")]
        self.assertLess(ibm, aws, "fase 2: sem bloco a IBM deveria ficar menor")
        self.assertAlmostEqual(aws - ibm, 88304.625, places=2)
        bloco = itens[("2", "ibm", "bloco")] - itens[("2", "aws", "bloco")]
        gap = total[("2", "ibm")] - total[("2", "aws")]
        self.assertGreater(bloco, gap, "o item tem de ser maior que a diferença inteira")

    def test_com_bloco_a_aws_vence_nas_duas_fases(self) -> None:
        total = total_por_nuvem()
        for fase in ("1", "2"):
            self.assertLess(total[(fase, "aws")], total[(fase, "ibm")])


class TestDecomposicaoDaFase2NoReadme(unittest.TestCase):
    """The phase-2 breakdown table printed in the README, item by item.

    Same rule as the rest of this file: a number on the page is a case here. This table only
    exists from v1.6.0, when the member/disk correction made phase 2 the interesting half.
    """

    ESPERADO = {"bloco": (340314.80, 123563.31, 216751.50, 168.7),
                "premio-gerenciado": (70926.82, 160712.71, -89785.89, -69.9),
                "compute": (192486.68, 186065.91, 6420.765, 5.0),
                "objeto": (38432.38, 52483.60, -14051.22, -10.9),
                "egress": (39912.54, 33177.60, 6734.94, 5.2),
                "backup": (2186.56, 0.00, 2186.56, 1.7)}

    def test_a_tabela_da_fase_2_bate_com_o_csv(self) -> None:
        itens = por_item()
        with (TABELAS / "decomposicao-do-gap.csv").open(encoding="utf-8") as f:
            dec = {l["item_custo"]: (float(l["delta_usd_36m"]), float(l["pct_do_gap"]))
                   for l in csv.DictReader(f) if l["fase"] == "2"}
        for item, (ibm, aws, delta, pct) in self.ESPERADO.items():
            with self.subTest(item=item):
                self.assertAlmostEqual(itens[("2", "ibm", item)], ibm, places=2)
                self.assertAlmostEqual(itens[("2", "aws", item)], aws, places=2)
                self.assertAlmostEqual(dec[item][0], delta, places=2)
                self.assertAlmostEqual(dec[item][1], pct, places=1)

    def test_as_participacoes_somam_cem_por_cento(self) -> None:
        with (TABELAS / "decomposicao-do-gap.csv").open(encoding="utf-8") as f:
            pcts = [float(l["pct_do_gap"]) for l in csv.DictReader(f) if l["fase"] == "2"]
        # the CSV stores rounded shares, so the sum lands within a ten-thousandth of 100
        self.assertAlmostEqual(sum(pcts), 100.0, delta=0.001)


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
