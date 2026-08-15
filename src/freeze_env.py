#!/usr/bin/env python3
"""Congela o ambiente de execução em `env.json` — o genesis da cadeia de proveniência.

O estágio `environment` é o primeiro elo de `configs/stages.json`: seu hash é o dos BYTES
LITERAIS de `env.json` em disco, nunca do ambiente vivo. Isso é o que faz o ROOT recomputar
byte-idêntico em qualquer máquina, meses depois.

Regra dura: se `env.json` já existe, NÃO sobrescreve (sai 0, avisando). Reescrever o genesis
muda o ROOT em silêncio e invalida todo manifesto já selado. Re-selo é ato deliberado: `--reseal`.

Só biblioteca padrão — a decisão de escopo do repo é stdlib-only (nada a instalar para verificar).
"""

from __future__ import annotations

import argparse
import json
import platform
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

# Raiz do repo = pasta-mãe de src/. Derivar de __file__ (e não do cwd) é o que permite rodar
# este script sobre uma cópia temporária do repo nos testes.
RAIZ = Path(__file__).resolve().parent.parent

# Bibliotecas de terceiros efetivamente usadas pelo código deste repo. Hoje: nenhuma —
# captura de preços, cadeia e testes são stdlib puro. Ao adicionar uma dependência real,
# acrescente o nome de distribuição aqui e re-sele o ambiente com --reseal.
BIBLIOTECAS_USADAS: list[str] = []


def _versoes(nomes: list[str]) -> dict[str, str]:
    from importlib.metadata import PackageNotFoundError, version
    out: dict[str, str] = {}
    for nome in nomes:
        try:
            out[nome] = version(nome)
        except PackageNotFoundError:
            out[nome] = "AUSENTE"
    return out


def snapshot() -> dict:
    """Retrato do ambiente. Sem caminhos absolutos: eles não são reproduzíveis em outra
    máquina e vazariam a árvore local para dentro de um artefato selado."""
    return {
        "_natureza": "gerado",
        "_papel": "genesis da cadeia de proveniência (estágio `environment`)",
        "congelado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": {
            "versao": platform.python_version(),
            "implementacao": platform.python_implementation(),
            "compilador": platform.python_compiler(),
            "version_completa": sys.version.replace("\n", " "),
        },
        "plataforma": {
            "sistema": platform.system(),
            "release": platform.release(),
            "versao": platform.version(),
            "descricao": platform.platform(),
        },
        "arquitetura": {
            "maquina": platform.machine(),
            "processador": platform.processor(),
            "bits_ponteiro": struct.calcsize("P") * 8,
            "byte_order": sys.byteorder,
        },
        "bibliotecas": _versoes(BIBLIOTECAS_USADAS),
        "_nota_bibliotecas": (
            "Vazio por design: este repo é stdlib-only. A lista é a de bibliotecas de "
            "terceiros efetivamente importadas pelo código em src/ e tests/."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Congela env.json (genesis da cadeia).")
    ap.add_argument("--root", type=Path, default=RAIZ, help="raiz do repo (padrão: pasta-mãe de src/)")
    ap.add_argument("--reseal", action="store_true",
                    help="sobrescreve env.json deliberadamente — muda o ROOT de toda a cadeia")
    args = ap.parse_args(argv)

    destino = Path(args.root) / "env.json"
    if destino.exists() and not args.reseal:
        print(f"[SKIP] {destino.name} já existe — genesis preservado. "
              f"Use --reseal para sobrescrever de propósito (isso muda o ROOT).")
        return 0

    destino.write_text(json.dumps(snapshot(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[OK] {'re-selado' if args.reseal else 'congelado'}: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
