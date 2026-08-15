#!/usr/bin/env python3
"""As cinco figuras do corpo, geradas por código a partir do que já está selado.

    python3 src/figuras.py            # gera os PNG e o arquivo de legendas
    python3 src/figuras.py --medir    # só mede tamanho e altura de fonte, sem regravar

Saída em `output/figuras/` — **fora da cadeia de proveniência**, por decisão registrada: os
estágios `figures` e `paper` foram cortados na adjudicação do validador nº 2, porque o texto é
reeditado muitas vezes e nunca será publicado. O que está selado é o que as figuras DESENHAM: os
CSV de `output/tabelas/` e os JSON de `configs/`. Uma figura que discordasse do CSV seria pega
pelo teste, não pela vista.

Três travas de desenho, todas com razão:

1. **Nenhum número é digitado.** Toda barra, ponto e rótulo numérico vem de CSV lido em disco.
2. **A legenda não é desenhada dentro do PNG.** A norma de estilo adotada (APA 7, §6)
   manda rótulo e título ACIMA do elemento e `Fonte:` ABAIXO, em fonte igual à do texto —
   Times New Roman 12. Assar isso no PNG produziria tipografia estrangeira ao corpo.
3. **Largura útil de A4 com margens de 2,54 cm = 16,5 cm.** É a largura de todas as figuras, e é
   contra ela que o critério de emancipação da figura 6 é medido (emenda 04).

Idioma: PT-BR nas figuras do paper, por regra de método da casa — a figura casa com o corpo.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                            # noqa: E402
from matplotlib.lines import Line2D                                        # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "output" / "figuras"
LARGURA_A4_CM = 16.5
CM = 1 / 2.54
DPI = 300

# paleta sóbria, legível em impressão monocromática (as famílias diferem em luminosidade)
COR = {
    "ibm": "#3B5B92", "aws": "#B4762A",
    "borda": "#2F3E4E", "seguranca": "#6E5A8C", "dados": "#3F6B52", "ia": "#8C3B3B",
    "fundo": "#F4F5F7", "linha": "#4A4A4A", "alvo": "#A02020",
}
COR_ITEM = {
    "compute": "#4E79A7", "bloco": "#F28E2B", "objeto": "#59A14F", "egress": "#E15759",
    "premio-gerenciado": "#B07AA1", "backup": "#76B7B2", "rede-ip-balanceador": "#EDC948",
    "ia": "#9C755F", "licencas": "#BAB0AC", "suporte": "#D3D3D3", "observabilidade": "#AAAAAA",
}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8, "axes.titlesize": 9,
    "axes.labelsize": 8, "legend.fontsize": 7.5, "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5, "axes.edgecolor": COR["linha"], "axes.linewidth": 0.6,
    "savefig.facecolor": "white", "figure.facecolor": "white",
})
MENOR_FONTE_PT = 6.5   # piso absoluto de desenho
PISO_LEGIBILIDADE_PT = 7.0   # critério da emenda 04 para o detalhe embutido continuar embutido
MEDICOES: dict[str, dict] = {}   # preenchido na geração; gravado em MEDICOES.json


# --------------------------------------------------------------------------- #
# insumos                                                                      #
# --------------------------------------------------------------------------- #
def ler_csv(nome: str, raiz: Path = RAIZ) -> list[dict]:
    with (raiz / "output" / "tabelas" / nome).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def ler_json(nome: str, raiz: Path = RAIZ) -> dict:
    return json.loads((raiz / "configs" / nome).read_text(encoding="utf-8"))


def br(valor: float, casas: int = 0) -> str:
    return f"{valor:,.{casas}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def multiplicador_iso_sla(raiz: Path = RAIZ) -> float:
    """O ponto de operação derivado em `filas.py`, lido do CSV — nunca escolhido aqui."""
    aptos = [l for l in ler_csv("filas-ponto-iso-sla.csv", raiz) if l["atende"] == "True"]
    if not aptos:
        raise LookupError("nenhum ponto da grade cumpre o alvo: rode src/filas.py")
    return min(float(l["multiplicador"]) for l in aptos)


def plato_de_custo(raiz: Path = RAIZ) -> tuple[float, float]:
    """Intervalo contíguo de multiplicadores, em torno do derivado, em que o TCO de 36 meses é o
    MESMO nas quatro configurações — o platô da escada de perfis.

    É a peça 4 da emenda 05: a consequência de custo é invariante a erro da aproximação do
    percentil em qualquer direção, desde que o multiplicador verdadeiro caia dentro deste
    intervalo. O corpo cita os extremos; eles são computados aqui, nunca digitados.
    """
    por_mult: dict[float, dict] = {}
    for l in ler_csv("tco-resumo.csv", raiz):
        if l["metodo"] != "iso-sla":
            continue
        m = float(l["multiplicador"])
        por_mult.setdefault(m, {})[(l["fase"], l["nuvem"])] = round(float(l["total_36m_usd"]), 4)
    grade = sorted(por_mult)
    derivado = multiplicador_iso_sla(raiz)
    alvo = por_mult[derivado]
    i = grade.index(derivado)
    inicio = fim = i
    while inicio > 0 and por_mult[grade[inicio - 1]] == alvo:
        inicio -= 1
    while fim < len(grade) - 1 and por_mult[grade[fim + 1]] == alvo:
        fim += 1
    return grade[inicio], grade[fim]


def salvar(fig, nome: str, raiz: Path = RAIZ) -> Path:
    """Grava sem metadado de data — PNG com carimbo de hora muda de bytes a cada execução, e um
    artefato que muda sem mudar de conteúdo estraga qualquer conferência futura."""
    caminho = (raiz / "output" / "figuras" / nome)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(caminho, dpi=DPI, bbox_inches="tight", pad_inches=0.02,
                metadata={"Software": None, "Creation Time": None})
    plt.close(fig)
    return caminho


# --------------------------------------------------------------------------- #
# primitivas de desenho de arquitetura                                         #
# --------------------------------------------------------------------------- #
def _largura_px(ax, texto: str, fonte: float, negrito: bool) -> float:
    """Mede o texto de verdade, com o renderizador — estimar por contagem de caracteres foi o
    que produziu a primeira versão destas figuras com rótulo transbordando a caixa."""
    r = ax.figure.canvas.get_renderer()
    t = ax.figure.text(0, 0, texto, fontsize=fonte,
                       fontweight="bold" if negrito else "normal")
    largura = t.get_window_extent(renderer=r).width
    t.remove()
    return largura


def _quebrar(ax, texto: str, limite_px: float, fonte: float, negrito: bool) -> list[str]:
    linhas, atual = [], ""
    for palavra in texto.split():
        teste = f"{atual} {palavra}".strip()
        if not atual or _largura_px(ax, teste, fonte, negrito) <= limite_px:
            atual = teste
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def _ajustar(ax, texto: str, limite_px: float, fonte: float, negrito: bool,
             max_linhas: int, piso: float = MENOR_FONTE_PT) -> tuple[list[str], float]:
    """Quebra e, se ainda não couber, encolhe a fonte — até o piso de legibilidade da banda.

    O piso NÃO é decorativo. `MENOR_FONTE_PT` é o mínimo absoluto de desenho; a banda que carrega
    o detalhe protegido pelo critério de emancipação da emenda 04 declara um piso MAIOR
    (`PISO_LEGIBILIDADE_PT`), e é isso que impede o desenho de liberar justamente o que o limiar
    existe para pegar. Quando o texto não cabe nem no piso, o certo é o desenho mudar.
    """
    fonte = max(fonte, piso)
    while True:
        linhas = _quebrar(ax, texto, limite_px, fonte, negrito)
        if len(linhas) <= max_linhas and all(
                _largura_px(ax, l, fonte, negrito) <= limite_px for l in linhas):
            return linhas, fonte
        if fonte <= piso + 1e-9:
            return linhas, fonte
        fonte = max(piso, fonte - 0.25)


ENTRELINHA = 1.28
PAD_CAIXA_PT = 5.0


def _fracao_y(ax, pontos: float) -> float:
    """Converte pontos tipográficos em fração do eixo — a altura da caixa tem de ser calculada
    a partir do texto, e não arbitrada, senão o conteúdo transborda a moldura."""
    px = pontos * ax.figure.dpi / 72.0
    return px / ax.get_window_extent(renderer=ax.figure.canvas.get_renderer()).height


def _medir(ax, titulo: str, sub: str, largura_frac: float, fonte: float,
           piso: float = MENOR_FONTE_PT) -> dict:
    limite = largura_frac * ax.get_window_extent(
        renderer=ax.figure.canvas.get_renderer()).width - 10.0
    l_tit, f_tit = _ajustar(ax, titulo, limite, fonte, True, 3, piso)
    # o subtítulo é um degrau menor que o título, mas NUNCA abaixo do piso da banda — antes
    # desta trava ele saía a 5,8 pt enquanto o piso declarado era 6,5
    l_sub, f_sub = (_ajustar(ax, sub, limite, fonte - 0.7, False, 3, piso) if sub
                    else ([], fonte))
    pontos = (len(l_tit) * f_tit + len(l_sub) * f_sub) * ENTRELINHA + PAD_CAIXA_PT
    return {"titulo": l_tit, "f_tit": f_tit, "sub": l_sub, "f_sub": f_sub,
            "altura": _fracao_y(ax, pontos)}


def caixa(ax, x, y, w, medida: dict, cor=COR["linha"], fundo="white", tracejado=False):
    """Desenha uma caixa já medida. Medir e desenhar são passos separados de propósito: a altura
    de cada faixa é o máximo das alturas das suas caixas, e isso só se sabe antes de desenhar."""
    h = medida["altura"]
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.003,rounding_size=0.008",
        linewidth=0.9, edgecolor=cor, facecolor=fundo,
        linestyle=(0, (3, 2)) if tracejado else "solid", zorder=2))
    alturas = ([_fracao_y(ax, medida["f_tit"] * ENTRELINHA)] * len(medida["titulo"])
               + [_fracao_y(ax, medida["f_sub"] * ENTRELINHA)] * len(medida["sub"]))
    topo = y + h / 2 + sum(alturas) / 2
    for i, linha in enumerate(medida["titulo"] + medida["sub"]):
        e_titulo = i < len(medida["titulo"])
        topo -= alturas[i]
        ax.text(x + w / 2, topo + alturas[i] / 2, linha, ha="center", va="center",
                fontsize=medida["f_tit"] if e_titulo else medida["f_sub"],
                color=cor if e_titulo else COR["linha"], zorder=3,
                fontweight="bold" if e_titulo else "normal")


def faixa(ax, x, y, w, h, rotulo, cor):
    ax.add_patch(Rectangle((x, y), w, h, linewidth=0, facecolor=cor, alpha=0.10, zorder=1))
    ax.text(x + 0.010, y + h - _fracao_y(ax, 3.0), rotulo, ha="left", va="top",
            fontsize=MENOR_FONTE_PT, color=cor, fontweight="bold", zorder=3)


def seta(ax, origem, destino, cor=COR["linha"], tracejada=False):
    ax.add_patch(FancyArrowPatch(
        origem, destino, arrowstyle="-|>", mutation_scale=7, linewidth=0.8, color=cor,
        linestyle=(0, (2.5, 2)) if tracejada else "solid",
        shrinkA=1.0, shrinkB=1.0, zorder=4))


def painel_vazio(ax):
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")


def desenhar_bandas(ax, bandas: list[dict], topo: float, base: float = 0.012,
                    margem: float = 0.03, folga_faixa: float = 0.016) -> list[dict]:
    """Empilha as faixas de cima para baixo, cada uma dimensionada pelo seu próprio conteúdo.

    Substituiu coordenadas fixas escritas à mão. A primeira versão desta figura usava-as e o
    texto atravessava a moldura: com fonte em pontos e caixa em fração de eixo, acertar à mão
    exige refazer tudo a cada palavra trocada. Aqui o conteúdo manda no tamanho.
    """
    x0, largura = margem, 1.0 - 2 * margem
    gap_x, gap_y = 0.014, _fracao_y(ax, 4.0)
    rotulo_h = _fracao_y(ax, MENOR_FONTE_PT * ENTRELINHA + 4.0)
    disponivel = topo - base

    # Encolher a CAIXA sem encolher a FONTE foi o defeito da versão anterior: sobrava moldura
    # pequena com texto do tamanho original atravessando-a. Quem cede aqui é a fonte, e há um
    # piso: se nem no piso couber, o desenho é que está errado e o código diz isso em voz alta.
    recuo = 0.0
    while True:
        for b in bandas:
            colunas = b.get("colunas", 1)
            w_caixa = (largura - 0.02 - (colunas - 1) * gap_x) / colunas
            piso = b.get("piso", MENOR_FONTE_PT)
            medidas = [(i, _medir(ax, t, s, w_caixa,
                                  max(b.get("fonte", 7.2) - recuo, piso), piso))
                       for i, (t, s, *_) in enumerate(b["itens"])]
            linhas = [medidas[i:i + colunas] for i in range(0, len(medidas), colunas)]
            b["_linhas"], b["_w"] = linhas, w_caixa
            b["_altura"] = (rotulo_h + sum(max(m["altura"] for _, m in ln) for ln in linhas)
                            + gap_y * (len(linhas) + 1))
        total = sum(b["_altura"] for b in bandas)
        if total + folga_faixa * (len(bandas) - 1) <= disponivel:
            break
        if all(b.get("fonte", 7.2) - recuo <= b.get("piso", MENOR_FONTE_PT) for b in bandas):
            raise ValueError(
                f"o conteúdo não cabe no painel nem no piso de {MENOR_FONTE_PT} pt "
                f"(precisa de {total:.3f} de {disponivel:.3f}): aumente a altura da figura ou "
                f"reduza o número de caixas — encolher mais seria ilegível em A4")
        recuo += 0.25

    espaco = ((disponivel - total) / (len(bandas) - 1)) if len(bandas) > 1 else 0.0
    y, limites = topo, []
    for b in bandas:
        h = b["_altura"]
        y -= h
        faixa(ax, x0, y, largura, h, b["rotulo"], b["cor"])
        limites.append((y, y + h))
        cursor = y + h - rotulo_h - gap_y
        for linha in b["_linhas"]:
            alt = max(m["altura"] for _, m in linha)
            cursor -= alt
            for j, (idx, m) in enumerate(linha):
                estilo = b.get("estilos", {}).get(idx, {})
                caixa(ax, x0 + 0.01 + j * (b["_w"] + gap_x), cursor, b["_w"],
                      dict(m, altura=alt), cor=estilo.get("cor", b["cor"]),
                      fundo=estilo.get("fundo", "white"),
                      tracejado=estilo.get("tracejado", False))
            cursor -= gap_y
        y -= espaco

    for (inf, _), (_, sup) in zip(limites[:-1], limites[1:]):
        if inf - sup > _fracao_y(ax, 4.0):
            seta(ax, (0.5, inf), (0.5, sup))

    # devolve a fonte que de fato foi usada, não a pedida: o laço de recuo acima encolhe TODAS as
    # bandas quando o painel aperta, e é contra este número — não contra a intenção — que o
    # critério de legibilidade da emenda 04 tem de ser conferido
    return [{"rotulo": b["rotulo"],
             "fonte_titulo": min(m["f_tit"] for _, m in sum(b["_linhas"], [])),
             "fonte_sub": min([m["f_sub"] for _, m in sum(b["_linhas"], []) if m["sub"]]
                              or [float("nan")])}
            for b in bandas]


# --------------------------------------------------------------------------- #
# figura 1 — arquitetura da fase 1                                             #
# --------------------------------------------------------------------------- #
def _cabecalho(ax, cor, titulo: str, sub: str) -> float:
    """Título do painel e limite superior a partir do qual as faixas começam."""
    ax.text(0.5, 0.998, titulo, ha="center", va="top", fontsize=9.5, fontweight="bold", color=cor)
    ax.text(0.5, 0.998 - _fracao_y(ax, 12.5), sub, ha="center", va="top",
            fontsize=MENOR_FONTE_PT, color=COR["linha"])
    return 0.998 - _fracao_y(ax, 24.0)


def _painel_fase1(ax, nuvem: str, titulo: str, regiao: str, s: dict):
    painel_vazio(ax)
    cor = COR[nuvem]
    topo = _cabecalho(ax, cor, titulo, f"Região {regiao} — três zonas de disponibilidade")
    return desenhar_bandas(ax, [
        {"rotulo": "SEGURANÇA DA CONTA", "cor": COR["seguranca"], "colunas": 2,
         "itens": s["seguranca"]},
        {"rotulo": "BORDA", "cor": COR["borda"], "itens": [s["borda"]]},
        {"rotulo": "APLICAÇÃO — SUB-REDE PRIVADA", "cor": cor, "itens": s["app"]},
        {"rotulo": "DADOS — SUB-REDE PRIVADA", "cor": COR["dados"], "itens": s["dados"]},
        {"rotulo": "ARMAZENAMENTO DE OBJETO", "cor": COR["borda"], "itens": [s["objeto"]]},
    ], topo=topo)


def figura_1(raiz: Path = RAIZ) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(LARGURA_A4_CM * CM, 16.0 * CM))
    fig.subplots_adjust(wspace=0.06, top=0.995, bottom=0.006, left=0.005, right=0.995)
    fig.canvas.draw()   # o ajuste de texto precisa de um renderizador vivo
    medidas = {"IBM Cloud": _painel_fase1(axes[0], "ibm", "IBM Cloud", "br-sao", {
        "seguranca": [("IAM", "papéis e privilégio mínimo"),
                      ("Key Protect", "chaves gerenciadas pelo cliente"),
                      ("Activity Tracker", "registro de auditoria da conta"),
                      ("Grupos de segurança", "e listas de controle de acesso")],
        "borda": ("Application Load Balancer", "público, TLS terminado na borda"),
        "app": [("VPC Virtual Server — famílias bxf e cxf",
                 "app-3 a app-5 — uma instância; app-1 — duas"),
                ("VPC Virtual Server — duas zonas",
                 "app-2 e app-6 — redundância exigida pelo nível de serviço"),
                ("Block Storage for VPC",
                 "volumes gen2: general-purpose e 10iops-tier")],
        "dados": [("VPC Virtual Server — duas zonas",
                   "banco-1 MySQL — alta disponibilidade"),
                  ("VPC Virtual Server — uma instância",
                   "banco-2 e banco-3, banco-4 MongoDB, banco-6 Redis"),
                  ("Bare Metal mx3-metal-16x128",
                   "banco-5 Oracle — licença própria, menor degrau é 16 núcleos"),
                  ("Backup for VPC", "30 dias; diário no banco-2; baixa latência no banco-5")],
        "objeto": ("Cloud Object Storage", "acervo de mídia e entrega ao usuário final"),
    })}
    medidas["AWS"] = _painel_fase1(axes[1], "aws", "AWS", "sa-east-1", {
        "seguranca": [("IAM", "papéis e privilégio mínimo"),
                      ("KMS", "chaves gerenciadas pelo cliente"),
                      ("CloudTrail", "registro de auditoria da conta"),
                      ("Grupos de segurança", "e listas de controle de acesso")],
        "borda": ("Application Load Balancer", "público, TLS terminado na borda"),
        "app": [("EC2 — famílias m6a e c6a",
                 "app-3 a app-5 — uma instância; app-1 — duas"),
                ("EC2 — duas zonas de disponibilidade",
                 "app-2 e app-6 — mesma redundância, por paridade"),
                ("EBS gp3", "capacidade, IOPS e vazão provisionados")],
        "dados": [("EC2 — duas zonas de disponibilidade",
                   "banco-1 MySQL — alta disponibilidade"),
                  ("EC2 — uma instância",
                   "banco-2 e banco-3, banco-4 MongoDB, banco-6 Redis"),
                  ("EC2 — família de uso geral",
                   "banco-5 Oracle — licença própria, mesma convenção"),
                  ("AWS Backup", "30 dias; diário no banco-2; baixa latência no banco-5")],
        "objeto": ("Amazon S3", "acervo de mídia e entrega ao usuário final"),
    })
    MEDICOES["figura-1-arquitetura-fase-1.png"] = medidas
    return salvar(fig, "figura-1-arquitetura-fase-1.png", raiz)


# --------------------------------------------------------------------------- #
# figura 2 — arquitetura da fase 2, com o isolamento da camada de IA           #
# --------------------------------------------------------------------------- #
def _painel_fase2(ax, nuvem: str, titulo: str, regiao: str, s: dict):
    painel_vazio(ax)
    cor = COR[nuvem]
    topo = _cabecalho(ax, cor, titulo, f"Região {regiao}")
    fora = s["ia_fora"]
    # a camada de IA é onde as duas nuvens deixam de ser equivalentes; o contorno tracejado e o
    # fundo distinto existem para que isso se veja sem depender da legenda
    return desenhar_bandas(ax, [
        {"rotulo": "SEGURANÇA E GOVERNANÇA DE DADOS", "cor": COR["seguranca"],
         "itens": [s["seguranca"]]},
        {"rotulo": "BORDA E EXECUÇÃO SEM SERVIDOR", "cor": COR["borda"],
         "itens": [s["borda"], s["serverless"]]},
        {"rotulo": "APLICAÇÃO EM CONTÊINERES", "cor": cor, "itens": [s["k8s"], s["bloco"]]},
        {"rotulo": "DADOS GERENCIADOS", "cor": COR["dados"], "colunas": 2, "itens": s["dados"]},
        {"rotulo": "CAMADA DE IA CORPORATIVA", "cor": COR["ia"], "fonte": 8.4,
         "piso": PISO_LEGIBILIDADE_PT + 0.7,   # +0,7 porque o subtítulo é um degrau abaixo
         "itens": [s["ia_prep"], s["ia"], s["ia_nota"]],
         "estilos": {1: {"cor": COR["ia"] if fora else COR["dados"], "tracejado": fora,
                         "fundo": "#FBEFEF" if fora else "#EDF4ED"},
                     2: {"cor": COR["ia"] if fora else COR["dados"]}}},
    ], topo=topo)


def figura_2(raiz: Path = RAIZ) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(LARGURA_A4_CM * CM, 17.0 * CM))
    fig.subplots_adjust(wspace=0.06, top=0.995, bottom=0.006, left=0.005, right=0.995)
    fig.canvas.draw()
    medidas = {"IBM Cloud": _painel_fase2(axes[0], "ibm", "IBM Cloud", "br-sao", {
        "seguranca": ("IAM, Key Protect e Activity Tracker",
                      "chaves do cliente, privilégio mínimo e auditoria"),
        "borda": ("Application Load Balancer", "TLS terminado na borda"),
        "serverless": ("Code Engine — app-2",
                       "duas instâncias sempre quentes contra a partida a frio"),
        "k8s": ("IBM Cloud Kubernetes Service",
                "trabalhadores bxf; plano de controle sem tarifa publicada"),
        "bloco": ("Block Storage for VPC", "volumes dos trabalhadores"),
        "dados": [("Databases for MySQL", "plano standard, alta disponibilidade"),
                  ("Databases for PostgreSQL", "criptografia em repouso"),
                  ("Databases for MongoDB", "escrita intensiva"),
                  ("Databases for Redis", "cache de baixa latência"),
                  ("Bare Metal — Oracle", "sem equivalente gerenciado"),
                  ("Cloud Object Storage", "mídia, backup e entrega")],
        "ia_prep": ("Preparação e mascaramento dos dados",
                    "executados dentro da região brasileira"),
        "ia": ("watsonx.ai — FORA de br-sao",
               "a inferência atravessa a fronteira nacional"),
        "ia_fora": True,
        "ia_nota": ("Transferência internacional de dados pessoais",
                    "regime da LGPD, art. 33 — exige salvaguarda contratual e "
                    "mascaramento antes do envio"),
    })}
    medidas["AWS"] = _painel_fase2(axes[1], "aws", "AWS", "sa-east-1", {
        "seguranca": ("IAM, KMS e CloudTrail",
                      "chaves do cliente, privilégio mínimo e auditoria"),
        "borda": ("Application Load Balancer", "TLS terminado na borda"),
        "serverless": ("Lambda — app-2",
                       "concorrência provisionada contra a partida a frio"),
        "k8s": ("Amazon EKS",
                "trabalhadores EC2; plano de controle cobrado por hora"),
        "bloco": ("EBS gp3", "volumes dos trabalhadores"),
        "dados": [("RDS for MySQL", "implantação Multi-AZ"),
                  ("RDS for PostgreSQL", "criptografia em repouso"),
                  ("DocumentDB", "escrita intensiva"),
                  ("ElastiCache for Redis", "cache de baixa latência"),
                  ("RDS for Oracle", "gerenciado, licença própria"),
                  ("Amazon S3", "mídia, backup e entrega")],
        "ia_prep": ("Preparação e mascaramento dos dados",
                    "executados dentro da região brasileira"),
        "ia": ("Amazon Bedrock — DENTRO de sa-east-1",
               "a inferência permanece em território nacional"),
        "ia_fora": False,
        "ia_nota": ("Sem transferência internacional no fluxo de inferência",
                    "o tratamento permanece sob o regime ordinário da LGPD"),
    })
    MEDICOES["figura-2-arquitetura-fase-2.png"] = medidas
    return salvar(fig, "figura-2-arquitetura-fase-2.png", raiz)


# --------------------------------------------------------------------------- #
# figura 3 — cronograma de ondas                                               #
# --------------------------------------------------------------------------- #
def figura_3(raiz: Path = RAIZ) -> Path:
    projeto, emenda = ler_json("projeto-tecnico.json", raiz), ler_json(
        "emenda-04-2026-08-13.json", raiz)
    dur = {d["onda"]: d["semanas"] for d in emenda["duracao_das_ondas"]["ondas"]}
    ondas = sorted(projeto["plano_ondas"], key=lambda o: o["onda"])
    risco_cor = {"baixo": "#7FA37F", "médio": "#D9A441", "alto": "#B4544A"}

    fig, ax = plt.subplots(figsize=(LARGURA_A4_CM * CM, 8.2 * CM))
    fig.subplots_adjust(left=0.235, right=0.995, top=0.94, bottom=0.20)
    fig.canvas.draw()
    total = sum(dur.values())
    limite_x = total * 2.15
    largura_px = ax.get_window_extent(renderer=fig.canvas.get_renderer()).width

    inicio, fim_fase1 = 0.0, None
    for i, o in enumerate(ondas):
        y = len(ondas) - 1 - i
        semanas = dur[o["onda"]]
        ax.barh(y, semanas, left=inicio, height=0.56, color=risco_cor[o["risco"]],
                edgecolor=COR["linha"], linewidth=0.5, zorder=3)
        # o rótulo vai FORA da barra: dentro, a onda de três semanas cortava o próprio número
        texto = f"{semanas} semanas — {o['conteudo']}"
        sobra = (limite_x - (inicio + semanas)) / limite_x * largura_px - 6.0
        linhas = _quebrar(ax, texto, sobra, MENOR_FONTE_PT, False)
        if len(linhas) > 2:                        # truncar em silêncio some com conteúdo selado
            raise SystemExit(f"ERRO: o rótulo da onda {o['onda']} exige {len(linhas)} linhas; "
                             "o desenho tem de mudar, não o texto")
        # fundo branco: as duas linhas tracejadas de fim de fase cruzam os rótulos, e sem a
        # máscara o leitor vê o traço atravessando os glifos (achado da auditoria externa r2)
        ax.text(inicio + semanas + 0.7, y, "\n".join(linhas), ha="left", va="center",
                fontsize=MENOR_FONTE_PT, color=COR["linha"], zorder=6, linespacing=1.25,
                bbox=dict(facecolor="white", edgecolor="none", pad=1.2))
        inicio += semanas
        if o["onda"] == 4:
            fim_fase1 = inicio

    for x, rotulo in ((fim_fase1, "fim da fase 1"), (inicio, "fim da fase 2")):
        ax.axvline(x, color=COR["borda"], linewidth=1.0, linestyle=(0, (4, 2)), zorder=5)
        ax.text(x, len(ondas) - 0.30, rotulo, ha="center", va="bottom",
                fontsize=MENOR_FONTE_PT, color=COR["borda"], fontweight="bold")

    ax.set_yticks(range(len(ondas)))
    ax.set_yticklabels([f"Onda {o['onda']} — {o['nome']}" for o in reversed(ondas)])
    ax.set_xlabel("Semanas a partir do início do programa")
    ax.set_xticks(range(0, int(total) + 5, 5))
    ax.set_xlim(0, limite_x)
    ax.set_ylim(-0.6, len(ondas) - 0.30)
    ax.grid(axis="x", color="#DDDDDD", linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    ax.legend(handles=[Line2D([], [], marker="s", linestyle="", markersize=6,
                              markerfacecolor=c, markeredgecolor=COR["linha"],
                              label=f"risco {r}") for r, c in risco_cor.items()],
              loc="upper center", bbox_to_anchor=(0.5, -0.20), frameon=False, ncol=3)
    return salvar(fig, "figura-3-cronograma-ondas.png", raiz)


# --------------------------------------------------------------------------- #
# figura 4 — TCO empilhado por item, duas nuvens x dois métodos                #
# --------------------------------------------------------------------------- #
def figura_4(raiz: Path = RAIZ) -> Path:
    mult = multiplicador_iso_sla(raiz)
    grade = ler_csv("tco-por-item-grade.csv", raiz)
    metodos = [("iso-especificacao", 1.0, "iso-especificação"),
               ("iso-sla", mult, f"iso-SLA (×{br(mult, 2)})")]

    def valor(fase, nuvem, metodo, m, item):
        for l in grade:
            if (int(l["fase"]) == fase and l["nuvem"] == nuvem and l["metodo"] == metodo
                    and abs(float(l["multiplicador"]) - m) < 1e-9 and l["item_custo"] == item):
                return float(l["usd_36m"])
        return 0.0

    itens = [i for i in dict.fromkeys(l["item_custo"] for l in grade)
             if any(valor(f, n, me, m, i) > 0 for f in (1, 2) for n in ("ibm", "aws")
                    for me, m, _ in metodos)]
    rotulo_item = {"compute": "Computação", "bloco": "Bloco", "objeto": "Objeto",
                   "egress": "Saída de dados", "premio-gerenciado": "Prêmio de gerenciado",
                   "backup": "Backup", "rede-ip-balanceador": "Rede e balanceador",
                   "ia": "Camada de IA"}

    colunas = [(f, n, me, m, rot) for f in (1, 2) for me, m, rot in metodos
               for n in ("ibm", "aws")]
    fig, ax = plt.subplots(figsize=(LARGURA_A4_CM * CM, 9.2 * CM))
    posicoes, rotulos, grupo_x = [], [], {}
    x = 0.0
    for i, (f, n, me, m, rot) in enumerate(colunas):
        if i and (f, me) != (colunas[i - 1][0], colunas[i - 1][2]):
            x += 0.55
        posicoes.append(x)
        rotulos.append(NUVEM_CURTA[n])
        grupo_x.setdefault((f, rot), []).append(x)
        x += 1.0

    for pos, (f, n, me, m, _) in zip(posicoes, colunas):
        base = 0.0
        for item in itens:
            v = valor(f, n, me, m, item)
            if v <= 0:
                continue
            ax.bar(pos, v, bottom=base, width=0.78, color=COR_ITEM.get(item, "#999999"),
                   edgecolor="white", linewidth=0.4, zorder=3)
            base += v
        ax.text(pos, base + 6000, br(base), ha="center", va="bottom", fontsize=MENOR_FONTE_PT,
                fontweight="bold", color=COR["linha"], zorder=4)

    ax.set_xticks(posicoes)
    ax.set_xticklabels(rotulos)
    for (f, rot), xs in grupo_x.items():
        ax.text(sum(xs) / len(xs), -0.105, f"Fase {f}\n{rot}", ha="center", va="top",
                fontsize=MENOR_FONTE_PT, color=COR["linha"], transform=ax.get_xaxis_transform())
    ax.set_ylabel("Custo total de propriedade em 36 meses (USD)")
    ax.yaxis.set_major_formatter(lambda v, _: br(v))
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.set_ylim(0, max(sum(valor(f, n, me, m, i) for i in itens)
                       for (f, n, me, m, _) in colunas) * 1.14)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    ax.legend(handles=[Line2D([], [], marker="s", linestyle="", markersize=6,
                              markerfacecolor=COR_ITEM.get(i, "#999999"),
                              markeredgecolor="white", label=rotulo_item.get(i, i))
                       for i in itens],
              loc="upper center", bbox_to_anchor=(0.5, -0.16), frameon=False, ncol=4)
    return salvar(fig, "figura-4-tco-empilhado.png", raiz)


NUVEM_CURTA = {"ibm": "IBM", "aws": "AWS"}


# --------------------------------------------------------------------------- #
# figura 5 — utilização x tempo de resposta (Kingman)                          #
# --------------------------------------------------------------------------- #
def figura_5(raiz: Path = RAIZ) -> Path:
    curva = ler_csv("filas-curva-kingman.csv", raiz)
    pontos = ler_csv("filas-ponto-iso-sla.csv", raiz)
    premissas = ler_json("premissas-carga.json", raiz)
    alvo = float(premissas["api_rest"]["alvo_latencia_ms"])
    cs_selado = float(premissas["api_rest"]["cv_servico"])

    fig, ax = plt.subplots(figsize=(LARGURA_A4_CM * CM, 8.6 * CM))
    cvs = sorted({float(l["cv_servico"]) for l in curva})
    tons = ["#9EB6D6", "#3B5B92", "#8C6BB1", "#5A3A78"]
    for cs, tom in zip(cvs, tons):
        pts = [(float(l["rho"]), float(l["resposta_p95_ms"])) for l in curva
               if abs(float(l["cv_servico"]) - cs) < 1e-9]
        pts.sort()
        selado = abs(cs - cs_selado) < 1e-9
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=tom,
                linewidth=1.8 if selado else 0.9, zorder=3,
                label=f"Cs = {br(cs, 1)}" + (" (premissa selada)" if selado else ""))

    ax.axhline(alvo, color=COR["alvo"], linewidth=1.1, linestyle=(0, (5, 3)), zorder=4)
    ax.text(0.012, alvo * 1.06, f"alvo do requisito especial: {br(alvo)} ms",
            fontsize=MENOR_FONTE_PT, color=COR["alvo"], va="bottom")

    chave = {float(p["multiplicador"]): p for p in pontos}
    base, derivado = chave[1.0], min((p for p in pontos if p["atende"] == "True"),
                                     key=lambda p: float(p["multiplicador"]))
    for p, rot, cor in ((base, "dimensionamento por\nespecificação (×1,00)", COR["alvo"]),
                        (derivado, f"ponto de operação iso-SLA\nderivado "
                                   f"(×{br(float(derivado['multiplicador']), 2)})", COR["dados"])):
        rho, y = float(p["rho"]), float(p["resposta_p95_ms"])
        ax.plot([rho], [y], marker="o", markersize=5.5, color=cor, zorder=6,
                markeredgecolor="white", markeredgewidth=0.8)
        ax.annotate(f"{rot}\nρ = {br(rho, 2)} · P95 = {br(y)} ms", xy=(rho, y),
                    xytext=(rho - 0.30, y * (2.5 if p is base else 3.4)),
                    fontsize=MENOR_FONTE_PT, color=cor, ha="left",
                    arrowprops=dict(arrowstyle="->", color=cor, linewidth=0.7))

    ax.set_xlabel("Utilização do servidor (ρ)")
    ax.set_ylabel("Percentil 95 do tempo de resposta (ms)")
    ax.set_yscale("log")
    ax.set_xlim(0, 0.95)
    ax.set_ylim(50, 5000)
    ax.yaxis.set_major_formatter(lambda v, _: br(v))
    ax.grid(color="#DDDDDD", linewidth=0.5, which="major", zorder=0)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    ax.legend(loc="lower right", frameon=False)
    return salvar(fig, "figura-5-utilizacao-espera.png", raiz)

def executar(raiz: Path = RAIZ) -> list[Path]:
    caminhos = [figura_1(raiz), figura_2(raiz), figura_3(raiz), figura_4(raiz), figura_5(raiz)]
    medicoes = raiz / "output" / "figuras" / "MEDICOES.json"
    medicoes.write_text(json.dumps(MEDICOES, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    return caminhos + [medicoes]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Figuras do corpo do artigo.")
    ap.add_argument("--root", type=Path, default=RAIZ)
    ap.add_argument("--medir", action="store_true", help="só mede o que já existe em disco")
    args = ap.parse_args(argv)

    caminhos = ([p for p in sorted((args.root / "output" / "figuras").glob("*.png"))]
                if args.medir else executar(args.root))
    total = 0
    for p in caminhos:
        tam = p.stat().st_size
        total += tam
        print(f"{tam / 1024:>8.1f} KB  {p.name}")
    print(f"{total / 1024:>8.1f} KB  TOTAL (teto de 4 MB é do PDF, não das figuras)")

    medidas = json.loads((args.root / "output" / "figuras" / "MEDICOES.json")
                         .read_text(encoding="utf-8"))
    print(f"\nfonte efetiva do corpo de texto, por banda "
          f"(piso absoluto {MENOR_FONTE_PT} pt; critério de emancipação "
          f"{PISO_LEGIBILIDADE_PT} pt no detalhe embutido da figura 2):")
    for figura, paineis in medidas.items():
        for painel, bandas in paineis.items():
            pior = min(b["fonte_sub"] for b in bandas)
            ia = [b["fonte_sub"] for b in bandas if b["rotulo"].startswith("CAMADA DE IA")]
            marca = f" · detalhe da IA {ia[0]:.2f} pt" if ia else ""
            print(f"  {figura[:34]:36} {painel:10} menor {pior:.2f} pt{marca}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
