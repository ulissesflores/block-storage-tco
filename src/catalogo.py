#!/usr/bin/env python3
"""Leitura normalizada dos preços JÁ capturados em disco — a única porta por onde um número
entra no modelo de custo.

Piso do projeto: **número sem probe não entra**. `capture_prices.py` garante isso na gravação;
este módulo garante na leitura. Nada aqui busca rede, nada aqui aceita valor digitado: toda
tarifa devolvida vem de um arquivo em `data/precos/`, e o caminho desse arquivo viaja junto com
o número até o CSV final (`precos-unitarios.csv`), que é o rastro do Apêndice A.

Três formas de tarifa convivem, porque os dois catálogos são diferentes:

- **IBM catálogo global** (`precos_no_pais`): `metric_id -> faixas [(quantidade_até, preço)]`,
  país USA (D12). A busca de métrica é por substring porque o identificador carrega o perfil
  (`part-is.instance-hours-bxf-4x16`).
- **IBM tela de provisionamento** (Object Storage): `prices[grupo][classe] -> [{price, ...}]`.
- **AWS offer file**: `products[sku].attributes` + `terms.OnDemand[sku][…].priceDimensions`, com
  faixa em `beginRange`/`endRange`.

Fail-closed em toda leitura: métrica ausente, produto sem correspondência ou tarifa zerada
levantam `LookupError` — o modelo para em vez de somar zero em silêncio. Foi exatamente o zero
silencioso do `/pricing` do plano que o validador nº 2 pegou na captura; a mesma armadilha existe
na leitura.

UNIDADE DOS BANCOS GERENCIADOS DA IBM (achado desta etapa, travado por teste): a métrica de host
(`databases-for-mysql-4-16`) declara `charge_unit: "Instance-Hour"`, mas a unidade real é **mês**.
Três provas independentes, todas computáveis dos corpos crus e verificadas em `test_tco.py`:
(i) `charge_unit_name` é `HOST_FOUR_SIXTEEN`, e as métricas que a compõem são `GIGABYTE_MONTHS_*`;
(ii) a razão entre o plano regional `standard` e o não-regional `standard-gen2` (esse sim por hora)
é da ordem de 730 — o número de horas de um mês; (iii) a decomposição `cpu × vCPU + ram × GB` bate
com a métrica de host em MySQL, PostgreSQL e MongoDB (Redis diverge ~5%, declarado). Ler essa
métrica como horária inflaria o lado IBM em 730 vezes e destruiria o veredito.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import capture_prices as cp   # noqa: E402

HORAS_MES = 730.0             # paridade comercial: horizonte declarado em projeto-tecnico.json
INFINITO = float("inf")


@dataclass(frozen=True)
class Tarifa:
    """Uma tarifa lida do disco, com a procedência colada nela."""
    provedor: str
    recurso: str                       # rótulo legível (SKU, métrica, usagetype)
    unidade: str
    faixas: tuple[tuple[float, float], ...]   # ((quantidade_até, preço), …) crescente
    regiao: str
    classe_evidencia: str              # api-versionada | pagina-publica
    arquivo: str                       # caminho relativo ao repo — o rastro
    atributos: dict = field(default_factory=dict, compare=False)

    @property
    def preco(self) -> float:
        """Preço da primeira faixa — o único válido quando a quantidade não cruza degrau."""
        return self.faixas[0][1]

    def custo(self, quantidade: float) -> float:
        """Custo graduado: cada faixa cobra apenas a parcela que cai dentro dela.

        O rótulo capturado da IBM é "Graduated Tier (Step Tier)" e as duas leituras divergem
        acima do primeiro degrau. Todas as quantidades deste trabalho ficam abaixo do primeiro
        degrau de toda tarifa graduada usada (6 TB de saída contra teto de 10.000 GB), então as
        duas leituras coincidem — e `test_tco.py` trava esse fato para que uma mudança de
        volumetria não atravesse a ambiguidade em silêncio.
        """
        restante, total, piso = quantidade, 0.0, 0.0
        for teto, preco in self.faixas:
            faixa = min(restante, (teto if teto is not None else INFINITO) - piso)
            if faixa > 0:
                total += faixa * preco
                restante -= faixa
            piso = teto if teto is not None else INFINITO
            if restante <= 0:
                break
        if restante > 0:                                  # última faixa é o teto declarado
            total += restante * self.faixas[-1][1]
        return total


def _faixas_ibm(faixas: Iterable) -> tuple[tuple[float, float], ...]:
    ordenadas = sorted(((float(q), float(p)) for q, p in faixas), key=lambda x: x[0])
    return tuple(ordenadas) or ((1.0, 0.0),)


def _faixas_aws(dimensoes: list[dict]) -> tuple[tuple[float, float], ...]:
    def teto(d: dict) -> float:
        fim = d.get("endRange")
        return INFINITO if fim in (None, "Inf") else float(fim)
    return tuple(sorted(((teto(d), float(d["pricePerUnit"]["USD"])) for d in dimensoes),
                        key=lambda x: x[0]))


class Catalogo:
    """Índice, em memória, de tudo que foi capturado — construído a partir do disco."""

    def __init__(self, raiz: Path = RAIZ) -> None:
        self.raiz = Path(raiz)
        self.trilha: list[Tarifa] = []          # toda tarifa efetivamente usada pelo modelo
        self._arquivos: dict[str, dict] = {}
        for arq in sorted((self.raiz / cp.DIR_PRECOS).rglob("*.json")):
            registro = json.loads(arq.read_text(encoding="utf-8"))
            chave = arq.name.rsplit("-", 3)[0]   # tira o sufixo -AAAA-MM-DD
            registro["_arquivo"] = str(arq.relative_to(self.raiz))
            self._arquivos[chave] = registro

    # ------------------------------------------------------------------ #
    # IBM — catálogo global                                              #
    # ------------------------------------------------------------------ #
    def _registro(self, chave: str) -> dict:
        try:
            return self._arquivos[chave]
        except KeyError:
            raise LookupError(f"captura ausente em disco: {chave!r}. Rode "
                              f"`python3 src/run_capture.py` ou declare o item como limitação.")

    def ibm(self, servico: str, plano: str, metrica: str, regiao: str | None = "br-sao") -> Tarifa:
        """Tarifa de uma métrica do catálogo global. `metrica` casa por substring do metric_id."""
        sufixo = f"-{regiao}" if regiao else "-nao-regional"
        registro = self._registro(f"ibm-{servico}-{plano}{sufixo}")
        candidatas = {mid: v for mid, v in registro["precos_no_pais"].items() if metrica in mid
                      and any(p for _, p in v["faixas"])}
        if not candidatas:
            raise LookupError(f"ibm {servico}/{plano}@{regiao}: nenhuma métrica com preço casa "
                              f"{metrica!r} (candidatas: {sorted(registro['precos_no_pais'])[:6]}…)")
        mid = min(candidatas, key=len)            # o mais específico é o de nome mais curto
        v = candidatas[mid]
        return self._anotar(Tarifa("ibm", mid, v["charge_unit"], _faixas_ibm(v["faixas"]),
                                   regiao or "não-regional (declarado)", "api-versionada",
                                   registro["_arquivo"], {"tier_model": v.get("tier_model")}))

    def metricas_ibm(self, servico: str, plano: str, regiao: str | None = "br-sao") -> dict:
        """`{metric_id: faixas}` de uma captura da IBM — a escada inteira, para o modelo escolher.

        Existe porque a regra de seleção selada precifica a ESCADA e deriva o SKU da evidência;
        quem enumera degrau é o modelo, não a leitura.
        """
        sufixo = f"-{regiao}" if regiao else "-nao-regional"
        return self._registro(f"ibm-{servico}-{plano}{sufixo}")["precos_no_pais"]

    def ibm_provisionamento(self, servico: str, grupo: str, classe: str) -> Tarifa:
        """Tarifa da API que a tela de provisionamento consome (Object Storage por classe/faixa)."""
        registro = self._registro(servico)
        try:
            faixas = registro["conteudo"]["prices"][grupo][classe]
        except KeyError as e:
            raise LookupError(f"{servico}: grupo/classe {grupo}/{classe} ausente") from e
        pares = tuple(sorted(((float(f.get("quantity_tier") or INFINITO), float(f["price"]))
                              for f in faixas), key=lambda x: x[0]))
        if not any(p for _, p in pares):
            raise LookupError(f"{servico}: {grupo}/{classe} veio zerado")
        return self._anotar(Tarifa("ibm", f"{grupo}.{classe}", faixas[0].get("unit", ""), pares,
                                   registro.get("_regiao", "br-sao"), "api-versionada",
                                   registro["_arquivo"]))

    def ibm_pagina(self, servico: str, contem: str, deslocamento: int = 0) -> Tarifa:
        """Segunda classe de evidência (D14): item extraído por regra do HTML salvo.

        `deslocamento` existe pela forma da página de preços do watsonx.ai: a tabela de modelos
        põe o preço de ENTRADA na linha do modelo e o de SAÍDA na linha seguinte, e o extrator
        preserva essa ordem. Endereçar a saída por posição relativa ao modelo é mais estável do
        que casar o texto do próprio preço — que mudaria junto com o preço.
        """
        itens = self._registro(servico)["conteudo"]["itens"]
        casados = [k for k, i in enumerate(itens) if contem.lower() in i["rotulo"].lower()]
        if not casados:
            raise LookupError(f"{servico}: nenhum item de página casa {contem!r}")
        alvo = casados[0] + deslocamento
        if not 0 <= alvo < len(itens):
            raise LookupError(f"{servico}: {contem!r}+{deslocamento} cai fora da tabela extraída")
        i = itens[alvo]
        return self._anotar(Tarifa("ibm", i["rotulo"][:70], i.get("unidade") or "—",
                                   ((INFINITO, float(i["usd"])),), "não-regional (declarado)",
                                   "pagina-publica", self._registro(servico)["_arquivo"]))

    # ------------------------------------------------------------------ #
    # AWS — offer file                                                   #
    # ------------------------------------------------------------------ #
    def aws_produtos(self, servico: str, filtro: Callable[[dict], bool],
                     regiao: str = "sa-east-1") -> list[tuple[dict, Tarifa]]:
        """`[(attributes, tarifa), …]` da fatia capturada que satisfaz `filtro`."""
        registro = self._registro(f"aws-{servico}-{regiao}")
        conteudo = registro["conteudo"]
        fora: list[tuple[dict, Tarifa]] = []
        for sku, produto in conteudo["products"].items():
            atributos = produto.get("attributes", {})
            if not filtro(atributos):
                continue
            dimensoes = [d for termo in conteudo["terms"].get("OnDemand", {}).get(sku, {}).values()
                         for d in termo["priceDimensions"].values()]
            if not dimensoes:
                continue
            faixas = _faixas_aws(dimensoes)
            unidade = dimensoes[0]["unit"]
            fora.append((atributos, Tarifa("aws", atributos.get("usagetype") or sku, unidade,
                                           faixas, regiao, "api-versionada", registro["_arquivo"],
                                           {"sku": sku, **atributos})))
        if not fora:
            raise LookupError(f"aws {servico}@{regiao}: filtro não casou produto na fatia "
                              f"({len(conteudo['products'])} capturados)")
        return fora

    def aws_um(self, servico: str, filtro: Callable[[dict], bool],
               regiao: str = "sa-east-1") -> Tarifa:
        """Produto único (uso, hora de cluster, requisição). Ambiguidade é erro, não escolha."""
        achados = self.aws_produtos(servico, filtro, regiao)
        precos = {a.faixas for _, a in achados}
        if len(precos) > 1:
            raise LookupError(f"aws {servico}: filtro casou {len(achados)} produtos com preços "
                              f"diferentes — refine o filtro em vez de escolher em silêncio")
        return self._anotar(achados[0][1])

    # ------------------------------------------------------------------ #
    def _anotar(self, tarifa: Tarifa) -> Tarifa:
        if tarifa not in self.trilha:
            self.trilha.append(tarifa)
        return tarifa

    def trilha_csv(self) -> list[dict]:
        return [{"provedor": t.provedor, "recurso": t.recurso, "unidade": t.unidade,
                 "preco_1a_faixa_usd": f"{t.preco:.10g}",
                 "faixas": " | ".join(f"até {'∞' if q == INFINITO else f'{q:g}'}: {p:.10g}"
                                      for q, p in t.faixas),
                 "regiao_do_preco": t.regiao, "classe_evidencia": t.classe_evidencia,
                 "arquivo_fonte": t.arquivo}
                for t in sorted(self.trilha, key=lambda t: (t.provedor, t.recurso))]
