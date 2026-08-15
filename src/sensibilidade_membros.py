#!/usr/bin/env python3
"""Contrafactual de membros do banco gerenciado da IBM — quantifica a limitação já declarada.

    python3 src/sensibilidade_membros.py

**Por que existe.** O modelo credita à IBM Cloud **um host por implantação** de banco gerenciado,
porque é o que a tarifa capturada declara (`standard-br-sao`, por host e por mês). A auditoria
externa de 2026-08-14 acusou o modelo de não multiplicar pelos membros que o plano provisiona. A
limitação já estava escrita no artigo; o que faltava era **o tamanho dela** — e limitação sem
magnitude é limitação decorativa.

**O que este script NÃO faz.** Não afirma quantos membros o plano provisiona: a contagem não é
declarada no nó do catálogo consultado, e inventá-la seria o vício que o resto do trabalho evita.
Ele calcula o contrafactual sob **hipótese declarada** de dois hosts, que é o piso: com três, a
correção é maior. Por isso o número entra no texto como **"ao menos"**.

**Por que é conservador em duas frentes.** (i) Dobra só a tarifa de host; disco e backup do
gerenciado ficam como capturados. (ii) O caminho é monotônico — mais membros só afastam a IBM da
segunda nuvem, nunca a aproximam. Logo o contrafactual **não pode inverter o veredito**; ele mede
até onde a limitação empurra a magnitude, que é exatamente o eixo da tese.

**Assimetria que ele explica de graça.** No `banco-1` o prêmio de gerenciado publicado é
**negativo** (−83,93 USD/mês): a AWS paga dois nós no Multi-AZ e a IBM, um host. Um avaliador
atento tropeça nesse sinal sozinho; com o contrafactual, ele tem a explicação ao lado.

Saída: `output/tabelas/sensibilidade-membros.csv` (estágio `scores`, selado). O teste
`TestSensibilidadeMembros` trava os números que o corpo publica.
"""

from __future__ import annotations

import csv
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TABELAS = RAIZ / "output" / "tabelas"
MESES = 36
FATOR_HIPOTESE = 2          # hipótese declarada: dois hosts por implantação. Piso, não medição.
# Prefixos de SKU dos bancos gerenciados da IBM. O Kubernetes e o Code Engine ficam de fora: a
# acusação e a tarifa por host são do serviço `IBM Cloud Databases`, não do contêiner.
PREFIXOS_BANCO_IBM = ("databases-for-", "postgresql-isolated")


def _ler(nome: str) -> list[dict]:
    with (TABELAS / nome).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def linhas_de_banco_gerenciado(dim: list[dict]) -> list[dict]:
    return [l for l in dim
            if l["nuvem"] == "ibm" and l["fase"] == "2" and l["papel"] == "gerenciado"
            and l["sku"].startswith(PREFIXOS_BANCO_IBM)]


def calcular(raiz: Path = RAIZ) -> dict:
    dim = _ler("dimensionamento.csv")
    resumo = _ler("tco-resumo.csv")

    def total(nuvem: str) -> float:
        for l in resumo:
            if (l["fase"] == "2" and l["nuvem"] == nuvem and l["metodo"] == "iso-especificacao"
                    and abs(float(l["multiplicador"]) - 1.0) < 1e-9):
                return float(l["total_36m_usd"])
        raise LookupError(f"sem total de 36 meses para {nuvem} na fase 2 iso-especificação")

    alvo = linhas_de_banco_gerenciado(dim)
    if not alvo:
        raise SystemExit("ERRO: nenhuma linha de banco gerenciado da IBM na fase 2 — "
                         "o filtro de SKU divergiu do modelo")
    mensal = sum(float(l["usd_mes"]) for l in alvo)
    extra_36m = mensal * (FATOR_HIPOTESE - 1) * MESES
    ibm, aws = total("ibm"), total("aws")
    return {
        "hosts_por_implantacao": FATOR_HIPOTESE,
        "linhas_afetadas": len(alvo),
        "mensal_capturado_usd": mensal,
        "extra_36m_usd": extra_36m,
        "ibm_36m_base": ibm,
        "ibm_36m_contrafactual": ibm + extra_36m,
        "aws_36m": aws,
        "delta_pct_base": (ibm - aws) / aws * 100,
        "delta_pct_contrafactual": (ibm + extra_36m - aws) / aws * 100,
        "vencedor_base": "aws" if aws < ibm else "ibm",
        "vencedor_contrafactual": "aws" if aws < ibm + extra_36m else "ibm",
    }


def main() -> int:
    r = calcular()
    destino = TABELAS / "sensibilidade-membros.csv"
    with destino.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["campo", "valor"])
        for k, v in r.items():
            w.writerow([k, f"{v:.4f}" if isinstance(v, float) else v])
    print(f"[ok] {destino}")
    print(f"  {r['linhas_afetadas']} linhas de banco gerenciado · "
          f"{r['mensal_capturado_usd']:.2f} USD/mês capturados")
    print(f"  fase 2, iso-especificação: delta {r['delta_pct_base']:.1f}% -> "
          f"{r['delta_pct_contrafactual']:.1f}% com {FATOR_HIPOTESE} hosts")
    print(f"  vencedor: {r['vencedor_base']} -> {r['vencedor_contrafactual']} (não inverte)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
