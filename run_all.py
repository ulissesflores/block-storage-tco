#!/usr/bin/env python3
"""Single entry point: regenerate every result, run the tests, verify the integrity.

The order is deliberate. Results are rebuilt **first**, from the captured price bodies
in ``data/``; only then are the tests run and the checksums verified. If any step of the
pipeline were non-deterministic, the verification at the end would fail — so a green run
is evidence that the published CSV files, the published figures and the published
checksums all come from the code in this repository.

Two tracks::

    python3 run_all.py            # Track 1: stdlib only — tables, queueing model, tests
    python3 run_all.py --figures  # Track 2: also redraws the five figures (needs matplotlib)

What this cannot do is re-capture the prices: the IBM Cloud ``/pricing`` endpoint is not
versioned by date, so a fresh capture in the future would return different numbers. The
2026-08-13 bodies in ``data/`` are frozen evidence, and their hashes are sealed
(see ``PROVENANCE.md``). ``src/capture_prices.py`` and ``src/run_capture.py`` are
published so the capture path itself can be audited and re-run against today's catalogue,
never so that it silently overwrites the frozen evidence.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def passo(titulo: str, comando: list[str]) -> bool:
    """Run one step and report it.

    Parameters
    ----------
    titulo : str
        Human-readable step name.
    comando : list of str
        Command line to execute from the repository root.

    Returns
    -------
    bool
        True when the step exited zero.
    """
    print(f"\n=== {titulo} ===", flush=True)
    r = subprocess.run(comando, cwd=RAIZ)
    if r.returncode != 0:
        print(f"[FAIL] {titulo} (exit {r.returncode})")
    return r.returncode == 0


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point.

    Parameters
    ----------
    argv : list of str, optional
        Arguments; defaults to ``sys.argv[1:]``.

    Returns
    -------
    int
        Zero when every step succeeded.
    """
    ap = argparse.ArgumentParser(description="Rebuild, test and verify everything.")
    ap.add_argument("--figures", action="store_true",
                    help="also redraw the figures (requires matplotlib)")
    args = ap.parse_args(argv)

    py = sys.executable
    etapas = [
        ("cost model (36-month TCO, four configurations, turning-point sweep)",
         [py, "src/tco.py"]),
        ("queueing model (Kingman G/G/1, iso-SLA operating point)", [py, "src/filas.py"]),
        ("counterfactual on managed-database members", [py, "src/sensibilidade_membros.py"]),
    ]
    if args.figures:
        etapas.append(("figures", [py, "src/figuras.py"]))
    etapas += [
        ("tests", [py, "-m", "unittest", "discover", "-s", "tests", "-q"]),
        ("integrity (fresh checksums + bridge to the sealed chain)",
         [py, "make_provenance.py", "--verify"]),
    ]

    for titulo, comando in etapas:
        if not passo(titulo, comando):
            return 1

    print("\n[OK] every result regenerated, every test green, integrity verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
