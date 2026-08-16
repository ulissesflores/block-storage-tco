# Reproducibility

## Two seals, and the difference between them

| Kind | Covers | Proves | Does **not** prove |
|---|---|---|---|
| **Frozen evidence** | `data/precos/**` (46 JSON bodies) and `data/evidencia/**` (4 HTML pages) | that these bytes are the bytes served on 2026-08-13, unaltered since | that the same request today returns the same bytes |
| **Reproducible derivation** | everything computed from the frozen evidence: 16 CSV files and 5 figures | that the published code, run on the published evidence, yields the published artefacts | anything about the providers' current prices |

Conflating the two is the usual way a repository over-claims. The IBM Cloud `/pricing` endpoint is
**not versioned by date**: a capture made today returns today's catalogue and cannot be compared byte
for byte with the frozen bodies. That is precisely why the bodies are frozen, hashed, and sealed —
and why `run_all.py` never writes into `data/`.

## Track 1 — standard library only (≈2 seconds)

```bash
python3 run_all.py
```

Rebuilds the cost model and the queueing model; runs the whole
test suite; verifies `checksums.sha256` and the bridge to the sealed chain. No third-party package
is imported at any point of this track — the three figure-geometry cases, which read constants
from the plotting module, report as skipped and everything else runs.

## Track 2 — with figures

```bash
python3 -m pip install -r requirements.txt
python3 run_all.py --figures
```

Additionally redraws the five figures. This is the only step that needs `matplotlib`.

> **Honest note about `env.json`.** The frozen environment file records an empty third-party library
> list, because it was frozen before the figure code entered the tree; `src/figuras.py` imports
> `matplotlib`. The file is the genesis of the provenance chain and is **not** re-sealed to tidy this
> up — re-sealing would change every downstream hash and rewrite history. The discrepancy is
> declared here instead, which is the whole point of freezing a genesis: you live with what it says.

## What re-running is expected to produce

On the reference environment (CPython 3.14 on macOS arm64, `env.json`) every regenerated CSV and every
regenerated PNG is **byte-identical** to the published one, which is why `run_all.py` can end with a
checksum verification rather than a tolerance comparison.

On a different interpreter, platform or `matplotlib` version, the CSV files should remain identical —
they are plain arithmetic over the frozen bodies, with no randomness, no parallelism and no
locale-dependent formatting — while the PNG bytes may differ, because font rasterisation and library
version affect the encoder. If that happens, the CSV verification is the one that matters and the
figures can be regenerated locally.

## What cannot be re-run

1. **The price capture.** `src/capture_prices.py`, `src/run_capture.py` and `src/capture_manual.py`
   are published so the path can be **audited** and re-run against today's catalogue. Their output is
   not comparable to the frozen evidence, and nothing in this repository pretends otherwise.
2. **The three-hop traversal against a moving catalogue.** The known-answer tests pin the vectors
   measured on 2026-08-13; they will keep passing because they read the frozen bodies, not the network.
3. **The article.** The text of the study is not part of this repository — see
   `docs/adr/ADR-001-scope-and-divergences.md`.

## Determinism contract

- No random number is drawn anywhere in the pipeline; there is no seed to set.
- No step depends on wall-clock time, locale, environment variables or network access.
- Figures are written by a single deterministic pass; the geometry is measured and asserted, and the
  generator **aborts** rather than silently shrinking a label below the legibility floor.
- `run_all.py` regenerates results **before** verifying integrity, so any drift fails the run instead
  of being discovered later.
