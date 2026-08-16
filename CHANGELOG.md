# Changelog

All notable changes to this repository are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the versioning follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] — 2026-08-16

Third round of external audit. Fixes here are metadata and prose; no captured evidence and no
computed number changed, and `environment` and `data` keep their sealed hashes.

### Fixed

- **Divergence count.** The narrative in `PROVENANCE.md` said 83 files byte-identical and 13
  divergent; the table carries 14 since the style-manual citation was sanitised.
- **Headline rounding.** The banner rounded the gap to whole dollars while the Results table below
  it carried cents. Both now carry cents, matching what the article publishes.
- **Release mechanics documented.** Two audits read the one-commit difference between the tag and
  `main` as a discrepancy. Zenodo mints the version DOI *from* the release, so the tagged tree
  cannot contain it; the backfill commit is the mechanism, and the README now says so.
- **Chain.** The ledger and the sealed-chain block name run `20260816-auditoria-r3-v25`
  (root `fa537655…`, link `f8b52f9e…`).

## [1.3.0] — 2026-08-15

Second round of external audit — seven independent reports on the same artefact. What they found
here is fixed below; no captured evidence and no computed number changed, and `environment` and
`data` keep the hashes a third party recomputes from this tree.

### Fixed

- **Framing.** The deposit notes and `ADR-001` described the article as assessed coursework
  submitted to an institution. That sentence is what links a private text to a public artefact and
  buys nothing — the scope rule already states the text is not deposited here.
- **Stale pointers.** `README.md` still folded the recomputed stage hashes into the previous run's
  ROOT, and `PROVENANCE.md` still counted thirty-two sealed runs against thirty-four in the ledger.
- **Chain.** The ledger and the sealed-chain block now name run `20260815-auditoria-r2-v24`
  (root `4c565c68…`, link `9167dcf6…`), which seals the corrected presentation strings of the
  table generator.
- **Table A2 columns.** The capacity columns carried the server's *requirement*, not the capacity of
  the selected profile, which made `postgresql-isolated-8-32` read as 6 vCPU / 24 GB. Renamed, and
  the dash rule is stated in the note.

## [1.2.0] — 2026-08-15

Round of external audit. Three independent reviewers audited the article and this repository on the
same artefact; what they found here is fixed below. No captured evidence and no computed number
changed: `environment` and `data` keep the hashes a third party recomputes from this tree.

### Fixed

- **Confidentiality.** `configs/emenda-04-2026-08-13.json` cited the institution's internal style
  manual by filename, which carried a course identifier in lowercase and survived a case-sensitive
  sanitisation sweep. The public copy now cites the rule, not the filename; the divergence is
  declared in `divergences.tsv`, and the sweep is case-insensitive from now on.
- **Published difference.** The Results table showed 97,832.16 and 80,313.87 — the rounded
  difference of the raw totals. The article publishes the subtraction of the **printed** totals,
  which is the arithmetic a reader redoes on the page: 97,832.15 and 80,313.86. The README and the
  test that locks these numbers now assert that convention.
- **Chain pointer.** `PROVENANCE.md` and `provenance.json` still named the previous run as head of
  the chain while the article cited the current one. Both now name run
  `20260815-auditoria-externa-v23` (root `ff31be04…`, link `a6b8227a…`).
- **Citation metadata.** `CITATION.cff` described `10.5281/zenodo.21955052` as the release
  candidate; Zenodo records it as v1.0.0. Relabelled, and the v1.1.0 version DOI added.

## [1.1.0] — 2026-08-15

Presentation pass on the article that this repository supports. No captured evidence, no computed
result and no figure changed: the `environment` and `data` stages keep the same hashes
(`e116b39d…`, `d1221100…`) that a third party can recompute from this tree.

### Changed

- **Chain ledger** gains run `20260815-p2r2-notas-v22` (root `f01f021c…`, link `b988abc2…`), which
  seals the edited presentation strings of the table and figure generators. The `code` stage hash
  moves; `environment` and `data` do not.
- **Divergence table** records the new sealed hash of `src/figuras.py`. The published copy of that
  file is **unchanged** — the edit touched `legendas()`, which this repository does not carry.

## [1.0.0] — 2026-08-15

First public release of the evidence and computation behind the case study.
Archived on Zenodo: concept DOI [10.5281/zenodo.21955051](https://doi.org/10.5281/zenodo.21955051), minted from the
`v1.0.0-rc1` deposit (version DOI 10.5281/zenodo.21955052).

### Added

- **Evidence.** 46 raw price bodies captured on 2026-08-13 from the IBM Cloud Global Catalog
  (`br-sao`) and the AWS Price List (`sa-east-1`), plus 4 raw HTML pages saved as evidence of what
  the public product pages served on that date. Byte-identical to the sealed copies.
- **Capture code.** Three-hop traversal of the IBM catalogue with a fail-closed guard against
  zero-valued metrics, AWS offer-file capture by streaming filter, and the second evidence path for
  pages that do not expose an API.
- **Analysis code.** 36-month cost model over ten cost items and four configurations, Kingman G/G/1
  queueing model with the operating point derived rather than assumed, managed-database
  counterfactual, and the five figures.
- **Results.** 16 CSV files and 5 figures, all regenerated by the published code; on the reference
  environment the regeneration is byte-identical.
- **Tests.** 61 cases covering the published totals, the tariff traversal with measured vectors, the
  currency separation, the distinctness of the two egress prices, the queueing known answers, the
  integrity layer, and every headline number printed in the README.
- **Integrity.** `make_provenance.py` (RFC 6962 Merkle over the tree), `checksums.sha256`,
  `provenance.json`, and a bridge that recomputes two stages of the study's sealed chain — the frozen
  environment and the captured bodies — from this repository alone.
- **Documents.** `README.md`, `METHODOLOGY.md`, `PROVENANCE.md` (audit report and divergence table),
  `PREREGISTRATION.md` (English rendering of the sealed plan), `REPRODUCIBILITY.md` (two-seal
  contract), and `docs/adr/ADR-001-scope-and-divergences.md`.

### Not included, by decision

The text of the article, its rendered tables and captions, and the toolchain that produces it. The
reasoning is in ADR-001; the twelve files that differ from their sealed counterparts are enumerated
with both digests in `PROVENANCE.md`.
