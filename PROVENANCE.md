# Provenance and audit report

This document is the reason to believe the numbers. It answers three questions, in order:
**what was sealed and when**, **what of that is published here and is it identical**, and
**what a reader can recompute without trusting the author**.

Nothing below is an assertion of good practice. Every claim is a hash you can recompute.

---

## 1. The sealed chain

The study sealed a hash chain over six stages, in the order in which science requires them to
happen:

```text
environment -> code -> prereg -> inputs -> data -> scores  =>  ROOT  =>  chain_head
```

Each stage is hashed as an RFC 6962 Merkle Tree Hash over `(relative path, file hash)` pairs;
the stage hashes are folded, in the fixed order above, into a single **ROOT**; each run's ROOT is
linked to the previous run's head (`chain_head = H(0x02 || prev_head || ROOT)`), which is the
Haber–Stornetta construction. The domain-separation bytes — `0x00` for a leaf, `0x01` for an
interior node, `0x02` for a chain link — are what stop a leaf from being passed off as a node.

**Thirty-four runs** were sealed between 2026-08-13 and 2026-08-15. The full ledger, hashes only, is in
[`docs/chain-ledger.tsv`](docs/chain-ledger.tsv). Three of its properties are worth reading directly,
because they are the ones that could not be faked after the fact:

| Property | How you see it in the ledger |
|---|---|
| The **pre-registration was sealed before any price existed** | in run `20260813-pre-captura`, `stage_data` is `e3b0c442…`, which is SHA-256 of the empty input — the data stage was an empty tree, while `stage_prereg` was already populated |
| The **results came after the data**, never the reverse | `stage_scores` stays `e3b0c442…` (empty) for the first eight runs, and only becomes non-empty in `20260813-e5-tco` |
| The **captured prices were never touched again** | `stage_data` is `d1221100…` in `20260813-emenda02-objeto` and in every one of the twenty-four runs that follow, up to the head |

Head of the chain at the time of publication:

| Field | Value |
|---|---|
| Run | `20260815-auditoria-externa-v23` |
| ROOT | `ff31be04d5ab3c51766f8cabcdf7ff5aba49f4036c72084c0105642e65af125f` |
| `chain_head` | `a6b8227a8e47e2f98f5522becd86f26b5c98f76d3f2b3bbfa69f8a4eca8a315f` |
| `stage_environment` | `e116b39d689216d7ee6b936adc6133dd8532071fa07ce16c39fa2c379b1e543d` |
| `stage_data` | `d1221100a76ce4e0bdd90dedd20e029d063a3b46d7a31f9bb706b63173d5ca95` |

The tool that builds the chain is an internal one and is not published; the `manifest.json` files it
writes are not published either, because they record absolute paths on the author's machine. That
would normally leave the reader with nothing but a promise — which is why the next section exists.

## 2. The bridge: what you can recompute from this repository alone

Two of the six stages are published here **byte for byte**, so their sealed hashes can be
recomputed from this repository and compared:

```bash
python3 make_provenance.py --verify
```

```text
[OK] sealed stage 'environment' recomputes to e116b39d689216d7ee6b936adc6133dd8532071fa07ce16c39fa2c379b1e543d
[OK] sealed stage 'data' recomputes to d1221100a76ce4e0bdd90dedd20e029d063a3b46d7a31f9bb706b63173d5ca95
```

- **`environment`** is the single file `env.json`, frozen at the start of the work. It is hashed as
  the literal bytes of the file, never as a live inspection of the interpreter, so it recomputes
  identically on any machine.
- **`data`** is the Merkle root over the 46 captured price bodies under `data/precos/**/*.json` —
  every one of them, not a convenient subset. `tests/test_provenance.py` asserts both the match and
  the fact that the glob covers every JSON body on disk.

`make_provenance.py` reimplements RFC 6962 in ninety lines of standard library, with known-answer
tests, so verifying does not require the internal tool. **A single changed byte in `data/` breaks
the match**, and the test suite fails.

The four remaining stages contain files that are deliberately not published — the article, the
tooling that produces it, and the pre-registration in its original Portuguese. Their hashes are
listed in the ledger for completeness, but this repository does **not** claim they can be
recomputed here. Stating that plainly is the point: the honest reading is *two stages verified,
four stages cited*.

## 3. Fresh integrity of the published tree

Independently of the sealed chain, this repository carries its own seal, computed over the files
as published:

| Artefact | What it is |
|---|---|
| `checksums.sha256` | one SHA-256 per file, verifiable with `sha256sum -c checksums.sha256` |
| `provenance.json` | the same digests plus a single `tree_hash` (RFC 6962 root over the whole tree) and the sealed-stage bridge |

`run_all.py` regenerates every CSV and every figure from the frozen bodies **and then** verifies the
checksums. On the reference environment (`env.json`) the regenerated artefacts are byte-identical to
the published ones — determinism is not asserted, it is what makes the last step of `run_all.py`
succeed.

## 4. Divergences: what is not byte-identical to the sealed copy, and why

Of the 96 files carried over from the sealed working tree, **83 are byte-identical** and **13 are
not**. Every one of the thirteen is listed here with both digests, and the machine-readable form is
[`divergences.tsv`](divergences.tsv). All 46 captured price bodies and all 4 raw HTML evidence files
are in the byte-identical group; **no captured evidence was edited**.

| File | SHA-256 sealed | SHA-256 published | Why it differs |
|---|---|---|---|
| `src/capture_prices.py` | `666e8c068918…` | `6ba17f308fc1…` | the `User-Agent` actually sent on 2026-08-13 carried the course identifier; the public copy renames it. This is precisely why the byte-for-byte identity claim is made over `data/` and not over `src/` |
| `src/run_capture.py` | `69e754769371…` | `a05e288fb4ba…` | course identifier removed from the manifest heading it writes; the published `MANIFEST.md` follows |
| `src/filas.py` | `9c56c83d958b…` | `81498a388109…` | course identifier removed from a command-line description string |
| `src/tco.py` | `cc50a36c87c4…` | `b735cce88ebc…` | idem |
| `src/figuras.py` | `1bb94162bb45…` | `f4c860e5b243…` | same string, plus two more edits: the docstring reference to the institution's style manual was made generic, and the `legendas()` function was dropped — figure captions are paragraphs of the article body, which is not published. The figures themselves are published and redraw identically |
| `configs/caso-xyz.json` | `cfc4d1cdd502…` | `27e4649317c6…` | absolute path removed; the short prose labels were rendered in English so the assignment text is not redistributed. **Every numeric field is identical**, and the sizing code reads only the numeric fields |
| `configs/projeto-tecnico.json` | `430dced8403b…` | `b8aa7c8b5517…` | the account-security plan was dropped: it is prose from the article body and no published module reads it |
| `configs/stages.json` | `8a43d9de04f9…` | `0ffe780e7e82…` | a note citing the internal state document was rewritten |
| `configs/emenda-01-…json` | `a4ea5e25fdb1…` | `9305e7dcd326…` | reference to the internal state document removed |
| `configs/emenda-05-…json` | `fe677ef77131…` | `cd661bdf5357…` | idem |
| `data/precos/MANIFEST.md` | `4a41bfa3e8ef…` | `d3199a4429fb…` | heading only; regenerate it with `python3 src/run_capture.py --manifesto` |
| `tests/test_tco.py` | `bff7e1ed09e4…` | `ea5d9d3c3a14…` | 5 cases removed — they assert over the article text and over a rendered body table, neither published |
| `tests/test_e7.py` | `7a96a9c775a3…` | `1b84f18cc43e…` | 19 cases removed — they depend on the table generator (not published) or read the figure captions |

Four executable files were **added** here and have no sealed counterpart — `run_all.py`,
`make_provenance.py`, `tests/test_provenance.py` and `tests/test_readme_numbers.py` — the public
entry point, the public integrity layer, and the tests that lock both. The documentation of this
repository (this file, the README, the methodology, the pre-registration rendering, the
reproducibility contract, ADR-001, the changelog and the citation metadata) was likewise written
for publication and has no sealed counterpart.

### What the divergences cost, stated without softening

Because five source files and two test files differ from the sealed copies, this repository
**cannot** claim that the code here is bit-identical to the code that produced the sealed results.
What it can claim, and does, is stronger than a promise and weaker than bit-identity:

1. the **evidence** (`data/`, 46 bodies, 4 HTML pages) is bit-identical and matches the sealed
   `data` stage hash;
2. the **environment** file is bit-identical and matches the sealed `environment` stage hash;
3. running the published code over that evidence reproduces every published CSV and every published
   figure **byte for byte**, which is checked by `run_all.py` at every run;
4. every difference is enumerated above with both digests, so a reader who obtains the sealed copy
   can diff it against this one and find exactly what is described.

## 5. Two seals, never confused

| Kind | What it covers | What it proves |
|---|---|---|
| **Frozen evidence** | the captured price bodies and HTML pages | non-tampering. It does **not** prove they can be captured again: the IBM Cloud `/pricing` endpoint is not versioned by date, so a capture made today returns today's numbers |
| **Reproducible derivation** | everything computed from the frozen evidence — CSV files, figures, verdicts | re-running the published code on the published evidence yields the published artefacts, byte for byte |

`run_all.py` never writes into `data/`. The capture code is published so the path can be audited and
re-run against today's catalogue, deliberately into a different directory.

## 6. How to audit this repository in five commands

```bash
sha256sum -c checksums.sha256                  # the tree is what was published
python3 make_provenance.py --verify            # + the two sealed stages recompute
python3 -m unittest discover -s tests           # every published number is asserted
python3 run_all.py --figures                   # rebuild everything, then verify again
git log --format='%H %ad %s' --date=short       # the history of this repository itself
```

---

**References for the construction.** Laurie, B., Langley, A., & Kasper, E. (2013). *Certificate
Transparency* (RFC 6962). <https://doi.org/10.17487/RFC6962> · Haber, S., & Stornetta, W. S. (1991).
How to time-stamp a digital document. *Journal of Cryptology*, 3(2), 99–111.
<https://doi.org/10.1007/BF00196791>
