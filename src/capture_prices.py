#!/usr/bin/env python3
"""Captura de preços públicos por DUAS vias, com o corpo cru salvo em disco.

Piso do projeto: **número sem probe não entra no paper**. Este módulo torna mecanicamente
impossível um preço entrar sem procedência — toda gravação exige URL exata, timestamp UTC,
código HTTP, tamanho em bytes e a via; faltando qualquer um, levanta erro antes de escrever.

Via (a) API      — catálogo global da IBM e Price List da AWS (offer file da região).
Via (b) MANUAL   — estimador público, para o que a IBM não expõe por API (Object Storage,
                   egress, watsonx). Exige arquivo de evidência existente em disco.

Saída: `data/precos/<via>/<servico>-<AAAA-MM-DD>.json`.

Só `urllib` da biblioteca padrão — nenhuma dependência nova.

TRÊS SALTOS NA IBM (medido em 2026-08-13, laudo do validador nº 2 §1):
o preço de uma instância **não está** no `/pricing` do plano — a métrica existe e vale
**zero**, sem erro. O caminho real é `serviço -> plano -> deployment da região -> pricing`.
Um capturador de um salto colheria zeros e ninguém notaria. Daí duas defesas aqui:
`capturar_ibm` percorre os três saltos quando `regiao` é dada, e `exigir_metricas` levanta
erro se a métrica que sustenta a linha de custo vier ausente ou zerada. Serviço que a IBM
precifica sem região (Code Engine, Object Storage, bancos gerenciados) usa `regiao=None`,
que é declaração explícita de não-regionalidade, não omissão.

MOEDA E PAÍS (D12): `amounts[]` é por país/moeda — o mesmo SKU sai USD 0,626 e BRL 3,4743.
Toda captura declara `pais` e falha se aquele país não constar; sem isso a planilha somaria
real com dólar e passaria em todos os gates.

NOTA (escolha onde a spec é omissa): o offer file da AWS por região tem centenas de MB. Ele é
baixado por STREAMING para um arquivo temporário — hash e bytes computados no fluxo — e depois
lido para extrair apenas a fatia consultada. O temporário é apagado; em disco fica a fatia
filtrada mais o SHA-256 do arquivo completo, que é o que prova a procedência sem versionar
centenas de MB. `filtro` é parâmetro obrigatório justamente para forçar a declaração de qual
fatia foi consultada.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

RAIZ = Path(__file__).resolve().parent.parent
DIR_PRECOS = "data/precos"

IBM_BASE = "https://globalcatalog.cloud.ibm.com/api/v1/"
AWS_HOST = "https://pricing.us-east-1.amazonaws.com"
AWS_REGION_INDEX = AWS_HOST + "/offers/v1.0/aws/{servico}/current/region_index.json"

USER_AGENT = "cloud-price-capture/2.0 (pesquisa academica; stdlib urllib)"
TIMEOUT_S = 90
PAIS_PADRAO = "USA"          # D12: país e moeda únicos nas duas nuvens

# Campos sem os quais uma captura NÃO pode ser gravada. `http_status` é exigido como CHAVE
# sempre; na via manual não há transação HTTP e o valor é None por design.
META_OBRIGATORIA = ("url", "timestamp_utc", "http_status", "bytes", "via")


# --------------------------------------------------------------------------- #
# gravação com procedência obrigatória                                        #
# --------------------------------------------------------------------------- #
def _agora_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validar_meta(meta: dict) -> None:
    faltando = [k for k in META_OBRIGATORIA if k not in meta]
    if faltando:
        raise ValueError(f"captura sem procedência: faltam os campos {faltando}")
    for k in ("url", "timestamp_utc", "via"):
        if not str(meta[k] or "").strip():
            raise ValueError(f"captura sem procedência: campo {k!r} vazio")
    if meta["via"] == "api" and not isinstance(meta["http_status"], int):
        raise ValueError("captura via API sem código HTTP inteiro")
    if not isinstance(meta["bytes"], int) or meta["bytes"] < 0:
        raise ValueError("captura sem tamanho em bytes válido")


def salvar_captura(via: str, servico: str, meta: dict, conteudo, raiz: Path = RAIZ) -> Path:
    """Grava o corpo cru + procedência. Levanta ValueError antes de escrever se faltar campo."""
    _validar_meta(meta)
    destino = Path(raiz) / DIR_PRECOS / via / f"{servico}-{datetime.now(timezone.utc):%Y-%m-%d}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    registro = {"_natureza": "coletado", "servico": servico, **meta, "conteudo": conteudo}
    destino.write_text(json.dumps(registro, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return destino


# --------------------------------------------------------------------------- #
# leitura de preço já capturado (usada pelo modelo e pelos testes)             #
# --------------------------------------------------------------------------- #
def precos_por_pais(pricing: dict, pais: str = PAIS_PADRAO) -> dict[str, dict]:
    """`{metric_id: {"moeda":…, "faixas":[(quantidade_ate, preco), …]}}` para um país.

    Métrica sem `amounts` daquele país simplesmente não aparece — quem exige presença é
    `exigir_metricas`, para que a ausência vire erro no ponto onde ela importa.
    """
    fora = {}
    for m in pricing.get("metrics") or []:
        for a in m.get("amounts") or []:
            if a.get("country") != pais:
                continue
            faixas = [(p.get("quantity_tier"), p.get("price")) for p in a.get("prices") or []]
            fora[m.get("metric_id")] = {"moeda": a.get("currency"),
                                        "charge_unit": m.get("charge_unit"),
                                        "tier_model": m.get("tier_model"),
                                        "faixas": faixas}
            break
    return fora


def _conferir_metricas(pricing: dict, exigidas: Iterable[str], pais: str, onde: str) -> None:
    """Fail-closed contra o zero silencioso: métrica exigida ausente, sem preço no país, ou
    com **todas** as faixas em zero levanta erro ANTES de a captura ser gravada."""
    tabela = precos_por_pais(pricing, pais)
    for alvo in exigidas:
        achadas = {mid: v for mid, v in tabela.items() if alvo in mid}
        if not achadas:
            raise ValueError(f"{onde}: métrica exigida {alvo!r} ausente ou sem preço em {pais}")
        if not any(preco for v in achadas.values() for _, preco in v["faixas"] if preco):
            raise ValueError(f"{onde}: métrica {alvo!r} veio ZERO em {pais} — provável captura "
                             f"no nó errado (o /pricing do plano devolve zero; use a região)")


# --------------------------------------------------------------------------- #
# via (a) — API IBM, travessia de três saltos                                  #
# --------------------------------------------------------------------------- #
def _abrir(url: str):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}),
        timeout=TIMEOUT_S,
    )


def _get_json(url: str) -> tuple[dict, int, int]:
    """(corpo decodificado, código HTTP, bytes). Para respostas pequenas — o offer file grande
    da AWS NÃO passa por aqui; ver `capturar_aws`."""
    with _abrir(url) as r:
        cru = r.read()
        return json.loads(cru.decode("utf-8")), r.status, len(cru)


def listar_filhos(no: str, limite: int = 200) -> tuple[list[dict], list[dict]]:
    """Filhos de um nó do catálogo, paginados. Devolve (recursos, saltos) — `saltos` carrega
    URL, status e bytes de cada página, para que a procedência registre a travessia inteira."""
    recursos: list[dict] = []
    saltos: list[dict] = []
    offset = 0
    while True:
        url = (f"{IBM_BASE}{urllib.parse.quote(no, safe='')}/%2A"
               f"?_offset={offset}&_limit={limite}")
        corpo, status, n = _get_json(url)
        pagina = corpo.get("resources") or []
        recursos += pagina
        saltos.append({"url": url, "http_status": status, "bytes": n})
        offset += len(pagina)
        if not pagina or offset >= corpo.get("count", 0):
            return recursos, saltos


def resolver_servico(nome: str) -> tuple[str, dict]:
    """Nó do catálogo a partir do nome do serviço -> (id, salto).

    A maioria dos serviços responde pelo próprio nome no caminho (`is.instance`), mas alguns
    só respondem pelo identificador — `codeengine` devolve **404 no caminho por nome** e o id
    dele é um UUID (medido em 2026-08-13). Sem esta resolução, metade da lista de SKUs selada
    falharia na captura por um motivo que não tem nada a ver com preço.
    """
    caminho = f"{IBM_BASE}{urllib.parse.quote(nome, safe='')}/%2A?_limit=1"
    try:
        _, status, n = _get_json(caminho)
        return nome, {"url": caminho, "http_status": status, "bytes": n, "papel": "resolucao-por-nome"}
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise

    busca = f"{IBM_BASE}?q=name:{urllib.parse.quote(nome)}&_limit=50"
    corpo, status, n = _get_json(busca)
    exatos = [r for r in corpo.get("resources") or [] if r.get("name") == nome]
    exatos.sort(key=lambda r: r.get("kind") != "service")     # entrada de serviço tem precedência
    if not exatos:
        raise KeyError(f"serviço {nome!r} não existe no catálogo (404 por nome e busca vazia)")
    return exatos[0]["id"], {"url": busca, "http_status": status, "bytes": n,
                             "papel": "resolucao-por-busca", "id_resolvido": exatos[0]["id"]}


def _achar(recursos: list[dict], nome: str, rotulo: str) -> dict:
    for r in recursos:
        if r.get("name") == nome:
            return r
    raise KeyError(f"{rotulo} {nome!r} não encontrado entre {len(recursos)} candidatos")


def _achar_deployment(recursos: list[dict], regiao: str) -> dict:
    for r in recursos:
        local = ((r.get("metadata") or {}).get("deployment") or {}).get("location")
        if local == regiao or regiao in (r.get("geo_tags") or []):
            return r
    raise KeyError(f"nenhum deployment em {regiao!r} entre {len(recursos)} filhos")


def capturar_ibm(servico: str, plano: str, regiao: str | None = "br-sao",
                 exigir_metricas: Iterable[str] = (), pais: str = PAIS_PADRAO,
                 raiz: Path = RAIZ) -> Path:
    """Preço de um plano da IBM, pela travessia `serviço -> plano -> [deployment] -> pricing`.

    `regiao=None` declara que o serviço é precificado **sem região** (Code Engine, Object
    Storage, bancos gerenciados) e o preço é lido no `/pricing` do próprio plano — dois saltos.
    Com `regiao`, são três, porque o do plano devolve zero em silêncio.
    """
    no_servico, salto_resolucao = resolver_servico(servico)
    planos, saltos = listar_filhos(no_servico)
    saltos.insert(0, salto_resolucao)
    escolhido = _achar(planos, plano, f"plano de {servico}")
    no_precificado, rotulo = escolhido, f"plano {plano}"

    if regiao is not None:
        filhos, mais = listar_filhos(escolhido["id"])
        saltos += mais
        no_precificado = _achar_deployment(filhos, regiao)
        rotulo = f"deployment {plano}@{regiao}"

    url_preco = f"{IBM_BASE}{urllib.parse.quote(no_precificado['id'], safe='')}/pricing"
    pricing, status, n = _get_json(url_preco)
    saltos.append({"url": url_preco, "http_status": status, "bytes": n})

    _conferir_metricas(pricing, exigir_metricas, pais, rotulo)

    sufixo = f"-{regiao}" if regiao else "-nao-regional"
    return salvar_captura("api", f"ibm-{servico}-{plano}{sufixo}",
                          {"url": url_preco, "timestamp_utc": _agora_utc(),
                           "http_status": status, "bytes": n, "via": "api", "provedor": "ibm",
                           "regiao": regiao, "regional": regiao is not None, "pais": pais,
                           "plano": plano, "plano_id": escolhido["id"],
                           "no_precificado_id": no_precificado["id"],
                           "saltos": saltos, "n_saltos": len(saltos),
                           "effective_from": pricing.get("effective_from"),
                           "metricas_exigidas": list(exigir_metricas),
                           "precos_no_pais": precos_por_pais(pricing, pais)},
                          pricing, raiz)


# --------------------------------------------------------------------------- #
# via (a) — API AWS                                                            #
# --------------------------------------------------------------------------- #
def _baixar_para_temp(url: str) -> tuple[Path, str, int, int]:
    """Streaming -> (caminho temporário, sha256 do arquivo COMPLETO, bytes, código HTTP)."""
    h = hashlib.sha256()
    total = 0
    fd, tmp = tempfile.mkstemp(prefix="aws-offer-", suffix=".json")
    with _abrir(url) as r, os.fdopen(fd, "wb") as f:
        status = r.status
        for bloco in iter(lambda: r.read(1 << 20), b""):
            h.update(bloco)
            total += len(bloco)
            f.write(bloco)
    return Path(tmp), h.hexdigest(), total, status


def capturar_aws(servico: str, filtro: Callable[[dict], bool],
                 regiao: str = "sa-east-1", raiz: Path = RAIZ) -> Path:
    """Price List da AWS: segue o `currentVersionUrl` da região e salva SÓ a fatia filtrada.

    `filtro` recebe o dicionário `attributes` de cada produto e decide se ele foi consultado.
    Obrigatório: é a declaração explícita de qual fatia do offer file sustenta o número.
    """
    idx_url = AWS_REGION_INDEX.format(servico=servico)
    indice, idx_status, idx_bytes = _get_json(idx_url)
    try:
        versao_rel = indice["regions"][regiao]["currentVersionUrl"]
    except KeyError as e:
        raise KeyError(f"região {regiao!r} ausente no region_index de {servico}") from e
    offer_url = AWS_HOST + versao_rel if versao_rel.startswith("/") else versao_rel

    tmp, sha_completo, n_bytes, status = _baixar_para_temp(offer_url)
    try:
        offer = json.loads(tmp.read_text(encoding="utf-8"))
    finally:
        tmp.unlink(missing_ok=True)   # o arquivo inteiro nunca fica em disco

    produtos = {sku: p for sku, p in offer.get("products", {}).items()
                if filtro(p.get("attributes", {}))}
    if not produtos:
        raise ValueError(f"captura AWS de {servico}@{regiao}: o filtro não casou nenhum produto "
                         f"entre {len(offer.get('products', {}))} — fatia vazia não é evidência")
    termos = {tipo: {sku: v for sku, v in por_sku.items() if sku in produtos}
              for tipo, por_sku in offer.get("terms", {}).items()}

    return salvar_captura("api", f"aws-{servico}-{regiao}",
                          {"url": offer_url, "timestamp_utc": _agora_utc(), "http_status": status,
                           "bytes": n_bytes, "via": "api", "provedor": "aws", "regiao": regiao,
                           "regional": True, "pais": "USA", "moeda": "USD",
                           "sha256_arquivo_completo": sha_completo,
                           "region_index_url": idx_url, "region_index_http_status": idx_status,
                           "region_index_bytes": idx_bytes,
                           "publicationDate": offer.get("publicationDate"),
                           "version": offer.get("version"),
                           "produtos_no_arquivo_completo": len(offer.get("products", {})),
                           "produtos_na_fatia": len(produtos)},
                          {"products": produtos, "terms": termos}, raiz)


# --------------------------------------------------------------------------- #
# via (b) — manual (estimador público)                                        #
# --------------------------------------------------------------------------- #
def capturar_ibm_provisionamento(servico: str, url: str, raiz: Path = RAIZ) -> Path:
    """Preço lido da API que a **tela oficial de provisionamento** da IBM consome.

    Descoberta em 2026-08-13 lendo as requisições de rede de `cloud.ibm.com/objectstorage/create`
    no navegador: a tela chama `/objectstorage/provision/api/v1/pricing?plan=…&region=…&country=…`.
    É a mesma natureza das capturas do catálogo global — JSON público, sem autenticação, endereçado
    por parâmetros explícitos — e por isso entra como `via="api"`, não como página.

    O que ela resolve e o catálogo global não: o Object Storage **não tem** métrica precificada no
    catálogo (deployment `global`, zero métrica), enquanto aqui vem a tabela inteira por classe de
    armazenamento e por faixa, com a região no parâmetro.

    Fail-closed: corpo sem o bloco de preços, ou com todos os preços em zero, levanta erro antes de
    gravar — um endpoint que muda de forma não pode virar planilha zerada em silêncio.
    """
    corpo, status, n = _get_json(url)
    precos = corpo.get("prices") or {}
    valores = [f.get("price") for grupo in precos.values() for faixas in grupo.values()
               for f in faixas]
    if not precos or not any(valores):
        raise ValueError(f"{servico}: resposta sem preço utilizável em {url} "
                         f"({len(precos)} grupos, {len(valores)} faixas)")
    return salvar_captura("api", servico,
                          {"url": url, "timestamp_utc": _agora_utc(), "http_status": status,
                           "bytes": n, "via": "api", "provedor": "ibm",
                           "fonte": "API da tela de provisionamento (cloud.ibm.com)",
                           "pais": corpo.get("country"), "moeda": corpo.get("currency"),
                           "grupos": sorted(precos)},
                          corpo, raiz)


def registrar_captura_manual(servico: str, url: str, data_captura: str,
                             arquivo_evidencia: str, itens: list, raiz: Path = RAIZ) -> Path:
    """Registra um preço lido no estimador público. Fail-closed: sem URL, data, arquivo de
    evidência EXISTENTE e itens, não grava — levanta ValueError."""
    faltando = [nome for nome, valor in
                (("url", url), ("data_captura", data_captura),
                 ("arquivo_evidencia", arquivo_evidencia), ("itens", itens))
                if not valor]
    if faltando:
        raise ValueError(f"captura manual sem procedência: faltam {faltando}")

    evid = Path(arquivo_evidencia)
    if not evid.is_absolute():
        evid = Path(raiz) / evid
    if not evid.is_file():
        raise ValueError(f"captura manual sem procedência: evidência inexistente em {evid}")

    return salvar_captura("manual", servico,
                          {"url": url, "timestamp_utc": _agora_utc(), "http_status": None,
                           "bytes": evid.stat().st_size, "via": "manual",
                           "classe_evidencia": "pagina-publica", "data_captura": data_captura,
                           "arquivo_evidencia": str(evid.relative_to(Path(raiz))
                                                    if evid.is_relative_to(Path(raiz)) else evid),
                           "sha256_evidencia": hashlib.sha256(evid.read_bytes()).hexdigest()},
                          {"itens": itens}, raiz)
