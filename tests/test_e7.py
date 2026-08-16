#!/usr/bin/env python3
"""Travas da E7 — modelo de fila, tabelas do corpo e figuras.

O que estes testes existem para impedir, em ordem de gravidade:

1. **Que o ponto de operação iso-SLA volte a ser escolhido a olho.** Ele é derivado, e o teste
   trava tanto o valor derivado quanto o fato de que o multiplicador imediatamente anterior
   NÃO cumpre o alvo — é justamente o que alguém escolheria por parecer razoável.
2. **Que o custo passe a depender da fila.** Se `tco.py` algum dia importar `filas.py`, a
   afirmação de invariância publicada no corpo vira falsa. O teste percorre o grafo de
   importação e falha.
3. **Que o número do texto divirja do número da tabela.** As tabelas do corpo são conferidas
   contra as mesmas constantes publicadas que `TestNumerosPublicados` já trava.
"""

from __future__ import annotations

import ast
import csv
import json
import math
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

try:                          # matplotlib só é preciso para redesenhar figuras
    import figuras            # noqa: E402
except ModuleNotFoundError:   # Track 1 roda sem dependência de terceiro
    figuras = None            # noqa: E402
import filas            # noqa: E402

# os quatro totais de 36 meses que o corpo publica; a mesma lista está em TestNumerosPublicados
TOTAIS_PUBLICADOS = {("C1", 1, "ibm"): 384802.1927, ("C2", 1, "aws"): 286970.0366,
                     ("C3", 2, "ibm"): 686676.6055, ("C4", 2, "aws"): 558229.7352}


def ler(nome: str) -> list[dict]:
    with (RAIZ / "output" / "tabelas" / nome).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class TestInvarianciaDoCusto(unittest.TestCase):
    """O corpo afirma que o ponto de virada não depende de utilização, variabilidade nem taxa de
    chegada. Isso só é verdade se o caminho de cômputo do custo não alcançar o módulo de fila."""

    def _alcancados(self, inicio: str) -> set[str]:
        locais = {p.stem for p in (RAIZ / "src").glob("*.py")}
        vistos, fila = set(), [inicio]
        while fila:
            mod = fila.pop()
            if mod in vistos:
                continue
            vistos.add(mod)
            arvore = ast.parse((RAIZ / "src" / f"{mod}.py").read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if isinstance(no, ast.Import):
                    nomes = [a.name.split(".")[0] for a in no.names]
                elif isinstance(no, ast.ImportFrom):
                    nomes = [(no.module or "").split(".")[0]]
                else:
                    continue
                fila += [n for n in nomes if n in locais and n not in vistos]
        return vistos

    def test_tco_nao_alcanca_filas(self):
        for inicio in ("tco", "catalogo"):
            with self.subTest(modulo=inicio):
                self.assertNotIn("filas", self._alcancados(inicio),
                                 f"{inicio}.py alcança filas.py: a invariância publicada no "
                                 f"corpo deixaria de ser verdadeira")



class TestKingman(unittest.TestCase):
    """Vetores calculados à mão. Se a fórmula for trocada por outra parecida, isto acusa."""

    def setUp(self):
        self.cfg = filas.carregar(RAIZ)

    def test_kat_espera_no_ponto_selado(self):
        # rho=0,75; (Ca^2+Cs^2)/2 = (1 + 1,44)/2 = 1,22; E[S]=25 ms
        # Wq = 3 * 1,22 * 25 = 91,5 ms
        wq = filas.espera_kingman(0.75, 1.0, 1.44, 0.025)
        self.assertAlmostEqual(wq * 1000, 91.5, places=6)

    def test_kat_percentil(self):
        # P95 = (91,5 + 25) * ln(20) = 116,5 * 2,995732... = 349,00... ms
        p95 = filas.percentil_resposta(0.0915, 0.025, 0.95)
        self.assertAlmostEqual(p95 * 1000, 116.5 * math.log(20), places=6)
        self.assertAlmostEqual(p95 * 1000, 349.003, places=2)

    def test_forma_e_exata_em_mm1(self):
        """Com Ca = Cs = 1 a resposta média tem de colapsar em E[S]/(1-rho), resultado clássico
        de M/M/1. É o que autoriza usar a cauda exponencial fora do regime assintótico."""
        for rho in (0.3, 0.5, 0.75, 0.9):
            with self.subTest(rho=rho):
                wq = filas.espera_kingman(rho, 1.0, 1.0, 0.025)
                self.assertAlmostEqual(wq + 0.025, 0.025 / (1 - rho), places=12)

    def test_fila_instavel_estoura_em_vez_de_devolver_numero(self):
        for rho in (1.0, 1.5):
            with self.subTest(rho=rho):
                with self.assertRaises(ValueError):
                    filas.espera_kingman(rho, 1.0, 1.44, 0.025)

    def test_rho_em_m1_reproduz_o_valor_selado(self):
        """60 * 0,025 / 2 = 0,75 — o valor escrito no próprio arquivo de premissas."""
        self.assertAlmostEqual(filas.avaliar(self.cfg, 1.0)["rho"], 0.75, places=12)


class TestPontoDeOperacaoDerivado(unittest.TestCase):

    def setUp(self):
        self.cfg = filas.carregar(RAIZ)
        self.derivado = filas.ponto_iso_sla(self.cfg)

    def test_derivado_e_1_50(self):
        self.assertTrue(self.derivado["existe"])
        self.assertAlmostEqual(self.derivado["escolhido"]["multiplicador"], 1.50, places=9)

    def test_1_25_nao_cumpre_o_alvo(self):
        """O degrau anterior é o que um autor escolheria por parecer suficiente: 211,9 ms contra
        um alvo de 200 ms. Travar isto é travar a diferença entre derivar e arbitrar."""
        p = filas.avaliar(self.cfg, 1.25)
        self.assertFalse(p["atende"])
        self.assertAlmostEqual(p["resposta_p95_ms"], 211.9, places=1)

    def test_todos_os_cv_da_grade_caem_no_platô_de_custo(self):
        """O multiplicador derivado muda com a variabilidade suposta (1,25 · 1,50 · 1,50 · 2,00),
        mas o TCO NÃO muda em nenhum deles: a escada de SKU arredonda igual em [1,25; 2,00]. É
        por isso que o corpo pode afirmar que a suposição de variabilidade é imaterial ao
        veredito — e se a escada mudar, este teste cai antes do texto."""
        derivados = {l["multiplicador_derivado"] for l in filas.sensibilidade_cv(self.cfg)}
        self.assertTrue(derivados.issubset({1.25, 1.5, 2.0}), derivados)
        resumo = ler("tco-resumo.csv")
        for fase in (1, 2):
            for nuvem in ("ibm", "aws"):
                totais = {round(float(l["total_36m_usd"]), 4) for l in resumo
                          if int(l["fase"]) == fase and l["nuvem"] == nuvem
                          and float(l["multiplicador"]) in derivados}
                self.assertEqual(len(totais), 1,
                                 f"fase {fase}/{nuvem}: o custo varia dentro do platô {totais}")




class TestGradePorItem(unittest.TestCase):

    def test_soma_dos_itens_bate_com_o_resumo(self):
        grade, resumo = ler("tco-por-item-grade.csv"), ler("tco-resumo.csv")
        for l in resumo:
            chave = (int(l["fase"]), l["nuvem"], round(float(l["multiplicador"]), 4))
            soma = sum(float(g["usd_36m"]) for g in grade
                       if (int(g["fase"]), g["nuvem"],
                           round(float(g["multiplicador"]), 4)) == chave)
            self.assertAlmostEqual(soma, float(l["total_36m_usd"]), places=2, msg=str(chave))

    def test_bloco_domina_o_delta_da_fase_1(self):
        """A leitura central do corpo — o que separa as nuvens é bloco, não computação — sai
        deste teste, não da impressão de quem olhou o gráfico."""
        grade = [g for g in ler("tco-por-item-grade.csv")
                 if int(g["fase"]) == 1 and float(g["multiplicador"]) == 1.0]
        def item(nuvem, nome):
            return next(float(g["usd_36m"]) for g in grade
                        if g["nuvem"] == nuvem and g["item_custo"] == nome)
        self.assertLess(item("ibm", "compute"), item("aws", "compute"))
        self.assertGreater(item("ibm", "bloco"), 2.0 * item("aws", "bloco"))


@unittest.skipIf(figuras is None, "matplotlib ausente: geometria de figura não é verificável")
class TestFiguras(unittest.TestCase):

    def test_as_cinco_figuras_existem_e_cabem_no_orcamento(self):
        arquivos = sorted((RAIZ / "output" / "figuras").glob("figura-*.png"))
        self.assertEqual(len(arquivos), 5, [p.name for p in arquivos])
        for p in arquivos:
            with self.subTest(figura=p.name):
                self.assertLess(p.stat().st_size, 600 * 1024)

    def test_detalhe_da_ia_cumpre_o_criterio_de_emancipacao(self):
        """A figura 6 do inventário é condicional, e o critério é mecânico (emenda 04): o detalhe
        embutido na figura 2 só continua embutido se o corpo de texto não cair abaixo de 7 pt na
        largura útil de A4. O número TEM de ser medido — a primeira redação deste projeto afirmou
        '7,0 pt' sem medir, e a medição mostrou 6,7 pt: o desenho estava liberando exatamente o
        que o limiar existe para pegar."""
        medidas = json.loads((RAIZ / "output" / "figuras" / "MEDICOES.json")
                             .read_text(encoding="utf-8"))
        for painel, bandas in medidas["figura-2-arquitetura-fase-2.png"].items():
            ia = [b for b in bandas if b["rotulo"].startswith("CAMADA DE IA")]
            with self.subTest(painel=painel):
                self.assertEqual(len(ia), 1)
                self.assertGreaterEqual(ia[0]["fonte_sub"], figuras.PISO_LEGIBILIDADE_PT)

    def test_nenhum_texto_de_figura_abaixo_do_piso_absoluto(self):
        medidas = json.loads((RAIZ / "output" / "figuras" / "MEDICOES.json")
                             .read_text(encoding="utf-8"))
        for figura, paineis in medidas.items():
            for painel, bandas in paineis.items():
                for b in bandas:
                    with self.subTest(figura=figura, painel=painel, banda=b["rotulo"]):
                        self.assertGreaterEqual(b["fonte_sub"], figuras.MENOR_FONTE_PT)
                        self.assertGreaterEqual(b["fonte_titulo"], figuras.MENOR_FONTE_PT)








if __name__ == "__main__":
    unittest.main(verbosity=2)
