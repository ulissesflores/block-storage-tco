#!/usr/bin/env python3
"""Executa a captura de preços contra a LISTA SELADA e gera o manifesto por código.

Regra do entregável D04: a cobertura é conferida **contra a lista selada** em
`configs/projeto-tecnico.json`, nunca contra uma lista redefinida em tempo de captura. Alvo
selado que falha é falha do run — sai com código diferente de zero e aparece no manifesto como
`FALHOU`, com a exceção literal. Nada é "pulado em silêncio".

O manifesto é **gerado deste conjunto de arquivos**, não redigido: o critério de aceite do D01/D04
exige veredito por serviço computado dos corpos crus em disco.

    python3 src/run_capture.py              # captura tudo
    python3 src/run_capture.py --so ibm     # só um provedor
    python3 src/run_capture.py --manifesto  # só regenera o manifesto do que já está em disco

Filtros da AWS: cada offer file tem centenas de MB e o filtro declara qual fatia sustenta o número.
Eles vivem aqui, versionados e selados, porque são parte da procedência — um filtro trocado muda os
preços disponíveis tanto quanto uma URL trocada.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import capture_prices as cp   # noqa: E402

PROJETO = RAIZ / "configs" / "projeto-tecnico.json"

# Tamanhos de instância que cobrem a escada exigida pelos 12 servidores (2 a 16 vCPU).
TAMANHOS_EC2 = r"(large|xlarge|2xlarge|4xlarge)"
FAMILIAS_EC2 = r"^[mc][0-9]+[a-z]*\."          # propósito geral (m*) e otimizada p/ computação (c*)
TAMANHOS_RDS = r"^db\.[a-z0-9]+\." + TAMANHOS_EC2 + r"$"


def _f_ec2(a: dict) -> bool:
    """Instâncias Linux em locação compartilhada, sem software pré-instalado, mais volumes gp3."""
    if a.get("volumeApiName") == "gp3":
        return True                                     # bloco: armazenamento, IOPS e vazão
    it = a.get("instanceType", "")
    return (a.get("operatingSystem") == "Linux" and a.get("tenancy") == "Shared"
            and a.get("preInstalledSw") == "NA" and a.get("capacitystatus") == "Used"
            and bool(re.match(FAMILIAS_EC2 + TAMANHOS_EC2 + r"$", it)))


def _f_rds(a: dict) -> bool:
    """MySQL, PostgreSQL e Oracle: instâncias na escada + armazenamento do banco."""
    motor = (a.get("databaseEngine") or "").lower()
    if not any(m in motor for m in ("mysql", "postgresql", "oracle")):
        return False
    it = a.get("instanceType", "")
    return bool(re.match(TAMANHOS_RDS, it)) or "Storage" in (a.get("usagetype") or "")


def _f_engine(*chaves: str):
    """Filtro por instância na escada, para serviços de um motor só (cache, documento)."""
    def f(a: dict) -> bool:
        it = a.get("instanceType", "")
        if bool(re.match(TAMANHOS_RDS, it)):
            return True
        alvo = " ".join(str(a.get(k) or "") for k in ("usagetype", "productFamily", "operation"))
        return any(c.lower() in alvo.lower() for c in chaves)
    return f


def _f_tudo(a: dict) -> bool:
    """Serviços cujo catálogo regional já é pequeno — a fatia é o arquivo da região inteiro."""
    return True


FILTROS = {
    "AmazonEC2": _f_ec2,
    "AmazonRDS": _f_rds,
    "AmazonElastiCache": _f_engine("Redis", "NodeUsage", "Cache"),
    "AmazonDocDB": _f_engine("InstanceUsage", "StorageUsage", "IOUsage"),
    "AmazonEKS": _f_tudo,
    "AWSLambda": _f_tudo,
    "AmazonS3": _f_tudo,
    "AWSDataTransfer": _f_tudo,
    "AWSELB": _f_tudo,
    "AmazonBedrock": _f_tudo,
}


def _alvos_ibm(pt: dict) -> list[tuple]:
    """Alvos da lista selada MAIS os das emendas (`configs/emenda-*.json`).

    Emenda existe porque um achado selado pode ser refutado por medição posterior — foi o caso
    dos bancos gerenciados, cujo preço de São Paulo existe no deployment da região e não no
    `/pricing` do plano. O arquivo selado não é reescrito: a correção entra como arquivo próprio
    e datado, também dentro do estágio `inputs`, e a cadeia exibe as duas versões.

    Captura e manifesto leem a MESMA função de propósito: se a emenda entrasse só no capturador,
    o gate continuaria julgando pela lista antiga e diria a coisa errada com toda a confiança.
    """
    entradas = list(pt["skus_a_precificar"]["ibm"])
    for emenda in _emendas():
        # `.get` porque nem toda emenda acrescenta alvo de captura: a emenda 03 é de MODELAGEM
        # (volumetria da camada de IA, convenções de paridade) e não toca a lista de SKUs.
        entradas += emenda.get("skus_a_precificar", {}).get("ibm", [])
    return [(e["servico"], plano, e.get("regiao"), e.get("metrica_exigida"), e.get("item_custo"))
            for e in entradas for plano in e["planos"]]


def _emendas() -> list[dict]:
    return [json.loads(a.read_text(encoding="utf-8"))
            for a in sorted((RAIZ / "configs").glob("emenda-*.json"))]


def _alvos_provisionamento() -> list[dict]:
    """Alvos servidos pela API que a tela de provisionamento da IBM consome (só por emenda).

    Existem porque o catálogo global não precifica tudo: o Object Storage tem deployment `global`
    e zero métrica, enquanto esta API devolve a tabela por classe e por faixa com a região no
    parâmetro. Descoberta lendo as requisições de rede do navegador; a captura é por código.
    """
    return [alvo for e in _emendas()
            for alvo in e.get("skus_a_precificar", {}).get("ibm_via_provisionamento", [])]


def capturar_tudo(so: str | None = None, raiz: Path = RAIZ) -> list[dict]:
    pt = json.loads(PROJETO.read_text(encoding="utf-8"))
    resultados: list[dict] = []

    if so in (None, "ibm"):
        for servico, plano, regiao, metrica, item in _alvos_ibm(pt):
            alvo = {"provedor": "ibm", "servico": servico, "plano": plano,
                    "regiao": regiao or "não-regional (declarado)", "item_custo": item}
            try:
                destino = cp.capturar_ibm(servico, plano, regiao=regiao,
                                          exigir_metricas=[metrica] if metrica else (), raiz=raiz)
                alvo |= {"veredito": "OK", "arquivo": str(destino.relative_to(raiz))}
            except Exception as e:
                alvo |= {"veredito": "FALHOU", "erro": f"{type(e).__name__}: {e}"}
            resultados.append(alvo)
            print(f"[{alvo['veredito']:6}] ibm {servico}/{plano}", flush=True)

        for e in _alvos_provisionamento():
            alvo = {"provedor": "ibm", "servico": e["servico"], "plano": "tela de provisionamento",
                    "regiao": e["regiao"], "item_custo": e["item_custo"]}
            try:
                destino = cp.capturar_ibm_provisionamento(e["servico"], e["url"], raiz=raiz)
                alvo |= {"veredito": "OK", "arquivo": str(destino.relative_to(raiz))}
            except Exception as e_:
                alvo |= {"veredito": "FALHOU", "erro": f"{type(e_).__name__}: {e_}"}
            resultados.append(alvo)
            print(f"[{alvo['veredito']:6}] ibm {e['servico']} (provisionamento)", flush=True)

    if so in (None, "aws"):
        for e in pt["skus_a_precificar"]["aws"]:
            servico, regiao = e["servico"], e["regiao"]
            alvo = {"provedor": "aws", "servico": servico, "plano": e["fatia"],
                    "regiao": regiao, "item_custo": e["item_custo"]}
            try:
                destino = cp.capturar_aws(servico, FILTROS[servico], regiao=regiao, raiz=raiz)
                alvo |= {"veredito": "OK", "arquivo": str(destino.relative_to(raiz))}
            except Exception as e_:
                alvo |= {"veredito": "FALHOU", "erro": f"{type(e_).__name__}: {e_}"}
            resultados.append(alvo)
            print(f"[{alvo['veredito']:6}] aws {servico}", flush=True)

    return resultados


def gerar_manifesto(raiz: Path = RAIZ) -> Path:
    """Manifesto computado dos arquivos em disco — não do relatório da execução.

    Ler o disco em vez de confiar no retorno da captura é o que impede o manifesto de afirmar
    cobertura que não existe: se um arquivo foi apagado depois, o manifesto acusa.
    """
    pt = json.loads(PROJETO.read_text(encoding="utf-8"))
    linhas = ["# Manifesto da captura de preços — IBM Cloud e AWS, São Paulo",
              "",
              f"> Gerado por `src/run_capture.py --manifesto` em "
              f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}, **lendo os corpos crus em "
              f"disco**. Cobertura conferida contra a lista selada em `configs/projeto-tecnico.json`.",
              "",
              "| Provedor | Serviço | Plano / fatia | Região do preço | Item de custo | Arquivo | Bytes | Métricas com preço |",
              "|---|---|---|---|---|---|---|---|"]
    faltando: list[str] = []

    def _achar(prefixo: str) -> Path | None:
        cands = sorted((raiz / cp.DIR_PRECOS).rglob(f"{prefixo}-*.json"))
        return cands[-1] if cands else None

    for servico, plano, regiao, _metrica, item in _alvos_ibm(pt):
        sufixo = f"-{regiao}" if regiao else "-nao-regional"
        arq = _achar(f"ibm-{servico}-{plano}{sufixo}")
        if arq is None:
            faltando.append(f"ibm {servico}/{plano}")
            continue
        r = json.loads(arq.read_text(encoding="utf-8"))
        n = sum(1 for v in r.get("precos_no_pais", {}).values()
                if any(p for _, p in v.get("faixas", [])))
        linhas.append(f"| IBM | `{servico}` | `{plano}` | {regiao or 'não-regional (declarado)'} | "
                      f"{item} | `{arq.relative_to(raiz)}` | {arq.stat().st_size} | {n} |")

    for e in pt["skus_a_precificar"]["aws"]:
        arq = _achar(f"aws-{e['servico']}-{e['regiao']}")
        if arq is None:
            faltando.append(f"aws {e['servico']}")
            continue
        r = json.loads(arq.read_text(encoding="utf-8"))
        linhas.append(f"| AWS | `{e['servico']}` | {e['fatia']} | {e['regiao']} | {e['item_custo']} | "
                      f"`{arq.relative_to(raiz)}` | {arq.stat().st_size} | "
                      f"{r.get('produtos_na_fatia', '—')} produtos na fatia |")

    for e in _alvos_provisionamento():
        arq = _achar(e["servico"])
        if arq is None:
            faltando.append(f"ibm {e['servico']} (provisionamento)")
            continue
        r = json.loads(arq.read_text(encoding="utf-8"))
        n = sum(1 for grupo in r["conteudo"]["prices"].values() for faixas in grupo.values()
                if any(f.get("price") for f in faixas))
        linhas.append(f"| IBM | `{e['servico']}` | tela de provisionamento | {e['regiao']} | "
                      f"{e['item_custo']} | `{arq.relative_to(raiz)}` | {arq.stat().st_size} | {n} |")

    linhas += ["", "## Alvos selados sem captura em disco", ""]
    linhas += ([f"- **{f}**" for f in faltando] if faltando
               else ["Nenhum. Todos os alvos da lista selada têm corpo cru em disco."])
    linhas += ["", "## Segunda classe de evidência (D14, `pagina-publica`)", "",
               "| Item de custo | Fonte | Itens extraídos | Evidência em disco | SHA-256 |",
               "|---|---|---|---|---|"]
    fontes = json.loads((raiz / "configs" / "fontes-manuais.json").read_text(encoding="utf-8"))
    resolvidos: set[str] = set()
    for f in fontes["fontes"]:
        arq = _achar(f["servico"])
        if arq is None:
            linhas.append(f"| `{f['item_custo']}` | {f['url']} | — | **sem captura** | — |")
            continue
        r = json.loads(arq.read_text(encoding="utf-8"))
        itens = r["conteudo"]["itens"]
        # Um número na página não é um preço. Só conta como resolvido o item que traz UNIDADE de
        # cobrança declarada (por TB e mês, por hora, por token, por página). Sem isto, uma linha
        # como "ganhe até US$ 500 de crédito" satisfaria o gate — presença de cifra não é tarifa.
        com_unidade = [i for i in itens if i.get("unidade")]
        if com_unidade:
            resolvidos.add(f["item_custo"])
        marca = "" if com_unidade else " ⚠️ **sem unidade de cobrança — não é tarifa**"
        linhas.append(f"| `{f['item_custo']}` | {f['url']} | {len(itens)} ({len(com_unidade)} com "
                      f"unidade){marca} | `{r['arquivo_evidencia']}` | `{r['sha256_evidencia'][:16]}…` |")

    # Item dominante também se resolve pela via de API: o banco gerenciado da IBM TEM tarifa
    # (plano `standard-gen2`), só não atribuível a br-sao — o que a coluna "região do preço"
    # declara. Tratar isso como "sem preço" seria um vermelho falso, tão ruim quanto o verde falso.
    for servico, plano, regiao, _m, item in _alvos_ibm(pt):
        sufixo = f"-{regiao}" if regiao else "-nao-regional"
        arq = _achar(f"ibm-{servico}-{plano}{sufixo}")
        if arq and any(p for v in json.loads(arq.read_text(encoding="utf-8"))
                       .get("precos_no_pais", {}).values() for _, p in v.get("faixas", [])):
            resolvidos.add(item)

    # A tela de provisionamento é terceira via, e resolve o que nem catálogo nem página resolvem.
    for e in _alvos_provisionamento():
        arq = _achar(e["servico"])
        if arq and any(f.get("price") for grupo in
                       json.loads(arq.read_text(encoding="utf-8"))["conteudo"]["prices"].values()
                       for faixas in grupo.values() for f in faixas):
            resolvidos.add(e["item_custo"])

    faltam = [m for m in pt["skus_a_precificar"]["ibm_via_manual"]
              if m["item_custo"] not in resolvidos]
    linhas += ["", "### Itens de custo ainda sem preço por nenhuma via", ""]
    linhas += ([f"- `{m['item_custo']}` — {m['servico']}. Razão da ausência na API: {m['razao']}"
                for m in faltam] if faltam else ["Nenhum."])

    dominantes = set(pt["conjunto_minimo_publicavel"]["dominantes"])
    sem_numero = sorted(dominantes & {m["item_custo"] for m in faltam})
    linhas += ["", "### Gate D15 — conjunto mínimo publicável", "",
               ("**REPROVA.** Item dominante sem número: " + ", ".join(f"`{d}`" for d in sem_numero)
                + ". Enquanto isto durar, o cenário correspondente não entra na planilha nem no texto."
                if sem_numero else
                "**PASSA** quanto à existência de preço: todo item dominante tem número em disco.")]

    destino = raiz / cp.DIR_PRECOS / "MANIFEST.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return destino


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Captura de preços contra a lista selada.")
    ap.add_argument("--so", choices=["ibm", "aws"], default=None)
    ap.add_argument("--manifesto", action="store_true", help="só regenera o manifesto")
    ap.add_argument("--root", type=Path, default=RAIZ)
    args = ap.parse_args(argv)

    falhas = 0
    if not args.manifesto:
        resultados = capturar_tudo(args.so, args.root)
        falhas = sum(1 for r in resultados if r["veredito"] == "FALHOU")
        for r in resultados:
            if r["veredito"] == "FALHOU":
                print(f"  FALHA {r['provedor']} {r['servico']}/{r.get('plano')}: {r['erro']}",
                      file=sys.stderr)

    print(f"[manifesto] {gerar_manifesto(args.root)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        traceback.print_exc()
        raise SystemExit(130)
