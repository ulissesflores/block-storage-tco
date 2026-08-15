#!/usr/bin/env python3
"""Segunda classe de evidência (D14): preço lido de **página pública**, com o corpo salvo em disco.

Quatro linhas de custo não saem pela API da IBM, e a razão de cada uma foi medida, não suposta —
está em `configs/projeto-tecnico.json` -> `skus_a_precificar.ibm_via_manual`. O enunciado autoriza
literalmente "calculadora pública", então a via existe por direito; o que ela **não** pode ser é
digitação do modelo. Daí a disciplina aqui:

1. o HTML cru é baixado e gravado em `data/evidencia/` — é o artefato que prova o que a página dizia;
2. os números são extraídos **por regra em código**, sobre esse arquivo, nunca lidos e digitados;
3. o registro final passa por `registrar_captura_manual`, que é fail-closed: sem arquivo de
   evidência existente em disco, sem URL e sem data, não grava. O registro carrega o SHA-256 do HTML,
   de modo que a cadeia de proveniência sela o vínculo número -> página, mesmo com o HTML fora do glob.

Uma página que não renderiza preço no servidor **falha aqui** — e falhar é o comportamento certo:
o item volta para a lista de pendências com a razão, em vez de virar número inventado.
"""

from __future__ import annotations

import html as _html
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import capture_prices as cp   # noqa: E402

DIR_EVIDENCIA = "data/evidencia"
# Navegador declarado: as páginas de produto da IBM recusam cliente sem User-Agent de navegador
# (medido: 403 pelo WebFetch, 200 aqui). Declarar é honesto; disfarçar identidade não é o ponto —
# o ponto é obter a mesma página que um humano veria na calculadora pública.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# `USD 0,10 / 1.000 tokens` e `0,42 USD / Capacity Unit-Hour` — as duas ordens aparecem na mesma página.
VALOR = re.compile(r"(?:USD\s*([\d]+(?:[.,]\d+)?)|([\d]+(?:[.,]\d+)?)\s*USD)\s*(?:/\s*([^<|\n]{1,40}))?")


def _texto(bruto: str) -> str:
    """HTML -> texto com marcador de fronteira, para que o rótulo não atravesse elementos."""
    sem_script = re.sub(r"<(script|style).*?</\1>", " ", bruto, flags=re.S | re.I)
    return re.sub(r"[ \t]+", " ", _html.unescape(re.sub(r"<[^>]+>", "\n", sem_script)))


def extrair_itens(bruto: str, rotulo_max: int = 120) -> list[dict]:
    """Todo par (rótulo, valor em dólar) que a página expõe, com a unidade quando declarada.

    O rótulo é o texto não vazio imediatamente anterior ao valor — é o que o leitor humano
    associaria ao número. Extração deliberadamente ampla: filtrar aqui esconderia o que a página
    de fato dizia, e a seleção do que entra na planilha é decisão do modelo, feita depois e à vista.
    """
    txt = _texto(bruto)
    itens: list[dict] = []
    for m in VALOR.finditer(txt):
        valor = (m.group(1) or m.group(2)).replace(",", ".")
        unidade = (m.group(3) or "").strip(" .;:")
        anteriores = [linha.strip() for linha in txt[:m.start()].split("\n") if linha.strip()]
        rotulo = " / ".join(anteriores[-2:])[-rotulo_max:] if anteriores else ""
        itens.append({"rotulo": rotulo, "usd": float(valor), "unidade": unidade})
    return itens


def capturar_pagina(servico: str, url: str, raiz: Path = RAIZ) -> tuple[Path, Path, list[dict]]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=90) as r:
        bruto = r.read().decode("utf-8", "replace")

    hoje = f"{datetime.now(timezone.utc):%Y-%m-%d}"
    evid = Path(raiz) / DIR_EVIDENCIA / f"{servico}-{hoje}.html"
    evid.parent.mkdir(parents=True, exist_ok=True)
    evid.write_text(bruto, encoding="utf-8")

    itens = extrair_itens(bruto)
    if not itens:
        raise ValueError(f"{servico}: a página não expõe preço no HTML servido "
                         f"({len(bruto)} bytes salvos em {evid.relative_to(raiz)}). "
                         f"Item volta para a lista de pendências — não se inventa número.")

    registro = cp.registrar_captura_manual(servico, url, hoje,
                                           str(evid.relative_to(raiz)), itens, raiz)
    return registro, evid, itens


def main(argv: list[str] | None = None) -> int:
    alvos = json.loads((RAIZ / "configs" / "fontes-manuais.json").read_text(encoding="utf-8"))
    falhas = 0
    for a in alvos["fontes"]:
        try:
            registro, evid, itens = capturar_pagina(a["servico"], a["url"])
            print(f"[OK    ] {a['servico']:34} {len(itens):>4} itens  {registro.name}")
        except Exception as e:
            falhas += 1
            print(f"[FALHOU] {a['servico']:34} {type(e).__name__}: {str(e)[:150]}")
    print(f"\n{len(alvos['fontes']) - falhas} de {len(alvos['fontes'])} fontes com preço em disco.")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
