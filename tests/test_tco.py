#!/usr/bin/env python3
"""Provas executáveis do modelo de custo — inclusive a trava dos números publicados.

Estes testes são o único rigor cujo modo de falha o avaliador enxerga: número do texto diferente
do número da tabela. Se um preço mudar na fonte, a falha aqui é o sinal de que o **paper** precisa
ser atualizado — nunca o vetor. Cada constante literal foi lida do disco no momento em que o teste
foi escrito e está impressa aqui de propósito: o estágio `code` sela `tests/*.py`, então o vetor
não muda sem mudar o ROOT da cadeia.

Não há rede: tudo lê os corpos crus já capturados em `data/precos/`.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import capture_prices                                    # noqa: E402
import catalogo as cat_mod                               # noqa: E402
import tco                                               # noqa: E402

CFG = tco.carregar(RAIZ)
CAT = CFG["catalogo"]


class TestUnidadeDosBancosGerenciados(unittest.TestCase):
    """(ix) A métrica de host da IBM é MENSAL, apesar de `charge_unit: Instance-Hour`.

    Ler essa métrica como horária multiplicaria o lado IBM por 730 e destruiria o veredito. Três
    provas independentes, todas computadas dos corpos crus — nenhuma delas depende de acreditar
    no rótulo do catálogo, que é justamente o campo suspeito.
    """

    SERVICOS = ("mysql", "postgresql", "mongodb", "redis")

    def _metricas(self, servico: str, plano: str, regiao):
        return CAT.metricas_ibm(f"databases-for-{servico}", plano, regiao)

    def test_ix_a_nome_da_unidade_contradiz_o_rotulo(self) -> None:
        """`charge_unit_name` diz HOST_* e GIGABYTE_MONTHS_*; `charge_unit` diz Instance-Hour."""
        for servico in self.SERVICOS:
            arq = sorted((RAIZ / capture_prices.DIR_PRECOS)
                         .rglob(f"ibm-databases-for-{servico}-standard-br-sao-*.json"))[-1]
            metricas = json.loads(arq.read_text(encoding="utf-8"))["conteudo"]["metrics"]
            hosts = [m for m in metricas if m["charge_unit_name"].startswith("HOST_")]
            self.assertTrue(hosts, f"{servico}: nenhuma métrica de host")
            for m in hosts:
                self.assertEqual(m["charge_unit"], "Instance-Hour")      # o rótulo enganoso
                self.assertNotIn("HOUR", m["charge_unit_name"])          # o nome verdadeiro
            ram = [m for m in metricas if m["charge_unit_name"].endswith("_RAM")][0]
            self.assertEqual(ram["charge_unit_name"], "GIGABYTE_MONTHS_RAM")

    def test_ix_b_razao_com_o_plano_horario_e_da_ordem_de_um_mes(self) -> None:
        """O plano não-regional `standard-gen2` É horário. A razão entre os dois é ~730."""
        razoes = {}
        for servico in self.SERVICOS:
            regional = self._metricas(servico, "standard", "br-sao")
            horario = self._metricas(servico, "standard-gen2", None)
            mensal = next(v["faixas"][0][1] for k, v in regional.items() if k.endswith("-4-16"))
            hora = next(v["faixas"][0][1] for k, v in horario.items() if k.endswith("4-16"))
            razoes[servico] = mensal / hora
            self.assertTrue(400 < razoes[servico] < 1000,
                            f"{servico}: razão {razoes[servico]:.1f} fora da ordem de horas/mês")
        # MongoDB fecha em 730 — o número de horas do mês usado pela casa — a menos do
        # arredondamento da tabela publicada (0,4704 contra 343,3822/730 = 0,47038…)
        self.assertAlmostEqual(razoes["mongodb"], 730.0, delta=0.05)

    def test_ix_c_decomposicao_cpu_mais_ram_bate_no_host(self) -> None:
        """host(4x16) = cpu x 4 + ram x 16, com as métricas de cpu e RAM declaradas em MÊS."""
        for servico in ("mysql", "postgresql", "mongodb"):
            m = self._metricas(servico, "standard", "br-sao")
            cpu = next(v["faixas"][0][1] for k, v in m.items() if k.endswith("-cpu"))
            ram = next(v["faixas"][0][1] for k, v in m.items() if k.endswith("-ram"))
            host = next(v["faixas"][0][1] for k, v in m.items() if k.endswith("-4-16"))
            self.assertAlmostEqual(cpu * 4 + ram * 16, host, delta=host * 1e-4,
                                   msg=f"{servico}: decomposição não fecha")
        # Redis diverge ~5% e a divergência é DECLARADA: usa-se a métrica de host, que é a cobrada
        m = self._metricas("redis", "standard", "br-sao")
        cpu = next(v["faixas"][0][1] for k, v in m.items() if k.endswith("-cpu"))
        ram = next(v["faixas"][0][1] for k, v in m.items() if k.endswith("-ram"))
        host = next(v["faixas"][0][1] for k, v in m.items() if k.endswith("-4-16"))
        self.assertNotAlmostEqual(cpu * 4 + ram * 16, host, delta=host * 1e-3)
        self.assertLess(abs(cpu * 4 + ram * 16 - host) / host, 0.10)     # mesma ordem, não igual


class TestPrecosAncora(unittest.TestCase):
    """(x) Os preços que sustentam as tabelas do corpo, lidos do disco. Mudou a fonte -> falha
    aqui -> atualiza-se o PAPER."""

    def test_x_precos_unitarios_publicados(self) -> None:
        self.assertEqual(CAT.ibm("is.instance", "bxf-4x16", "instance-hours-bxf-4x16").preco, 0.266)
        self.assertEqual(CAT.ibm("is.instance", "cxf-2x4", "instance-hours-cxf-2x4").preco, 0.117)
        self.assertEqual(CAT.ibm("databases-for-mysql", "standard",
                                 "databases-for-mysql-4-16").preco, 304.4334)
        self.assertEqual(CAT.ibm("is.vpc", "nextgen-egress", "is.vpc.egress").preco, 0.115197)
        self.assertEqual(CAT.ibm_provisionamento("ibm-cloud-object-storage-br-sao",
                                                 "bandwidth", "standard").preco, 0.1935)
        self.assertEqual(CAT.ibm_provisionamento("ibm-cloud-object-storage-br-sao",
                                                 "storage", "standard").preco, 0.0296571)
        self.assertEqual(CAT.aws_um("AmazonEC2", lambda a: a.get("usagetype") ==
                                    "SAE1-EBS:VolumeUsage.gp3").preco, 0.152)
        self.assertEqual(CAT.aws_um("AmazonEC2", lambda a: a.get("usagetype") ==
                                    "SAE1-EBS:VolumeP-IOPS.gp3").preco, 0.0095)
        self.assertEqual(CAT.aws_um("AmazonEKS", lambda a: a.get("usagetype") ==
                                    "SAE1-AmazonEKS-Hours:perCluster").preco, 0.10)
        self.assertEqual(CAT.aws_um("AWSDataTransfer", lambda a: a.get("usagetype") ==
                                    "SAE1-DataTransfer-Out-Bytes").preco, 0.15)

    def test_x_precos_do_modelo_de_ia_pareado(self) -> None:
        """`gpt-oss-120b` com o MESMO identificador nos dois catálogos — e a leitura da página da
        IBM é a peça mais frágil do modelo (extração por posição relativa), então trava-se aqui."""
        self.assertEqual(CAT.ibm_pagina("ibm-watsonx-ai", "gpt-oss-120b").preco, 0.159)
        self.assertEqual(CAT.ibm_pagina("ibm-watsonx-ai", "gpt-oss-120b",
                                        deslocamento=1).preco, 0.636)
        self.assertEqual(CAT.aws_um("AmazonBedrock", lambda a: a.get("usagetype") ==
                                    "SAE1-gpt-oss-120b-input-tokens").preco, 0.00018)
        self.assertEqual(CAT.aws_um("AmazonBedrock", lambda a: a.get("usagetype") ==
                                    "SAE1-gpt-oss-120b-output-tokens").preco, 0.00073)
        # por milhão de tokens, a IBM é ~12% mais barata na entrada e na saída; o que separa as
        # duas nuvens na camada de IA não é preço, é a fronteira de dados (br-sao não declarado)
        self.assertAlmostEqual(0.159 / (0.00018 * 1000), 0.8833, places=3)

    def test_x_premio_do_gerenciado_sobre_a_base_REGIONAL(self) -> None:
        """O prêmio de 35% do STATE saiu do plano por hora e não-regional. Sobre o plano regional,
        cobrado por host e por mês, ele é de 57%. É este o número que vai ao texto."""
        gerenciado = CAT.ibm("databases-for-mysql", "standard", "databases-for-mysql-4-16").preco
        maquina = CAT.ibm("is.instance", "bxf-4x16", "instance-hours-bxf-4x16").preco * cat_mod.HORAS_MES
        self.assertAlmostEqual(maquina, 194.18, places=2)
        self.assertAlmostEqual(gerenciado / maquina - 1, 0.5677, places=3)


class TestEgressEmDuasParcelas(unittest.TestCase):
    """(xi) Cinco dos seis terabytes saem pelo objeto, e o objeto tem preço PRÓPRIO."""

    def test_xi_as_duas_tarifas_sao_distintas(self) -> None:
        objeto = CAT.ibm_provisionamento("ibm-cloud-object-storage-br-sao",
                                         "bandwidth", "standard").preco
        vpc = CAT.ibm("is.vpc", "nextgen-egress", "is.vpc.egress").preco
        self.assertGreater(objeto / vpc, 1.6, "o egress do objeto deixou de ser mais caro")

    def test_xi_modelar_tudo_pelo_vpc_subestimaria(self) -> None:
        d = CFG["premissas"]["dados_e_trafego"]
        gb_objeto = d["egress_objeto_tb_mes"] * tco.GB_POR_TB
        gb_app = d["egress_aplicacao_tb_mes"] * tco.GB_POR_TB
        t_obj = CAT.ibm_provisionamento("ibm-cloud-object-storage-br-sao", "bandwidth", "standard")
        t_vpc = CAT.ibm("is.vpc", "nextgen-egress", "is.vpc.egress")
        correto = t_obj.custo(gb_objeto) + t_vpc.custo(gb_app)
        so_vpc = t_vpc.custo(gb_objeto + gb_app)
        self.assertGreater(correto / so_vpc - 1, 0.50,
                           "a diferença entre as duas leituras encolheu — reconferir o modelo")

    def test_xi_volumetria_fica_na_primeira_faixa(self) -> None:
        """Enquanto o volume não cruza o primeiro degrau, `graduated` e `step` coincidem e a
        ambiguidade do rótulo capturado é imaterial. Se este teste falhar, a ambiguidade voltou
        a morder e exige fonte primária antes de publicar número."""
        d = CFG["premissas"]["dados_e_trafego"]
        for tarifa, gb in ((CAT.ibm("is.vpc", "nextgen-egress", "is.vpc.egress"),
                            d["egress_aplicacao_tb_mes"] * tco.GB_POR_TB),
                           (CAT.ibm_provisionamento("ibm-cloud-object-storage-br-sao",
                                                    "bandwidth", "standard"),
                            d["egress_objeto_tb_mes"] * tco.GB_POR_TB),
                           (CAT.aws_um("AWSDataTransfer", lambda a: a.get("usagetype") ==
                                       "SAE1-DataTransfer-Out-Bytes"),
                            (d["egress_objeto_tb_mes"] + d["egress_aplicacao_tb_mes"])
                            * tco.GB_POR_TB)):
            with self.subTest(tarifa=tarifa.recurso):
                self.assertLess(gb, tarifa.faixas[0][0], "volume cruzou o primeiro degrau")
                self.assertAlmostEqual(tarifa.custo(gb), gb * tarifa.preco, places=6)


class TestRegraDeSelecao(unittest.TestCase):
    """(xii) O SKU é derivado da evidência, e a escada falha em vez de improvisar."""

    ESCADA = [{"sku": "a", "vcpu": 2, "ram": 8, "usd_hora": 0.20},
              {"sku": "b", "vcpu": 4, "ram": 16, "usd_hora": 0.30},
              {"sku": "c", "vcpu": 4, "ram": 16, "usd_hora": 0.25}]

    def test_xii_escolhe_o_mais_barato_entre_os_aptos(self) -> None:
        self.assertEqual(tco.escolher(self.ESCADA, 4, 16, "teste")["sku"], "c")
        self.assertEqual(tco.escolher(self.ESCADA, 2, 8, "teste")["sku"], "a")

    def test_xii_falha_quando_a_escada_nao_alcanca(self) -> None:
        with self.assertRaises(LookupError) as ctx:
            tco.escolher(self.ESCADA, 32, 128, "teste")
        self.assertIn("não alcança", str(ctx.exception))

    def test_xii_paridade_x86_exclui_arm_no_cenario_primario(self) -> None:
        primario = {d["sku"] for d in tco.escada_aws(CAT, "AmazonEC2", "m")}
        com_arm = {d["sku"] for d in tco.escada_aws(CAT, "AmazonEC2", "m", admitir_arm=True)}
        self.assertTrue(primario < com_arm, "a exclusão de ARM deixou de mudar a escada")
        self.assertFalse([s for s in primario if s.split(".")[0].endswith(("g", "gd", "gn"))],
                         "família Graviton entrou no cenário primário")

    def test_xii_bloco_escolhe_a_opcao_mais_barata_que_entrega_o_alvo(self) -> None:
        """A 10 operações por gigabyte, o degrau `10iops-tier` bate o volume `custom`."""
        modelo = tco.Modelo(CFG)
        _custo, plano, _arq = modelo.disco_ibm("gen2-volume-custom", 1024)
        self.assertEqual(plano, "gen2-volume-10iops-tier")
        _custo, plano, _arq = modelo.disco_ibm("gen2-volume-general-purpose", 1024)
        self.assertEqual(plano, "gen2-volume-general-purpose")


class TestReferenteDaContagemDeDisco(unittest.TestCase):
    """O gate G-05 confere se o número existe entre as constantes; NÃO confere a que objeto ele
    se refere. Foi assim que "56,8% no banco transacional" passou verde sendo do analítico, e
    que "cinco dos doze servidores" sobreviveu a duas rodadas. Este teste trava o referente.
    """

    ALVO_ALTO = 10                                   # operações por gigabyte do degrau provisionado

    def servidores_com_disco_provisionado(self) -> set[str]:
        modelo = tco.Modelo(CFG)
        return {p["id"] for p in CFG["projeto"]["de_para"]
                if modelo.iops_alvo_por_gb(p["fase1_ibm"].get("disco", "")) >= self.ALVO_ALTO}

    def test_o_corpo_diz_quatro_e_sao_quatro_servidores_distintos(self) -> None:
        servidores = self.servidores_com_disco_provisionado()
        self.assertEqual(servidores, {"banco-1", "banco-4", "banco-5", "app-4"})
        self.assertEqual(len(servidores), 4)

    def test_a_apendice_a2_tem_cinco_linhas_e_isso_nao_e_cinco_servidores(self) -> None:
        """A origem nomeável do erro: banco-5 aparece nas duas fases, logo a A2 lista CINCO
        linhas `10iops-tier` para QUATRO servidores. Linha de tabela não é unidade de análise."""
        with (RAIZ / "output" / "tabelas" / "dimensionamento.csv").open(encoding="utf-8") as f:
            linhas = [l for l in csv.DictReader(f) if l["sku"] == "gen2-volume-10iops-tier"]
        self.assertEqual(len(linhas), 5)
        self.assertEqual(len({l["servidor"] for l in linhas}), 4)





class TestNumerosPublicados(unittest.TestCase):
    """(xiii) A trava contra o texto divergir da tabela: os totais que vão ao paper.

    Falha aqui = a fonte mudou. Atualiza-se o PAPER, nunca o vetor.
    """

    TCO_36M = {(1, "ibm"): 384802.19, (1, "aws"): 286970.04,
               (2, "ibm"): 429733.13, (2, "aws"): 349419.27}

    @classmethod
    def setUpClass(cls) -> None:
        cls.r = tco.executar(RAIZ, escrever=False)

    def test_xiii_totais_de_36_meses(self) -> None:
        for chave, esperado in self.TCO_36M.items():
            self.assertAlmostEqual(self.r["base"][chave]["total_36m"], esperado, places=2,
                                   msg=f"TCO de {chave} divergiu do publicado")

    def test_xiii_aws_vence_nas_duas_fases_no_ponto_de_operacao(self) -> None:
        for fase in (1, 2):
            self.assertLess(self.r["base"][(fase, "aws")]["total_36m"],
                            self.r["base"][(fase, "ibm")]["total_36m"])

    def test_xiii_o_delta_encolhe_quando_o_headroom_cresce(self) -> None:
        """O mecanismo da tese, medido: o método de dimensionamento move o veredito na direção
        da virada — de 23,0% para 7,7% na fase 2 — sem cruzar dentro da grade."""
        fase2 = sorted((l for l in self.r["grade"]["linhas"] if l["fase"] == 2),
                       key=lambda l: l["multiplicador"])
        self.assertAlmostEqual(fase2[0]["delta_pct_sobre_menor"], 22.99, places=1)
        self.assertAlmostEqual(fase2[-1]["delta_pct_sobre_menor"], 7.68, places=1)
        self.assertLess(fase2[-1]["delta_pct_sobre_menor"], fase2[0]["delta_pct_sobre_menor"])

    def test_xiii_veredito_da_tese_e_computado_e_nao_redigido(self) -> None:
        self.assertEqual(self.r["tese"]["veredito"], "TESE NÃO REFUTADA")
        self.assertEqual(len(self.r["tese"]["violacoes"]), 8)
        self.assertEqual(len(self.r["tese"]["deltas"]), 24)

    def test_xiii_nao_ha_virada_dentro_da_grade_pre_registrada(self) -> None:
        for v in self.r["viradas"]:
            self.assertFalse(v["existe"], "apareceu virada na grade — reescrever a leitura")
            self.assertEqual(v["de"], "aws")

    def test_xiii_determinismo(self) -> None:
        outra = tco.executar(RAIZ, escrever=False)
        for chave in self.TCO_36M:
            self.assertEqual(outra["base"][chave]["total_36m"],
                             self.r["base"][chave]["total_36m"])


class TestCoberturaDaTaxonomia(unittest.TestCase):
    """(xiv) D15 no nível do modelo: todo item aparece, e todo dominante tem número."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.r = tco.executar(RAIZ, escrever=False)
        cls.projeto = CFG["projeto"]

    def test_xiv_todos_os_dez_itens_aparecem_nas_quatro_configuracoes(self) -> None:
        for chave, cenario_ in self.r["base"].items():
            for item in self.projeto["taxonomia_custo"]["itens"]:
                self.assertIn(item, cenario_["tco"], f"{chave}: item {item} ausente")

    def test_xiv_dominantes_tem_numero(self) -> None:
        """`compute`, `bloco`, `objeto`, `egress` e `ia` com valor positivo; `banco-gerenciado` e
        `compute-oracle` aparecem decompostos em `compute` mais `premio-gerenciado`."""
        for (fase, nuvem), c in self.r["base"].items():
            for item in ("compute", "bloco", "objeto", "egress"):
                self.assertGreater(c["tco"][item], 0, f"({fase},{nuvem}) {item} sem número")
            if fase == 2:
                self.assertGreater(c["tco"]["ia"], 0, f"({fase},{nuvem}) camada de IA sem número")

    def test_xiv_itens_zerados_sao_os_declarados_na_emenda(self) -> None:
        # zeros legítimos: os três declarados na emenda 03 (suporte básico sem custo,
        # observabilidade e licença própria simétrica) e, na fase 1, o prêmio de gerenciado —
        # que é zero porque a fase 1 é lift-and-shift e não tem serviço gerenciado nenhum.
        for chave, c in self.r["base"].items():
            declarados = {"suporte", "observabilidade", "licencas"}
            if chave[0] == 1:
                declarados |= {"premio-gerenciado"}
            if chave == (2, "aws"):
                # assimetria medida: nenhum SKU de backup ou snapshot no offer file do RDS em
                # sa-east-1, contra métrica de backup por GB e mês nos quatro bancos da IBM
                declarados |= {"backup"}
            zerados = {i for i in self.projeto["taxonomia_custo"]["itens"] if c["tco"][i] == 0}
            self.assertTrue(zerados <= declarados,
                            f"{chave}: item zerado sem declaração na emenda 03: "
                            f"{zerados - declarados}")

    def test_xiv_sensibilidade_da_ia_nao_inverte_o_veredito(self) -> None:
        """Fato computado, não promessa: a escolha do volume de tokens é imaterial ao veredito."""
        self.assertEqual({linha["vencedor"] for linha in self.r["ia"]}, {"aws"})


class TestSensibilidadeMembros(unittest.TestCase):
    """Trava o contrafactual de membros que o corpo publica (plano r2, item 6).

    Os dois números do texto — 42,9% e a monotonicidade — nascem aqui. Sem esta trava, o corpo
    citaria um contrafactual que ninguém recomputa, que é o defeito que o gate de números existe
    para pegar.
    """

    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(RAIZ / "src"))
        import sensibilidade_membros            # noqa: E402
        cls.mod = sensibilidade_membros
        cls.r = sensibilidade_membros.calcular()

    def test_afeta_os_cinco_bancos_gerenciados_e_nada_mais(self) -> None:
        """Kubernetes e Code Engine não entram: a acusação é sobre `IBM Cloud Databases`."""
        self.assertEqual(self.r["linhas_afetadas"], 5)
        self.assertAlmostEqual(self.r["mensal_capturado_usd"], 1929.2246, places=3)

    def test_o_delta_da_fase_2_sobe_de_23_para_42_9(self) -> None:
        self.assertAlmostEqual(self.r["delta_pct_base"], 22.985, places=2)
        self.assertAlmostEqual(self.r["delta_pct_contrafactual"], 42.861, places=2)

    def test_o_contrafactual_nao_inverte_o_veredito_e_e_monotonico(self) -> None:
        """A hipótese só pode afastar a IBM: com três hosts, a diferença cresce de novo."""
        self.assertEqual(self.r["vencedor_base"], self.r["vencedor_contrafactual"], "aws")
        base = self.r["delta_pct_contrafactual"]
        self.mod.FATOR_HIPOTESE = 3
        try:
            maior = self.mod.calcular()["delta_pct_contrafactual"]
        finally:
            self.mod.FATOR_HIPOTESE = 2
        self.assertGreater(maior, base)


if __name__ == "__main__":
    unittest.main()
