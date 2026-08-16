#!/usr/bin/env python3
"""Modelo de custo total de propriedade — as quatro configurações, os dois métodos de
dimensionamento, os dez itens da taxonomia, 36 meses.

    python3 src/tco.py            # computa tudo e escreve os CSV em output/tabelas/
    python3 src/tco.py --resumo   # imprime o resumo no terminal, sem escrever

O que este arquivo NÃO faz, por construção:

- **não digita preço**: toda tarifa vem de `catalogo.py`, que só lê os corpos crus em disco;
- **não escolhe SKU à mão**: aplica a regra selada (menor degrau da família declarada que
  satisfaça vCPU e RAM; empate pelo menor preço) e falha se a escada capturada não alcançar o
  requisito — substituir em silêncio seria inventar catálogo;
- **não importa nada de teoria de filas**: o ponto de virada é função apenas dos preços
  capturados e das escadas dos dois catálogos. Se este módulo dependesse de `rho`, a afirmação
  de invariância aos parâmetros de fila seria falsa e inspecionável. A curva de Kingman é
  ilustração, vive fora daqui, e entra no paper como figura.

**Precisão da claim de invariância** (escrita assim no corpo, porque a versão curta seria falsa):
o ponto de virada é invariante aos parâmetros que permitiriam escolher o resultado — utilização,
variabilidade e taxa de chegada — e é **condicional ao vetor de demanda selado**, porque saída de
dados e armazenamento de objetos escalam com ele. As duas coisas são diferentes e o paper diz as
duas.

Os itens de custo são os dez da taxonomia selada. Dois merecem nota:

- **`premio-gerenciado` é decomposição exata, não estimativa**: para todo recurso que a fase 2
  entrega gerenciado, `compute` recebe o que a MESMA capacidade custaria em máquina virtual na
  MESMA nuvem, e `premio-gerenciado` recebe a diferença. A soma é o preço real do serviço; a
  separação é o que transforma "prêmio do gerenciado" de adjetivo em número. Pode dar negativo,
  e se der, sai negativo.
- **`licencas`**: zero no cenário primário por convenção D13 (licença própria simétrica: o custo
  existe, mas fora da fatura da nuvem). O cenário de licença inclusa da AWS é nomeado à parte.

ponytail: dívida aceita — módulo único e longo, em vez de `dimensionamento`/`custo`/`grade`
separados. A coesão é real (tudo é o mesmo cálculo, e a fronteira natural — leitura de preço —
já está fora, em `catalogo.py`), e sob o prazo de 17/08 dividir agora custaria um re-selo da
cadeia sem mudar um número. Dividir depois da entrega, se sobrar tempo.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from catalogo import HORAS_MES, Catalogo, Tarifa   # noqa: E402

MESES = 36
GB_POR_TB = 1024
TAXONOMIA = ["compute", "bloco", "objeto", "egress", "licencas", "premio-gerenciado",
             "backup", "suporte", "rede-ip-balanceador", "observabilidade"]
CONFIG_ID = {(1, "ibm"): "C1", (1, "aws"): "C2", (2, "ibm"): "C3", (2, "aws"): "C4"}

# Famílias declaradas no de-para -> prefixo no catálogo de cada nuvem.
FAMILIA_IBM = {"bxf": "bxf", "cxf": "cxf", "bare-metal + bxf": "bxf"}
FAMILIA_AWS = {"general-purpose": "m", "compute-optimized": "c"}


# --------------------------------------------------------------------------- #
# configuração                                                                #
# --------------------------------------------------------------------------- #
def carregar(raiz: Path = RAIZ) -> dict:
    def js(nome: str) -> dict:
        return json.loads((raiz / "configs" / nome).read_text(encoding="utf-8"))
    return {"caso": js("caso-xyz.json"), "projeto": js("projeto-tecnico.json"),
            "premissas": js("premissas-carga.json"), "emenda": js("emenda-03-2026-08-13.json"),
            "membros": js("emenda-07-2026-08-16.json"),
            "redundancia": js("emenda-08-2026-08-16.json"), "catalogo": Catalogo(raiz)}


# --------------------------------------------------------------------------- #
# escadas de capacidade — a diferenciação legítima entre as nuvens             #
# --------------------------------------------------------------------------- #
def _mem_gib(texto: str | None) -> float:
    return float((texto or "0").split()[0]) if texto else 0.0


def escada_ibm_vm(cat: Catalogo, familia: str) -> list[dict]:
    """Degraus `bxf`/`cxf` capturados em br-sao, com o preço por hora de cada um."""
    degraus = []
    for planos in ([f"{familia}-{v}x{r}" for v, r in ((2, 8), (4, 16), (8, 32), (16, 64))]
                   if familia == "bxf" else
                   [f"{familia}-{v}x{r}" for v, r in ((2, 4), (4, 8), (8, 16), (16, 32))]):
        vcpu, ram = (int(x) for x in planos.split("-")[1].split("x"))
        tarifa = cat.ibm("is.instance", planos, f"instance-hours-{planos}")
        degraus.append({"sku": planos, "vcpu": vcpu, "ram": ram,
                        "usd_hora": tarifa.preco, "tarifa": tarifa})
    return sorted(degraus, key=lambda d: (d["vcpu"], d["ram"], d["usd_hora"]))


def _aws_x86_corrente(a: dict, prefixo: str, campo_tipo: str = "instanceType",
                      admitir_arm: bool = False) -> bool:
    """Paridade de SKU da emenda 03: x86, geração corrente, desempenho sustentado.

    O nome da família decide o ARM junto com `physicalProcessor` porque parte dos produtos
    Graviton vem com esse atributo nulo no offer file (medido em `db.m8gd.*`): confiar só no
    processador declarado deixaria ARM entrar no cenário primário sem que nada acusasse.
    """
    tipo = a.get(campo_tipo) or ""
    familia = tipo.split(".")[-2] if tipo.count(".") == 2 else tipo.split(".")[0]
    if not familia.startswith(prefixo) or familia.startswith("t"):
        return False
    if a.get("currentGeneration") != "Yes":
        return False
    arm = bool(re.search(r"g[dn]?$", familia)) or "Graviton" in (a.get("physicalProcessor") or "")
    return admitir_arm or not arm


def escada_aws(cat: Catalogo, servico: str, prefixo: str, extra=lambda a: True,
               campo_tipo: str = "instanceType", admitir_arm: bool = False) -> list[dict]:
    """Degraus da AWS na fatia capturada que satisfazem a paridade de SKU declarada."""
    degraus = {}
    for atributos, tarifa in cat.aws_produtos(servico, lambda a: (
            a.get(campo_tipo) and _aws_x86_corrente(a, prefixo, campo_tipo, admitir_arm)
            and extra(a))):
        tipo = atributos[campo_tipo]
        item = {"sku": tipo, "vcpu": int(atributos["vcpu"]), "ram": _mem_gib(atributos.get("memory")),
                "usd_hora": tarifa.preco, "tarifa": tarifa}
        if tipo not in degraus or item["usd_hora"] < degraus[tipo]["usd_hora"]:
            degraus[tipo] = item
    return sorted(degraus.values(), key=lambda d: (d["vcpu"], d["ram"], d["usd_hora"]))


def escada_ibm_gerenciado(cat: Catalogo, servico: str) -> list[dict]:
    """Degraus (`4-16`, `8-32`, …) de um banco gerenciado da IBM, plano regional `standard`.

    ATENÇÃO À UNIDADE: o valor é **mensal**, apesar de `charge_unit: Instance-Hour` — ver a
    docstring de `catalogo.py` e os três testes que travam esse fato.
    """
    degraus = []
    for mid, v in cat.metricas_ibm(servico, "standard").items():
        casa = re.search(r"(\d+)-(\d+)$", mid)
        if not casa or not any(p for _, p in v["faixas"]):
            continue
        vcpu, ram = int(casa.group(1)), int(casa.group(2))
        degraus.append({"sku": mid, "vcpu": vcpu, "ram": ram,
                        "usd_mes": v["faixas"][0][1],
                        "tarifa": cat.ibm(servico, "standard", mid)})
    return sorted(degraus, key=lambda d: (d["vcpu"], d["ram"], d["usd_mes"]))


def escolher(escada: list[dict], vcpu: float, ram: float, onde: str) -> dict:
    """Regra selada: o degrau mais barato que satisfaz os dois requisitos.

    A regra em `projeto-tecnico.json` diz "menor SKU que satisfaça; havendo empate de capacidade,
    vence o menor preço". Aplicada à letra, ela ordena por capacidade e pode escolher um degrau
    MAIS CARO por ter alguns décimos de gigabyte a menos — medido no catálogo de cache da AWS:
    `cache.r4.large` (12,30 GiB, USD 0,455/h) venceria `cache.r5.large` (13,07 GiB, USD 0,432/h).
    Pagar mais por menos não é o que a regra quer dizer, e nenhum arquiteto o faria. Adota-se a
    ordenação por preço, com a capacidade como desempate — igualmente determinística, imune à
    escolha a dedo (que é o que a regra existe para impedir) e economicamente correta. O desvio
    está declarado na emenda 03.
    """
    aptos = [d for d in escada if d["vcpu"] >= vcpu - 1e-9 and d["ram"] >= ram - 1e-9]
    if not aptos:
        teto = max(((d["vcpu"], d["ram"]) for d in escada), default=(0, 0))
        raise LookupError(
            f"{onde}: a escada capturada não alcança {vcpu:g} vCPU / {ram:g} GB (maior degrau: "
            f"{teto[0]:g}x{teto[1]:g}). Capturar o degrau maior ou declarar a limitação — o modelo "
            f"NÃO substitui por um degrau menor.")
    return min(aptos, key=lambda d: (d.get("usd_hora", d.get("usd_mes")), d["vcpu"], d["ram"]))


# --------------------------------------------------------------------------- #
# dimensionamento                                                             #
# --------------------------------------------------------------------------- #
def requisito(servidor: dict, multiplicador: float) -> tuple[float, float]:
    """Capacidade exigida. O multiplicador do método iso-SLA incide **só** onde o nível de
    serviço morde (corte de escopo travado no STATE: banco-1, app-2, app-6)."""
    m = multiplicador if servidor.get("sla_morde") else 1.0
    return servidor["vcpu"] * m, servidor["ram_gb"] * m


class Modelo:
    """Custos mensais por item da taxonomia, para uma nuvem e uma fase."""

    def __init__(self, cfg: dict, opcoes: dict | None = None) -> None:
        self.cat: Catalogo = cfg["catalogo"]
        self.caso, self.projeto = cfg["caso"], cfg["projeto"]
        self.premissas, self.emenda = cfg["premissas"], cfg["emenda"]
        self.membros = cfg["membros"]
        self.redundancia = cfg["redundancia"]
        # cenários de sensibilidade nomeados ANTES de capturar (pré-registro §5 e emenda 03);
        # o cenário primário é o dicionário vazio, e é o que alimenta as tabelas do corpo.
        self.opcoes = {"arm": False, "oracle_ibm": None, "oracle_aws_licenca": None,
                       "disco_banco_1_uso_geral": False} | (opcoes or {})
        self.detalhe: list[dict] = []
        self._escadas: dict[tuple, list[dict]] = {}

    # -- escadas com memória (a captura é lida uma vez) --------------------- #
    def escada(self, chave: tuple) -> list[dict]:
        if chave not in self._escadas:
            provedor, tipo, arg = chave
            if provedor == "ibm" and tipo == "vm":
                self._escadas[chave] = escada_ibm_vm(self.cat, arg)
            elif provedor == "ibm" and tipo == "gerenciado":
                self._escadas[chave] = escada_ibm_gerenciado(self.cat, arg)
            elif provedor == "aws" and tipo == "ec2":
                self._escadas[chave] = escada_aws(self.cat, "AmazonEC2", arg,
                                                  admitir_arm=self.opcoes["arm"])
            elif provedor == "aws" and tipo == "rds":
                motor, implantacao, licenca = arg
                self._escadas[chave] = escada_aws(
                    self.cat, "AmazonRDS", "m",
                    lambda a: (a.get("databaseEngine") == motor
                               and a.get("deploymentOption") == implantacao
                               and a.get("licenseModel") == licenca),
                    admitir_arm=self.opcoes["arm"])
            elif provedor == "aws" and tipo == "docdb":
                self._escadas[chave] = escada_aws(
                    self.cat, "AmazonDocDB", "r",
                    lambda a: "InstanceUsage:" in (a.get("usagetype") or ""),
                    admitir_arm=self.opcoes["arm"])
            elif provedor == "aws" and tipo == "cache":
                self._escadas[chave] = escada_aws(
                    self.cat, "AmazonElastiCache", arg,
                    lambda a: (a.get("cacheEngine") == "Redis"
                               and (a.get("usagetype") or "").startswith("SAE1-NodeUsage")),
                    admitir_arm=self.opcoes["arm"])
            else:
                raise KeyError(chave)
        return self._escadas[chave]

    def _reg(self, **kw) -> None:
        self.detalhe.append(kw)

    # -- blocos de custo ---------------------------------------------------- #
    def iops_alvo_por_gb(self, classe: str) -> int:
        """A classe nomeada no de-para vira REQUISITO de desempenho, não SKU obrigatório.

        Cada degrau de volume da IBM entrega uma razão declarada de operações por segundo por
        gigabyte; o `custom` entrega a que se provisionar, e a emenda 03 fixa esse alvo em dez.
        Traduzir a classe para o requisito é o que permite aplicar dos dois lados a mesma regra
        selada — menor preço entre as opções que satisfazem —, e o que impede a comparação de
        medir escolha de projeto em vez de preço.
        """
        return {"gen2-volume-general-purpose": 3, "gen2-volume-5iops-tier": 5,
                "gen2-volume-10iops-tier": 10,
                "gen2-volume-custom": self.emenda["iops_e_classe_de_disco"]["iops_por_gb"],
                "general-purpose": 3}.get(classe, 3)

    def disco_ibm(self, classe: str, gb: float) -> tuple[float, str, str]:
        """Opção de bloco mais barata da IBM que entrega o alvo de operações por segundo.

        Medido em 2026-08-13 e material: a 10 operações por gigabyte, o volume `custom` sai a
        1,327 USD por gigabyte e mês (0,1658 de armazenamento mais dez vezes 0,1161 de IOPS)
        contra 0,796 do degrau `10iops-tier`. Honrar o nome literal do de-para nesses casos
        cobraria da IBM 67% a mais por desempenho idêntico — penalidade de escolha de projeto,
        não de catálogo.
        """
        alvo = self.iops_alvo_por_gb(classe)
        opcoes = []
        for plano, entrega in (("gen2-volume-general-purpose", 3), ("gen2-volume-5iops-tier", 5),
                               ("gen2-volume-10iops-tier", 10)):
            if entrega >= alvo:
                t = self.cat.ibm("is.volume", plano, f"is.volume.{plano.split('-', 2)[2].replace('-', '')}.GB")
                opcoes.append((t.custo(gb) * HORAS_MES, plano, t.arquivo))
        t_gb = self.cat.ibm("is.volume", "gen2-volume-custom", "is.volume.custom.GB")
        t_iops = self.cat.ibm("is.volume", "gen2-volume-custom", "is.volume.custom.IOPS")
        opcoes.append(((t_gb.custo(gb) + t_iops.custo(alvo * gb)) * HORAS_MES,
                       "gen2-volume-custom", t_gb.arquivo))
        custo, plano, arquivo = min(opcoes)
        return custo, plano, arquivo

    def disco_aws(self, classe: str, gb: float) -> tuple[float, str, str]:
        """gp3 com o MESMO alvo de operações por segundo; IOPS só acima da franquia documentada."""
        alvo = self.iops_alvo_por_gb(classe) * gb
        armazenamento = self.cat.aws_um("AmazonEC2", lambda a: a.get("usagetype") ==
                                        "SAE1-EBS:VolumeUsage.gp3")
        custo = armazenamento.custo(gb)
        excedente = max(0.0, alvo - self.emenda["iops_e_classe_de_disco"]["franquia_gp3"]
                        ["iops_incluidos"])
        if excedente:
            custo += self.cat.aws_um("AmazonEC2", lambda a: a.get("usagetype") ==
                                     "SAE1-EBS:VolumeP-IOPS.gp3").custo(excedente)
        return custo, f"gp3 ({alvo:.0f} IOPS)", armazenamento.arquivo

    # -- fase 1: máquina virtual + bloco ------------------------------------ #
    def classe_de_disco(self, servidor_id: str) -> str:
        """A classe declarada no de-para, com um cenário de sensibilidade nomeado para o banco-1.

        Achado 2 (GRAVE) da auditoria externa: a linha de base do banco-1 pede apenas alta
        disponibilidade, e o degrau de dez operações por gigabyte foi fixado porque o degrau
        comercial existe — raciocínio circular no mecanismo central da tese. A resposta honesta
        não é remover o degrau (o de-para o declarou ANTES da captura, e mexer nele agora seria
        escolher o resultado): é PRECIFICAR a alternativa e publicar o número.
        """
        classe = next(d["fase1_ibm"]["disco"] for d in self.projeto["de_para"]
                      if d["id"] == servidor_id)
        if servidor_id == "banco-1" and self.opcoes["disco_banco_1_uso_geral"]:
            return "gen2-volume-general-purpose"
        return classe

    def fase1(self, nuvem: str, servidor: dict, alvo: dict, mult: float) -> dict[str, float]:
        vcpu, ram = requisito(servidor, mult)
        n = alvo.get("instancias", 1)
        # a classe de disco declarada do lado IBM define o ALVO de desempenho dos dois lados
        classe = self.classe_de_disco(servidor["id"])
        gb = servidor["armazenamento_gb"] * n
        if nuvem == "ibm" and servidor["tecnologia"] == "Oracle Database":
            # os DOIS caminhos da D13 valem já na fase 1: o lift-and-shift literal é a máquina
            # virtual, e o bare metal é o cenário de sensibilidade nomeado
            saida = self.oracle_ibm(servidor, mult)
            bloco, sku_bloco, arq_bloco = self.disco_ibm(classe, gb)
            self._reg(servidor=servidor["id"], fase=1, nuvem=nuvem, papel="compute",
                      sku=saida["sku"], vcpu="", ram="", instancias=n, usd_mes=saida["compute"],
                      arquivo_fonte=saida["arquivo"])
            self._reg(servidor=servidor["id"], fase=1, nuvem=nuvem, papel="bloco", sku=sku_bloco,
                      vcpu="", ram="", instancias=n, usd_mes=bloco, arquivo_fonte=arq_bloco)
            return {"compute": saida["compute"], "bloco": bloco}
        if nuvem == "ibm":
            degrau = escolher(self.escada(("ibm", "vm", FAMILIA_IBM[alvo["familia"]])), vcpu, ram,
                              f"{servidor['id']} fase 1 IBM")
            bloco, sku_bloco, arq_bloco = self.disco_ibm(classe, gb)
        else:
            degrau = escolher(self.escada(("aws", "ec2", FAMILIA_AWS[alvo["familia"]])), vcpu, ram,
                              f"{servidor['id']} fase 1 AWS")
            bloco, sku_bloco, arq_bloco = self.disco_aws(classe, gb)
        compute = degrau["usd_hora"] * HORAS_MES * n
        self._reg(servidor=servidor["id"], fase=1, nuvem=nuvem, papel="compute", sku=degrau["sku"],
                  vcpu=degrau["vcpu"], ram=degrau["ram"], instancias=n, usd_mes=compute,
                  arquivo_fonte=degrau["tarifa"].arquivo)
        self._reg(servidor=servidor["id"], fase=1, nuvem=nuvem, papel="bloco", sku=sku_bloco,
                  vcpu="", ram="", instancias=n, usd_mes=bloco, arquivo_fonte=arq_bloco)
        return {"compute": compute, "bloco": bloco}

    # -- fase 2: gerenciado, contêiner ou serverless ------------------------ #
    def fase2(self, nuvem: str, servidor: dict, alvo: dict, mult: float) -> dict[str, float]:
        servico = alvo["servico"]
        vcpu, ram = requisito(servidor, mult)
        par_fase1 = next(d[f"fase1_{nuvem}"] for d in self.projeto["de_para"]
                         if d["id"] == servidor["id"])
        n = par_fase1.get("instancias", 1)     # continuidade: mesma redundância da fase 1
        gb = servidor["armazenamento_gb"]

        # o custo da mesma capacidade em máquina virtual — base da decomposição do prêmio
        base_vm = self.fase1_equivalente(nuvem, servidor, par_fase1, mult)

        if "Bare Metal" in servico or servico.startswith("permanece"):
            saida = self.oracle_ibm(servidor, mult)
            self._reg(servidor=servidor["id"], fase=2, nuvem=nuvem, papel="compute-oracle",
                      sku=saida["sku"], vcpu="", ram="", instancias=1,
                      usd_mes=saida["compute"], arquivo_fonte=saida["arquivo"])
            bloco, sku_bloco, arq = self.disco_ibm(par_fase1["disco"], gb)
            self._reg(servidor=servidor["id"], fase=2, nuvem="ibm", papel="bloco",
                      sku=sku_bloco, vcpu="", ram="", instancias=1, usd_mes=bloco,
                      arquivo_fonte=arq)
            return {"compute": saida["compute"], "bloco": bloco,
                    "backup": self.backup_objeto(nuvem, gb)}

        if servico.startswith("Databases for"):
            motor = servico.split()[-1].lower()
            degrau = escolher(self.escada(("ibm", "gerenciado", f"databases-for-{motor}")),
                              vcpu, ram, f"{servidor['id']} fase 2 IBM")
            # emenda 07: as três correções que a documentação primária da IBM autoriza, e só elas.
            # (i) a tarifa capturada é POR HOST e o plano `standard` provisiona vários membros de
            # dados; (ii) o disco é alocado POR MEMBRO, mas o fator é o que cada página declara —
            # o MongoDB tem três membros e disco de ao menos duas vezes o conjunto de dados, de
            # sorte que usar membros como multiplicador de disco extrapolaria; (iii) a cópia de
            # segurança é gratuita até o disco provisionado, e a regra selada de retenção é uma
            # cópia completa, logo a linha é zero — o mesmo tratamento por franquia que o lado AWS
            # já recebia em `gerenciado_aws`, que é a simetria que dois auditores cobraram.
            membros = self.membros["membros_por_motor"][motor]
            mult_disco = self.membros["multiplicador_de_disco_por_motor"][motor]
            total = degrau["usd_mes"] * membros
            disco = self.cat.ibm(f"databases-for-{motor}", "standard", "-disk").custo(gb * mult_disco)
            backup = self.membros["franquia_de_backup"]["custo_no_cenario_primario_usd_mes"]
            arquivo = degrau["tarifa"].arquivo
            sku = f"{degrau['sku']} ×{membros}"
        elif servico.startswith("RDS for") or servico == "DocumentDB" or "ElastiCache" in servico:
            total, disco, backup, sku, arquivo = self.gerenciado_aws(servidor, servico, vcpu,
                                                                     ram, gb)
        elif "Kubernetes" in servico or "EKS" in servico:
            total, disco, backup, sku, arquivo = self.kubernetes(nuvem, servidor, vcpu, ram, n)
            # o prêmio do contêiner isola a GESTÃO, então a base é a máquina virtual do MESMO
            # perfil do trabalhador — comparar com outra família mediria diferença de família.
            base_vm = (self.vm_do_perfil(sku.split(".")[-1], n) if nuvem == "ibm"
                       else {"usd_mes": total, "sku": sku, "arquivo": arquivo})
        elif "Code Engine" in servico or "Lambda" in servico:
            total, disco, backup, sku, arquivo = self.serverless(nuvem)
            # serverless não tem máquina virtual equivalente: todo o custo é computação, e o
            # prêmio fica em zero por definição, não por arredondamento.
            base_vm = {"usd_mes": total, "sku": "sem equivalente em máquina virtual",
                       "arquivo": arquivo}
        else:
            raise ValueError(f"serviço de fase 2 sem regra de custo: {servico!r}")

        premio = total - base_vm["usd_mes"]
        self._reg(servidor=servidor["id"], fase=2, nuvem=nuvem, papel="gerenciado", sku=sku,
                  vcpu=vcpu, ram=ram, instancias=n, usd_mes=total, arquivo_fonte=arquivo)
        self._reg(servidor=servidor["id"], fase=2, nuvem=nuvem, papel="premio-gerenciado",
                  sku=f"{sku} − {base_vm['sku']}", vcpu="", ram="", instancias=n, usd_mes=premio,
                  arquivo_fonte=base_vm["arquivo"])
        return {"compute": base_vm["usd_mes"], "premio-gerenciado": premio,
                "bloco": disco, "backup": backup}

    def vm_do_perfil(self, perfil: str, n: int) -> dict:
        """Máquina virtual do perfil exato (`bxf-4x16`) — base do prêmio do contêiner."""
        degrau = next(d for d in self.escada(("ibm", "vm", perfil.split("-")[0]))
                      if d["sku"] == perfil)
        return {"usd_mes": degrau["usd_hora"] * HORAS_MES * n, "sku": degrau["sku"],
                "arquivo": degrau["tarifa"].arquivo}

    def fase1_equivalente(self, nuvem: str, servidor: dict, par: dict, mult: float) -> dict:
        """O que a mesma capacidade custaria em máquina virtual — base do prêmio do gerenciado."""
        vcpu, ram = requisito(servidor, mult)
        n = par.get("instancias", 1)
        if nuvem == "ibm":
            degrau = escolher(self.escada(("ibm", "vm", FAMILIA_IBM[par["familia"]])), vcpu, ram,
                              f"{servidor['id']} base VM IBM")
        else:
            degrau = escolher(self.escada(("aws", "ec2", FAMILIA_AWS[par["familia"]])), vcpu, ram,
                              f"{servidor['id']} base VM AWS")
        return {"usd_mes": degrau["usd_hora"] * HORAS_MES * n, "sku": degrau["sku"],
                "arquivo": degrau["tarifa"].arquivo}

    def replicas_aws(self, servidor_id: str) -> int:
        """Emenda 08: quantas réplicas de dados a linha da AWS paga nesta comparação.

        O número vem do plano da IBM porque é o lado que NÃO permite escolher — o Standard é HA
        por construção. Fixar a unidade pelo lado rígido e levar a nuvem flexível até ela é o que
        impede que a escolha de implantação decida o veredito, que foi a acusação externa.
        """
        entrada = self.redundancia["replicas_por_servidor"].get(servidor_id)
        return entrada["replicas"] if entrada else 1

    def gerenciado_aws(self, servidor: dict, servico: str, vcpu: float, ram: float,
                       gb: float) -> tuple:
        # emenda 08: preço unitário x réplicas, na instância E no armazenamento. A implantação
        # deixa de ser escolhida por `sla_morde`: usa-se sempre o unitário Single-AZ como unidade,
        # porque a própria AWS cobra o dobro dele para duas réplicas (medido, e travado por KAT).
        n_rep = self.replicas_aws(servidor["id"])
        if servico.startswith("RDS for"):
            motor = servico.split()[-1]
            implantacao = "Single-AZ"
            # D13: licença própria simétrica no primário. A licença inclusa só existe na edição
            # Standard Two da AWS e entra apenas no cenário de sensibilidade nomeado.
            licenca = ("Bring your own license" if motor == "Oracle" else "No license required")
            if motor == "Oracle" and self.opcoes["oracle_aws_licenca"] == "inclusa":
                licenca = "License included"
            degrau = escolher(self.escada(("aws", "rds", (motor, implantacao, licenca))), vcpu, ram,
                              f"{servidor['id']} fase 2 RDS")
            disco = self.cat.aws_um("AmazonRDS", lambda a: (
                a.get("databaseEngine") == motor
                and a.get("usagetype") == "SAE1-RDS:GP3-Storage")).custo(gb) * n_rep
        elif servico == "DocumentDB":
            degrau = escolher(self.escada(("aws", "docdb", None)), vcpu, ram,
                              f"{servidor['id']} fase 2 DocumentDB")
            disco = self.cat.aws_um("AmazonDocDB", lambda a: a.get("usagetype") ==
                                    "SAE1-StorageUsage").custo(gb) * n_rep
        else:                                              # ElastiCache: cache é servido de memória
            degrau = escolher(self.escada(("aws", "cache", "r")), vcpu, ram,
                              f"{servidor['id']} fase 2 ElastiCache")
            disco = 0.0
        # Backup do lado AWS na fase 2 = 0,00 por FRANQUIA, não por lacuna de captura. A emenda 03
        # dizia "nenhum SKU de backup ou snapshot na fatia capturada"; a razão estava mal fundada,
        # porque a fatia retém só `Database Instance`, `Database Storage` e `System Operation` — a
        # família de snapshot é excluída pelo próprio filtro, e ausência na fatia nunca foi
        # evidência sobre o catálogo. A razão verdadeira, com fonte capturada em 14/08/2026
        # (aws.amazon.com/rds/faqs): "Free backup storage is provided up to your account's total
        # provisioned database storage across the entire region." É documentação pública que resume
        # a posição comercial, não cláusula contratual verificada. A regra selada é UMA cópia
        # completa, que iguala o provisionado e cabe inteira na franquia. Registro e trecho literal
        # em 00-material-fonte/research/EIXO-6-sla-ferramentas-politicas.md.
        sku = degrau["sku"] if n_rep == 1 else f"{degrau['sku']} \u00d7{n_rep}"
        return (degrau["usd_hora"] * HORAS_MES * n_rep, disco, 0.0, sku,
                degrau["tarifa"].arquivo)

    def kubernetes(self, nuvem: str, servidor: dict, vcpu: float, ram: float, n: int) -> tuple:
        """Trabalhador do cluster. O plano de controle NÃO entra aqui: é um só para todo o
        ambiente e entra uma única vez nos compartilhados da fase 2 — ratear por aplicação
        inventaria um custo por servidor que nenhum dos dois catálogos cobra assim."""
        if nuvem == "ibm":
            degrau = escolher(self.escada_worker_iks(), vcpu, ram, f"{servidor['id']} worker IKS")
        else:
            degrau = escolher(self.escada(("aws", "ec2", "m")), vcpu, ram,
                              f"{servidor['id']} worker EKS")
        total = degrau["usd_hora"] * HORAS_MES * n
        gb = servidor["armazenamento_gb"] * n
        # o requisito de desempenho de disco NÃO desaparece com a contêinerização: o app-4 pede
        # alta capacidade de entrada e saída nas duas fases. Mantém-se a classe da fase 1.
        classe = next(d["fase1_ibm"]["disco"] for d in self.projeto["de_para"]
                      if d["id"] == servidor["id"])
        disco, _sku, _arq = (self.disco_ibm(classe, gb) if nuvem == "ibm"
                             else self.disco_aws(classe, gb))
        return total, disco, 0.0, degrau["sku"], degrau["tarifa"].arquivo

    def escada_worker_iks(self) -> list[dict]:
        """Só dois perfis de trabalhador foram capturados (`bxf-4x16` e `bxf-8x32`); a regra de
        seleção falha em vez de improvisar se o requisito passar do maior deles."""
        if ("ibm", "iks", None) not in self._escadas:
            degraus = []
            for perfil in ("bxf-4x16", "bxf-8x32"):
                v, r = (int(x) for x in perfil.split("-")[1].split("x"))
                tarifa = self.cat.ibm("containers-kubernetes",
                                      f"containers-kubernetes-vpc-{perfil}",
                                      f"part-iks.vpc.{perfil.replace('-', '.')}")
                degraus.append({"sku": f"iks.vpc.{perfil}", "vcpu": v, "ram": r,
                                "usd_hora": tarifa.preco, "tarifa": tarifa})
            self._escadas[("ibm", "iks", None)] = sorted(degraus,
                                                         key=lambda d: (d["vcpu"], d["ram"]))
        return self._escadas[("ibm", "iks", None)]

    def serverless(self, nuvem: str) -> tuple:
        """app-2 na fase 2, com a mitigação N4 (capacidade sempre quente) precificada."""
        s = self.premissas["serverless_fase2"]
        n4 = self.emenda["mitigacao_n4_serverless"]
        invocacoes, duracao_s = s["invocacoes_mes"], s["duracao_media_ms"] / 1000
        memoria_gb = s["memoria_mb"] / 1024
        gb_segundo = invocacoes * duracao_s * memoria_gb
        if nuvem == "ibm":
            combo = n4["combo_code_engine"]
            vcpu_h = self.cat.ibm("codeengine", "standard", "multi-tenant-vCPU-hour", regiao=None)
            gb_h = self.cat.ibm("codeengine", "standard", "multi-tenant-GB-hour", regiao=None)
            chamadas = self.cat.ibm("codeengine", "standard", "multi-tenant-api-call", regiao=None)
            sob_demanda = (vcpu_h.custo(gb_segundo / 3600 * combo["vcpu"] / memoria_gb)
                           + gb_h.custo(gb_segundo / 3600)
                           + chamadas.custo(invocacoes / 1e6))
            quente = n4["instancias_sempre_quentes"] * HORAS_MES * (
                vcpu_h.preco * combo["vcpu"] + gb_h.preco * combo["memoria_gb"])
            return sob_demanda + quente, 0.0, 0.0, "code-engine multi-tenant", vcpu_h.arquivo
        duracao = self.cat.aws_um("AWSLambda", lambda a: a.get("usagetype") ==
                                  "SAE1-Lambda-Provisioned-GB-Second")
        requisicoes = self.cat.aws_um("AWSLambda", lambda a: a.get("usagetype") == "SAE1-Request")
        concorrencia = self.cat.aws_um("AWSLambda", lambda a: a.get("usagetype") ==
                                       "SAE1-Lambda-Provisioned-Concurrency")
        quente = concorrencia.custo(n4["instancias_sempre_quentes"] * memoria_gb * HORAS_MES * 3600)
        total = duracao.custo(gb_segundo) + requisicoes.custo(invocacoes) + quente
        return total, 0.0, 0.0, "lambda concorrência provisionada", duracao.arquivo

    def oracle_ibm(self, servidor: dict, mult: float, caminho: str | None = None) -> dict:
        """D13/emenda 03: os dois caminhos precificados; o primário é o mais barato para a IBM."""
        caminho = (caminho or self.opcoes["oracle_ibm"]
                   or self.emenda["caminho_oracle_ibm"]["primario"])
        if caminho == "bare-metal":
            tarifa = self.cat.ibm("is.bare-metal-server", "mx3-metal-16x128", "part-is.mx3-metal")
            return {"compute": tarifa.preco * HORAS_MES, "sku": "mx3-metal-16x128",
                    "arquivo": tarifa.arquivo}
        vcpu, ram = requisito(servidor, mult)
        degrau = escolher(self.escada(("ibm", "vm", "bxf")), vcpu, ram, "banco-5 Oracle IBM")
        return {"compute": degrau["usd_hora"] * HORAS_MES, "sku": degrau["sku"],
                "arquivo": degrau["tarifa"].arquivo}

    # -- compartilhados ------------------------------------------------------ #
    def backup_objeto(self, nuvem: str, gb: float) -> float:
        """Fase 1: uma cópia completa retida no armazenamento de objetos (emenda 03)."""
        if nuvem == "ibm":
            return self.cat.ibm_provisionamento("ibm-cloud-object-storage-br-sao",
                                                "storage", "standard").custo(gb)
        return self.cat.aws_um("AmazonS3", lambda a: a.get("usagetype") ==
                               "SAE1-TimedStorage-ByteHrs").custo(gb)

    def compartilhados(self, nuvem: str, fase: int) -> dict[str, float]:
        d = self.premissas["dados_e_trafego"]
        objeto_gb = d["objeto_armazenado_tb"] * GB_POR_TB
        egress_objeto = d["egress_objeto_tb_mes"] * GB_POR_TB
        egress_app = d["egress_aplicacao_tb_mes"] * GB_POR_TB
        # três balanceadores na fase 1 (as aplicações que o de-para declara atrás de balanceador);
        # um só na fase 2, que é a entrada do cluster
        n_lb = 3 if fase == 1 else 1

        if nuvem == "ibm":
            objeto = self.cat.ibm_provisionamento("ibm-cloud-object-storage-br-sao",
                                                  "storage", "standard").custo(objeto_gb)
            # duas parcelas com preços DIFERENTES: a mídia sai pelo objeto, a aplicação pelo VPC
            saida = (self.cat.ibm_provisionamento("ibm-cloud-object-storage-br-sao",
                                                  "bandwidth", "standard").custo(egress_objeto)
                     + self.cat.ibm("is.vpc", "nextgen-egress", "is.vpc.egress").custo(egress_app))
            lb = self.cat.ibm("is.load-balancer", "gen2-load-balancer", "service-usage")
            lb_dados = self.cat.ibm("is.load-balancer", "gen2-load-balancer", "data-processed")
            # a HORA é por balanceador; o DADO PROCESSADO é o tráfego total, contado uma vez —
            # multiplicá-lo pelo número de balanceadores cobraria o mesmo terabyte três vezes
            rede = lb.preco * HORAS_MES * n_lb + lb_dados.custo(egress_app)
        else:
            objeto = self.cat.aws_um("AmazonS3", lambda a: a.get("usagetype") ==
                                     "SAE1-TimedStorage-ByteHrs").custo(objeto_gb)
            saida = self.cat.aws_um("AWSDataTransfer", lambda a: a.get("usagetype") ==
                                    "SAE1-DataTransfer-Out-Bytes").custo(egress_objeto + egress_app)
            lb = self.cat.aws_um("AWSELB", lambda a: (a.get("usagetype") == "SAE1-LoadBalancerUsage"
                                                      and a.get("operation") ==
                                                      "LoadBalancing:Application"))
            lcu = self.cat.aws_um("AWSELB", lambda a: (a.get("usagetype") == "SAE1-LCUUsage"
                                                       and a.get("operation") ==
                                                       "LoadBalancing:Application"))
            # uma unidade de capacidade por balanceador e por hora — convenção declarada na
            # emenda 03, já que o consumo real de LCU depende de conexões e regras, que a XYZ
            # fictícia não tem como informar
            rede = (lb.preco + lcu.preco) * HORAS_MES * n_lb

        self._reg(servidor="—", fase=fase, nuvem=nuvem, papel="objeto", sku="armazenamento padrão",
                  vcpu="", ram="", instancias=1, usd_mes=objeto, arquivo_fonte="ver trilha")
        self._reg(servidor="—", fase=fase, nuvem=nuvem, papel="egress", sku="saída para internet",
                  vcpu="", ram="", instancias=1, usd_mes=saida, arquivo_fonte="ver trilha")
        self._reg(servidor="—", fase=fase, nuvem=nuvem, papel="rede", sku="balanceador",
                  vcpu="", ram="", instancias=3 if fase == 1 else 1, usd_mes=rede,
                  arquivo_fonte="ver trilha")
        fora = {"objeto": objeto, "egress": saida, "rede-ip-balanceador": rede,
                "suporte": 0.0, "observabilidade": 0.0, "licencas": 0.0}
        if fase == 2:
            # Plano de controle do cluster: UM por ambiente, não um por aplicação. O do EKS é
            # cobrado por hora; o do IKS não expõe métrica com preço (medido em 2026-08-13).
            # A assimetria é refletida, não normalizada — e cai em `premio-gerenciado`, que é
            # exatamente o que ela é: o preço de o provedor operar o orquestrador.
            controle = (0.0 if nuvem == "ibm" else
                        self.cat.aws_um("AmazonEKS", lambda a: a.get("usagetype") ==
                                        "SAE1-AmazonEKS-Hours:perCluster").preco * HORAS_MES)
            fora["premio-gerenciado"] = controle
            self._reg(servidor="—", fase=2, nuvem=nuvem, papel="premio-gerenciado",
                      sku="plano de controle do cluster", vcpu="", ram="", instancias=1,
                      usd_mes=controle, arquivo_fonte="ver trilha")
        return fora

    def custo_ia(self, nuvem: str, tokens_mes: float) -> float:
        """Camada de IA no modelo pareado (emenda 03): mesmo identificador nos dois catálogos."""
        razao = self.emenda["camada_ia"]["razao_entrada_saida"]
        entrada = tokens_mes * razao / (1 + razao)
        saida = tokens_mes - entrada
        modelo = self.emenda["camada_ia"]["pareamento_de_modelo"]["primario"]["modelo"]
        if nuvem == "ibm":
            # a página põe entrada na linha do modelo e saída na linha seguinte (ver `ibm_pagina`)
            p_in = self.cat.ibm_pagina("ibm-watsonx-ai", modelo)
            p_out = self.cat.ibm_pagina("ibm-watsonx-ai", modelo, deslocamento=1)
            return (entrada * p_in.preco + saida * p_out.preco) / 1e6      # IBM cobra por 1M
        p_in = self.cat.aws_um("AmazonBedrock", lambda a: a.get("usagetype") ==
                               f"SAE1-{modelo}-input-tokens")
        p_out = self.cat.aws_um("AmazonBedrock", lambda a: a.get("usagetype") ==
                                f"SAE1-{modelo}-output-tokens")
        return (entrada / 1000 * p_in.preco) + (saida / 1000 * p_out.preco)   # AWS cobra por 1K


# --------------------------------------------------------------------------- #
# agregação                                                                    #
# --------------------------------------------------------------------------- #
def custo_mensal(modelo: Modelo, nuvem: str, fase: int, mult: float,
                 tokens_mes: float | None = None) -> dict[str, float]:
    """Custo do primeiro mês, por item da taxonomia."""
    total = {item: 0.0 for item in TAXONOMIA}
    for servidor in modelo.caso["servidores"]:
        dp = next(d for d in modelo.projeto["de_para"] if d["id"] == servidor["id"])
        alvo = dp[f"fase{fase}_{nuvem}"]
        parcelas = (modelo.fase1(nuvem, servidor, alvo, mult) if fase == 1
                    else modelo.fase2(nuvem, servidor, alvo, mult))
        for item, valor in parcelas.items():
            total[item] = total.get(item, 0.0) + valor
        if fase == 1 and servidor["categoria"] == "banco":
            # uma cópia completa retida no armazenamento de objetos (emenda 03)
            total["backup"] += modelo.backup_objeto(nuvem, servidor["armazenamento_gb"])
    for item, valor in modelo.compartilhados(nuvem, fase).items():
        total[item] = total.get(item, 0.0) + valor
    if fase == 2:
        tokens = tokens_mes if tokens_mes is not None else \
            modelo.emenda["camada_ia"]["ponto_ilustrativo_tokens_mes"]
        total["ia"] = modelo.custo_ia(nuvem, tokens)
    return total


def tco_36m(mensal: dict[str, float], premissas: dict) -> dict[str, float]:
    """36 meses. Objeto e bloco crescem de forma composta; o resto é constante (emenda 03)."""
    d = premissas["dados_e_trafego"]
    crescimento = {"objeto": d["objeto_crescimento_mes_pct"] / 100,
                   "bloco": d["bloco_crescimento_mes_pct"] / 100}
    fora = {}
    for item, valor in mensal.items():
        g = crescimento.get(item, 0.0)
        fora[item] = (valor * MESES if g == 0
                      else valor * ((1 + g) ** MESES - 1) / g)
    return fora


def cenario(cfg: dict, nuvem: str, fase: int, mult: float, tokens_mes: float | None = None,
            opcoes: dict | None = None) -> dict:
    modelo = Modelo(cfg, opcoes)
    mensal = custo_mensal(modelo, nuvem, fase, mult, tokens_mes)
    total = tco_36m(mensal, cfg["premissas"])
    return {"nuvem": nuvem, "fase": fase, "multiplicador": mult, "mensal": mensal,
            "tco": total, "total_36m": sum(total.values()), "detalhe": modelo.detalhe,
            "catalogo": modelo.cat}


def ranking(tco: dict[str, float]) -> list[str]:
    """Itens de custo em ordem decrescente — o ranking que a condição de quebra compara."""
    return [item for item, valor in sorted(tco.items(), key=lambda kv: -kv[1]) if valor > 0]


# --------------------------------------------------------------------------- #
# grade, ponto de virada e veredito da tese                                   #
# --------------------------------------------------------------------------- #
def grade(cfg: dict) -> dict:
    """Toda a grade pré-registrada de multiplicadores, nas duas nuvens e nas duas fases."""
    multiplicadores = cfg["premissas"]["grade_sensibilidade"]["multiplicador_headroom"]
    linhas, por_chave = [], {}
    for fase in (1, 2):
        for mult in multiplicadores:
            for nuvem in ("ibm", "aws"):
                c = cenario(cfg, nuvem, fase, mult)
                por_chave[(fase, mult, nuvem)] = c
            ibm, aws = por_chave[(fase, mult, "ibm")], por_chave[(fase, mult, "aws")]
            linhas.append({"fase": fase, "multiplicador": mult,
                           "tco_ibm_36m": ibm["total_36m"], "tco_aws_36m": aws["total_36m"],
                           "delta_usd": ibm["total_36m"] - aws["total_36m"],
                           "delta_pct_sobre_menor": (abs(ibm["total_36m"] - aws["total_36m"])
                                                     / min(ibm["total_36m"], aws["total_36m"]) * 100),
                           "vencedor": "ibm" if ibm["total_36m"] < aws["total_36m"] else "aws"})
    return {"linhas": linhas, "cenarios": por_chave}


def ponto_de_virada(linhas: list[dict], fase: int) -> dict:
    """Menor multiplicador em que o vencedor muda em relação ao dimensionamento por especificação."""
    da_fase = sorted((l for l in linhas if l["fase"] == fase), key=lambda l: l["multiplicador"])
    base = da_fase[0]["vencedor"]
    for linha in da_fase[1:]:
        if linha["vencedor"] != base:
            return {"fase": fase, "existe": True, "multiplicador": linha["multiplicador"],
                    "de": base, "para": linha["vencedor"]}
    return {"fase": fase, "existe": False, "multiplicador": None, "de": base, "para": base,
            "_leitura": "nenhuma virada dentro da grade pré-registrada — resultado reportável, "
                        "não ausência de resultado: a escada de perfis é discreta e o cruzamento "
                        "pode não existir no intervalo declarado"}


def virada_extrapolada(cfg: dict, passo: float = 0.05, teto: float = 6.0) -> list[dict]:
    """Onde o veredito viraria FORA da grade pré-registrada — declarado como extrapolação.

    A grade selada vai até três vezes a capacidade e nela não há virada; parar aí deixaria a
    pergunta mais interessante sem resposta. Esta varredura continua até a escada capturada
    acabar, e é a própria escada que impõe o limite: quando nenhum degrau atende ao requisito,
    o modelo levanta erro em vez de improvisar, e o limite entra no relatório como achado de
    catálogo. Nada daqui entra na condição de quebra — ela vale sobre a grade, e só.
    """
    fora = []
    for fase in (1, 2):
        base, mult, ultimo = None, 1.0, None
        while mult <= teto + 1e-9:
            try:
                tcos = {n: cenario(cfg, n, fase, mult)["total_36m"] for n in ("ibm", "aws")}
            except LookupError as e:
                fora.append({"fase": fase, "virada": "não alcançada", "multiplicador": ultimo,
                             "limite": "escada capturada esgotada", "detalhe": str(e)[:160]})
                break
            vencedor = "ibm" if tcos["ibm"] < tcos["aws"] else "aws"
            base = base or vencedor
            if vencedor != base:
                fora.append({"fase": fase, "virada": "sim", "multiplicador": round(mult, 2),
                             "limite": f"{base} -> {vencedor}",
                             "detalhe": f"IBM {tcos['ibm']:,.2f} contra AWS {tcos['aws']:,.2f}"})
                break
            ultimo, mult = round(mult, 2), mult + passo
        else:
            fora.append({"fase": fase, "virada": "não alcançada", "multiplicador": ultimo,
                         "limite": f"teto da varredura ({teto:g})", "detalhe": f"vencedor {base}"})
    return fora


def veredito_tese(cfg: dict, g: dict) -> dict:
    """Condição de quebra do pré-registro §2, computada — nunca redigida.

    'Refutada se, PARA TODA A GRADE, o delta entre os dois métodos for < 10% do custo total de 36
    meses NAS DUAS NUVENS e o ranking dos itens permanecer idêntico em todos os pontos.'
    """
    limiar, deltas, rankings, violacoes = 10.0, [], [], []
    for fase in (1, 2):
        base = {n: g["cenarios"][(fase, 1.0, n)] for n in ("ibm", "aws")}
        ranking_base = {n: ranking(base[n]["tco"]) for n in base}
        for mult in cfg["premissas"]["grade_sensibilidade"]["multiplicador_headroom"]:
            if mult == 1.0:
                continue
            for nuvem in ("ibm", "aws"):
                c = g["cenarios"][(fase, mult, nuvem)]
                delta = (c["total_36m"] - base[nuvem]["total_36m"]) / base[nuvem]["total_36m"] * 100
                deltas.append({"fase": fase, "multiplicador": mult, "nuvem": nuvem,
                               "delta_pct_entre_metodos": delta})
                mesmo_ranking = ranking(c["tco"]) == ranking_base[nuvem]
                rankings.append({"fase": fase, "multiplicador": mult, "nuvem": nuvem,
                                 "ranking_identico": mesmo_ranking})
                if delta >= limiar or not mesmo_ranking:
                    violacoes.append({"fase": fase, "multiplicador": mult, "nuvem": nuvem,
                                      "delta_pct": delta, "ranking_identico": mesmo_ranking})
    refutada = not violacoes
    return {"refutada": refutada, "limiar_pct": limiar, "deltas": deltas, "rankings": rankings,
            "violacoes": violacoes,
            "veredito": "TESE REFUTADA" if refutada else "TESE NÃO REFUTADA",
            "_criterio": "delta entre métodos < 10% nas DUAS nuvens E ranking idêntico, "
                         "em TODOS os pontos da grade (pré-registro §2)"}


def sensibilidades(cfg: dict) -> list[dict]:
    """Os cenários nomeados ANTES de capturar (pré-registro §5 e emenda 03), cada um contra o
    primário. Nenhum deles substitui o primário: existem para mostrar o quanto o veredito depende
    de convenção, que é literalmente a tese."""
    base = {(f, n): cenario(cfg, n, f, 1.0)["total_36m"] for f in (1, 2) for n in ("ibm", "aws")}
    linhas = [{"cenario": "primario", "nuvem": n, "fase": f, "tco_36m": v,
               "delta_vs_primario_pct": 0.0, "observacao": "convenção do pré-registro"}
              for (f, n), v in base.items()]

    def juntar(nome: str, nuvem: str, fases: tuple, opcoes: dict, obs: str) -> None:
        for f in fases:
            v = cenario(cfg, nuvem, f, 1.0, opcoes=opcoes)["total_36m"]
            linhas.append({"cenario": nome, "nuvem": nuvem, "fase": f, "tco_36m": v,
                           "delta_vs_primario_pct": (v - base[(f, nuvem)]) / base[(f, nuvem)] * 100,
                           "observacao": obs})

    juntar("oracle-ibm-bare-metal", "ibm", (1, 2), {"oracle_ibm": "bare-metal"},
           "D13: o menor bare metal de br-sao tem 16 núcleos, o dobro do requisito do banco-5")
    juntar("oracle-aws-licenca-inclusa", "aws", (2,), {"oracle_aws_licenca": "inclusa"},
           "só existe na edição Standard Two da AWS; não há equivalente na IBM")
    juntar("graviton-aws", "aws", (1, 2), {"arm": True},
           "ARM admitido do lado AWS, sem contrapartida no catálogo IBM de br-sao")
    for nuvem in ("ibm", "aws"):
        juntar("banco-1-disco-uso-geral", nuvem, (1, 2), {"disco_banco_1_uso_geral": True},
               "achado externo: a linha de base do banco-1 declara alta disponibilidade, não "
               "desempenho de disco; aqui ele recebe o degrau de uso geral nas DUAS nuvens")
    return linhas


def sensibilidade_ia(cfg: dict) -> list[dict]:
    """Veredito em cada ponto da grade de volume de IA — a premissa que a emenda 03 acrescentou."""
    fora = []
    for tokens in cfg["emenda"]["camada_ia"]["grade_tokens_mes"]:
        c = {n: cenario(cfg, n, 2, 1.0, tokens) for n in ("ibm", "aws")}
        fora.append({"tokens_mes": tokens,
                     "ia_ibm_usd_mes": c["ibm"]["mensal"]["ia"],
                     "ia_aws_usd_mes": c["aws"]["mensal"]["ia"],
                     "tco_ibm_36m": c["ibm"]["total_36m"], "tco_aws_36m": c["aws"]["total_36m"],
                     "vencedor": "ibm" if c["ibm"]["total_36m"] < c["aws"]["total_36m"] else "aws"})
    return fora


# --------------------------------------------------------------------------- #
# saída                                                                        #
# --------------------------------------------------------------------------- #
def _escrever(destino: Path, linhas: list[dict]) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(linhas[0]))
        escritor.writeheader()
        for linha in linhas:
            escritor.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v)
                               for k, v in linha.items()})
    return destino


def executar(raiz: Path = RAIZ, escrever: bool = True) -> dict:
    cfg = carregar(raiz)
    g = grade(cfg)
    tese = veredito_tese(cfg, g)
    ia = sensibilidade_ia(cfg)
    viradas = [ponto_de_virada(g["linhas"], fase) for fase in (1, 2)]

    # cenários do ponto de operação (multiplicador 1,0): é o que vai às tabelas do corpo
    base = {(f, n): g["cenarios"][(f, 1.0, n)] for f in (1, 2) for n in ("ibm", "aws")}
    por_item = [{"configuracao": {(1, "ibm"): "C1", (1, "aws"): "C2",
                                  (2, "ibm"): "C3", (2, "aws"): "C4"}[(f, n)],
                 "nuvem": n, "fase": f, "item_custo": item,
                 "usd_mes_1": base[(f, n)]["mensal"].get(item, 0.0),
                 "usd_36m": base[(f, n)]["tco"].get(item, 0.0)}
                for (f, n) in base for item in list(TAXONOMIA) + ["ia"]]
    resumo = [{"configuracao": {(1, "ibm"): "C1", (1, "aws"): "C2",
                                (2, "ibm"): "C3", (2, "aws"): "C4"}[(f, n)],
               "nuvem": n, "fase": f, "metodo": "iso-especificacao", "multiplicador": 1.0,
               "total_36m_usd": base[(f, n)]["total_36m"]}
              for (f, n) in base]
    resumo += [{"configuracao": {(1, "ibm"): "C1", (1, "aws"): "C2",
                                 (2, "ibm"): "C3", (2, "aws"): "C4"}[(l["fase"], n)],
                "nuvem": n, "fase": l["fase"], "metodo": "iso-sla",
                "multiplicador": l["multiplicador"],
                "total_36m_usd": l[f"tco_{n}_36m"]}
               for l in g["linhas"] if l["multiplicador"] != 1.0 for n in ("ibm", "aws")]

    # o mesmo detalhamento por item, agora em TODA a grade pré-registrada. A figura de TCO
    # empilhado é cobrada "duas nuvens x dois métodos", e o método iso-SLA não tem por-item no
    # CSV acima, que congela o multiplicador 1,0. Emite-se a grade inteira de propósito: este
    # módulo não sabe — e não pode saber — qual multiplicador é o ponto de operação iso-SLA, que
    # é derivado do modelo de fila em `filas.py`. Saber aqui criaria a dependência que a
    # afirmação de invariância do cabeçalho nega.
    por_item_grade = [{"configuracao": CONFIG_ID[(f, n)], "nuvem": n, "fase": f,
                       "metodo": "iso-especificacao" if mult == 1.0 else "iso-sla",
                       "multiplicador": mult, "item_custo": item,
                       "usd_mes_1": g["cenarios"][(f, mult, n)]["mensal"].get(item, 0.0),
                       "usd_36m": g["cenarios"][(f, mult, n)]["tco"].get(item, 0.0)}
                      for (f, mult, n) in sorted(g["cenarios"])
                      for item in list(TAXONOMIA) + ["ia"]]

    detalhe = [d for (f, n) in base for d in base[(f, n)]["detalhe"]]
    trilha = base[(1, "ibm")]["catalogo"].trilha_csv()
    for chave in base.values():
        for linha in chave["catalogo"].trilha_csv():
            if linha not in trilha:
                trilha.append(linha)

    # decomposição da diferença entre as nuvens, por item — o MECANISMO, computado.
    # O corpo afirma qual item produz a diferença; até a v1.5.0 essa afirmação repousava numa
    # leitura da figura empilhada. Emiti-la como CSV é o que permite ao gate G-05 casar o
    # percentual do texto com um número selado, em vez de deixá-lo passar por coincidência.
    decomposicao = []
    for f in (1, 2):
        gap = base[(f, "ibm")]["total_36m"] - base[(f, "aws")]["total_36m"]
        for item in list(TAXONOMIA) + ["ia"]:
            d = base[(f, "ibm")]["tco"].get(item, 0.0) - base[(f, "aws")]["tco"].get(item, 0.0)
            decomposicao.append({"fase": f, "item_custo": item, "delta_usd_36m": d,
                                 "pct_do_gap": d / gap * 100 if gap else 0.0})

    saidas = {
        "tco-resumo.csv": resumo,
        "decomposicao-do-gap.csv": decomposicao,
        "tco-por-item.csv": por_item,
        "tco-por-item-grade.csv": por_item_grade,
        "dimensionamento.csv": detalhe,
        "ponto-de-virada.csv": g["linhas"],
        "virada-sintese.csv": viradas,
        "virada-extrapolada.csv": virada_extrapolada(cfg),
        "sensibilidade-ia.csv": ia,
        "sensibilidade-cenarios.csv": sensibilidades(cfg),
        "tese-veredito.csv": [{"veredito": tese["veredito"], "criterio": tese["_criterio"],
                               "violacoes": len(tese["violacoes"]),
                               "pontos_avaliados": len(tese["deltas"])}],
        "tese-grade-deltas.csv": [d | {"ranking_identico": r["ranking_identico"]}
                                  for d, r in zip(tese["deltas"], tese["rankings"])],
        "precos-unitarios.csv": trilha,
    }
    if escrever:
        for nome, linhas in saidas.items():
            _escrever(raiz / "output" / "tabelas" / nome, linhas)
    return {"grade": g, "tese": tese, "ia": ia, "viradas": viradas, "base": base,
            "saidas": saidas}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Modelo de TCO do estudo de caso.")
    ap.add_argument("--root", type=Path, default=RAIZ)
    ap.add_argument("--resumo", action="store_true", help="imprime sem escrever os CSV")
    args = ap.parse_args(argv)

    r = executar(args.root, escrever=not args.resumo)
    print(f"{'config':8} {'nuvem':5} {'fase':4} {'TCO 36m (USD)':>16}")
    for (f, n), c in sorted(r["base"].items()):
        print(f"{'C' + str((f - 1) * 2 + (1 if n == 'ibm' else 2)):8} {n:5} {f:<4} "
              f"{c['total_36m']:>16,.2f}")
    for v in r["viradas"]:
        print(f"[virada fase {v['fase']}] " + ("multiplicador "
              f"{v['multiplicador']} ({v['de']} -> {v['para']})" if v["existe"]
              else f"nenhuma na grade; vencedor {v['de']} em todos os pontos"))
    print(f"[tese] {r['tese']['veredito']} — {len(r['tese']['violacoes'])} violações em "
          f"{len(r['tese']['deltas'])} pontos avaliados")
    if not args.resumo:
        print(f"[csv] {args.root / 'output' / 'tabelas'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
