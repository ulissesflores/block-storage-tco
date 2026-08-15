#!/usr/bin/env python3
"""Modelo de fila da Aplicação 2 — Kingman G/G/1 — e a derivação do ponto de operação iso-SLA.

    python3 src/filas.py            # escreve os CSV em output/tabelas/
    python3 src/filas.py --resumo   # imprime no terminal, sem escrever

**Este módulo existe separado por invariância, não por organização.** O modelo de custo
(`tco.py`) afirma no corpo do paper que o ponto de virada é invariante aos parâmetros de fila —
utilização, variabilidade, taxa de chegada. Se o caminho de cômputo do custo importasse qualquer
coisa daqui, a afirmação seria falsa e inspecionável em dez segundos por quem lesse o código. A
dependência é de mão única e há teste mecânico que a trava: `tco.py` e `catalogo.py` não alcançam
`filas` no grafo transitivo de importação.

O que este módulo entrega, e por que importa:

1. **A curva utilização x tempo de resposta** (figura 5), que justifica visualmente por que
   dimensionar por especificação não é o mesmo que dimensionar por alvo de latência.
2. **O ponto de operação iso-SLA, DERIVADO** — o menor multiplicador da grade pré-registrada cujo
   percentil 95 do tempo de resposta cabe nos 200 ms do requisito especial. Antes desta etapa o
   repositório não dizia qual multiplicador ia à tabela de síntese; escolher um a olho seria o
   mesmo vício de parâmetro-que-escolhe-o-resultado que a adjudicação do validador nº 2 matou.
   Regra e justificativa em `configs/emenda-04-2026-08-13.json`.

Fórmulas, com a atribuição correta (a confusão entre elas é erro que um avaliador do setor pega):

- **Kingman (1961)**, aproximação G/G/1:  Wq = (rho/(1-rho)) * ((Ca^2 + Cs^2)/2) * E[S].
- **Pollaczek-Khinchine** é a fórmula EXATA de M/G/1. Ela É o que se calcula aqui na MÉDIA: o caso
  declara `cv_chegada = 1,0` como chegadas de Poisson (`premissas-carga.json`), e com Ca^2 = 1 a
  expressão de Kingman coincide numericamente com Pollaczek-Khinchine. A média é exata sob essa
  hipótese; o percentil é que é aproximação. *(A versão anterior deste bloco dizia que P-K "não é o
  que se usa aqui" — retratado na `emenda-05-2026-08-13.json`, peça 2. Vale escrever "chegadas de
  Poisson", não só "Ca = 1": coeficiente unitário é necessário e não suficiente.)*
- **Kingman (1962)**: em tráfego pesado a distribuição da espera converge para a exponencial, o
  que fecha a ponte média -> percentil. Daí P95 = media * ln(1/(1-0,95)). Fora do tráfego pesado a
  forma continua **exata em M/M/1** (ver `test_forma_e_exata_em_mm1`), e é isso que a autoriza; a
  **direção** do erro fora desses dois casos NÃO é afirmada — ver a emenda 05.

Toda constante numérica vem de `configs/premissas-carga.json` e `configs/caso-xyz.json`, ambos
selados; nada é digitado aqui. O único número literal do arquivo é o nível do percentil, e ele
também é lido do arquivo selado.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ALVO = "app-2"          # a Aplicação 2 é o único servidor cujo requisito especial é de latência


# --------------------------------------------------------------------------- #
# insumos                                                                      #
# --------------------------------------------------------------------------- #
def carregar(raiz: Path = RAIZ) -> dict:
    """Lê as premissas seladas. Falha alto se o alvo não estiver no caso — o modelo não inventa."""
    premissas = json.loads((raiz / "configs" / "premissas-carga.json").read_text(encoding="utf-8"))
    caso = json.loads((raiz / "configs" / "caso-xyz.json").read_text(encoding="utf-8"))
    emenda = json.loads((raiz / "configs" / "emenda-04-2026-08-13.json").read_text(encoding="utf-8"))

    servidores = [s for v in caso.values() if isinstance(v, list) for s in v
                  if isinstance(s, dict) and s.get("id") == ALVO]
    if not servidores:
        raise LookupError(f"{ALVO} não encontrado em caso-xyz.json — o modelo de fila não tem alvo")
    return {"premissas": premissas, "emenda": emenda, "servidor": servidores[0],
            "api": premissas["api_rest"], "grade": premissas["grade_sensibilidade"]}


# --------------------------------------------------------------------------- #
# o modelo                                                                     #
# --------------------------------------------------------------------------- #
def utilizacao(pico_rps: float, servico_s: float, vcpu: float, multiplicador: float) -> float:
    """rho(m) = lambda * E[S] / (vCPU especificado * m).

    Em m = 1 reproduz o valor selado em `premissas-carga.json/_nota_estabilidade`
    (60 * 0,025 / 2 = 0,75). O multiplicador é o headroom sobre a ESPECIFICAÇÃO, que é a definição
    do método iso-SLA — a escada de SKU arredonda para cima a partir daí, então usar o requisito é
    o lado conservador da conta.
    """
    capacidade = vcpu * multiplicador
    if capacidade <= 0:
        raise ValueError("capacidade não-positiva")
    return pico_rps * servico_s / capacidade


def espera_kingman(rho: float, ca2: float, cs2: float, servico_s: float) -> float:
    """Espera média em fila, G/G/1 (Kingman, 1961). Estoura em rho >= 1, que é o certo:
    fila instável não tem espera média finita, e devolver um número seria mentir."""
    if not 0.0 < rho < 1.0:
        raise ValueError(f"rho={rho:.4f} fora de (0,1): fila instável ou vazia, sem espera finita")
    return (rho / (1.0 - rho)) * ((ca2 + cs2) / 2.0) * servico_s


def percentil_resposta(espera_s: float, servico_s: float, p: float) -> float:
    """Percentil do TEMPO DE RESPOSTA sob cauda exponencial (Kingman, 1962).

    Trata resposta como uma variável só, de média Wq + E[S]. Exata em M/M/1 para qualquer
    utilização: com Ca^2 = Cs^2 = 1 a média colapsa em E[S]/(1-rho) e o percentil, no resultado
    clássico. Somar P95 da espera com a MÉDIA do serviço, a alternativa óbvia, mistura duas
    escalas e não é cota nem por cima nem por baixo — a escolha está declarada na emenda 04.
    """
    if not 0.0 < p < 1.0:
        raise ValueError("percentil fora de (0,1)")
    return (espera_s + servico_s) * math.log(1.0 / (1.0 - p))


def avaliar(cfg: dict, multiplicador: float, cs: float | None = None,
            ca: float | None = None) -> dict:
    """Um ponto do modelo: utilização, espera, resposta média e percentil, em milissegundos."""
    api = cfg["api"]
    servico_s = api["tempo_servico_medio_ms"] / 1000.0
    ca2 = (api["cv_chegada"] if ca is None else ca) ** 2
    cs2 = (api["cv_servico"] if cs is None else cs) ** 2
    rho = utilizacao(api["pico_rps"], servico_s, cfg["servidor"]["vcpu"], multiplicador)
    instavel = rho >= 1.0
    wq = float("inf") if instavel else espera_kingman(rho, ca2, cs2, servico_s)
    p = api["percentil_alvo"] / 100.0
    pxx = float("inf") if instavel else percentil_resposta(wq, servico_s, p)
    return {
        "multiplicador": multiplicador,
        "cv_chegada": math.sqrt(ca2),
        "cv_servico": math.sqrt(cs2),
        "rho": rho,
        "espera_media_ms": wq * 1000.0,
        "resposta_media_ms": (wq + servico_s) * 1000.0,
        f"resposta_p{api['percentil_alvo']}_ms": pxx * 1000.0,
        "alvo_ms": float(api["alvo_latencia_ms"]),
        "atende": bool(pxx * 1000.0 <= api["alvo_latencia_ms"]),
    }


# --------------------------------------------------------------------------- #
# a derivação (o entregável desta etapa)                                       #
# --------------------------------------------------------------------------- #
def ponto_iso_sla(cfg: dict, cs: float | None = None) -> dict:
    """Menor multiplicador DA GRADE PRÉ-REGISTRADA que cumpre o alvo de percentil.

    Devolve `existe: False` em vez de extrapolar. Sair da grade selada para achar um número que
    agrade é exatamente o que o pré-registro existe para impedir; se nenhum ponto cumprir, o
    resultado reportável é que a grade não alcança o alvo.
    """
    grade = sorted(cfg["grade"]["multiplicador_headroom"])
    pontos = [avaliar(cfg, m, cs=cs) for m in grade]
    aptos = [p for p in pontos if p["atende"]]
    return {"existe": bool(aptos), "escolhido": aptos[0] if aptos else None,
            "pontos": pontos, "grade": grade}


def sensibilidade_cv(cfg: dict) -> list[dict]:
    """O ponto derivado para cada valor de cv de serviço da grade. Relata-se a grade inteira:
    recortá-la depois de vê-la é o mesmo vício que ela existe para impedir (pré-registro §4)."""
    linhas = []
    for cs in cfg["grade"]["cv_servico"]:
        r = ponto_iso_sla(cfg, cs=cs)
        alvo = cfg["api"]["alvo_latencia_ms"]
        chave = f"resposta_p{cfg['api']['percentil_alvo']}_ms"
        linhas.append({
            "cv_servico": cs,
            "selado_em_premissas": cs == cfg["api"]["cv_servico"],
            "multiplicador_derivado": r["escolhido"]["multiplicador"] if r["existe"] else "",
            "rho_no_ponto": r["escolhido"]["rho"] if r["existe"] else "",
            f"resposta_p95_ms": r["escolhido"][chave] if r["existe"] else "",
            "alvo_ms": float(alvo),
            "_leitura": ("cumpre o alvo dentro da grade" if r["existe"] else
                         "a grade pré-registrada NÃO alcança o alvo neste nível de variabilidade "
                         "— resultado reportável, não motivo para estender a grade"),
        })
    return linhas


def curva(cfg: dict, passo: float = 0.01, teto: float = 0.95) -> list[dict]:
    """Curva utilização x tempo de resposta, para cada cv de serviço da grade (figura 5)."""
    api, servico_s = cfg["api"], cfg["api"]["tempo_servico_medio_ms"] / 1000.0
    ca2, p = api["cv_chegada"] ** 2, api["percentil_alvo"] / 100.0
    linhas = []
    n = int(round(teto / passo))
    for i in range(1, n + 1):
        rho = round(i * passo, 10)
        for cs in cfg["grade"]["cv_servico"]:
            wq = espera_kingman(rho, ca2, cs ** 2, servico_s)
            linhas.append({
                "rho": rho, "cv_servico": cs,
                "espera_media_ms": wq * 1000.0,
                "resposta_media_ms": (wq + servico_s) * 1000.0,
                f"resposta_p{api['percentil_alvo']}_ms":
                    percentil_resposta(wq, servico_s, p) * 1000.0,
            })
    return linhas


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
    derivado = ponto_iso_sla(cfg)
    saidas = {
        "filas-curva-kingman.csv": curva(cfg),
        "filas-ponto-iso-sla.csv": derivado["pontos"],
        "filas-sensibilidade-cv.csv": sensibilidade_cv(cfg),
    }
    if escrever:
        for nome, linhas in saidas.items():
            _escrever(raiz / "output" / "tabelas" / nome, linhas)
    return {"cfg": cfg, "derivado": derivado, "saidas": saidas}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Modelo de fila da Aplicação 2 (API REST).")
    ap.add_argument("--root", type=Path, default=RAIZ)
    ap.add_argument("--resumo", action="store_true", help="imprime sem escrever os CSV")
    args = ap.parse_args(argv)

    r = executar(args.root, escrever=not args.resumo)
    chave = f"resposta_p{r['cfg']['api']['percentil_alvo']}_ms"
    print(f"{'mult':>6} {'rho':>7} {'Wq (ms)':>9} {'resposta média':>15} {'P95 (ms)':>9}  alvo")
    for p in r["derivado"]["pontos"]:
        print(f"{p['multiplicador']:>6.2f} {p['rho']:>7.4f} {p['espera_media_ms']:>9.1f} "
              f"{p['resposta_media_ms']:>15.1f} {p[chave]:>9.1f}  "
              f"{'CUMPRE' if p['atende'] else 'excede'}")
    d = r["derivado"]
    if d["existe"]:
        e = d["escolhido"]
        print(f"\n[ponto de operação iso-SLA, DERIVADO] multiplicador {e['multiplicador']:.2f} "
              f"(rho {e['rho']:.4f}, P95 {e[chave]:.1f} ms <= {e['alvo_ms']:.0f} ms)")
    else:
        print("\n[ponto de operação iso-SLA] nenhum ponto da grade pré-registrada cumpre o alvo")
    for l in sensibilidade_cv(r["cfg"]):
        marca = " (selado)" if l["selado_em_premissas"] else ""
        print(f"  cv_servico {l['cv_servico']:.1f}{marca}: multiplicador "
              f"{l['multiplicador_derivado'] or 'nenhum na grade'}")
    if not args.resumo:
        print(f"\n[csv] {args.root / 'output' / 'tabelas'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
