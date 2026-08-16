#!/usr/bin/env python3
"""Integrity of this repository, and its link back to the sealed internal chain.

Two independent things are computed here, and they must not be confused.

1. **Fresh checksums over the published tree.** Every file tracked in this repository
   is hashed with SHA-256; the digests go to ``checksums.sha256`` and are folded into a
   single ``tree_hash`` (RFC 6962 Merkle Tree Hash over ``(relative path, file hash)``
   pairs sorted by path). This is what a reader verifies with ``--verify``: it proves
   the tree you downloaded is the tree that was published.

2. **The bridge to the sealed chain.** The study that produced this repository sealed a
   hash chain over ``environment -> code -> prereg -> inputs -> data -> scores`` with an
   internal tool that is not published. Two of those stages are published here **byte for
   byte** — the frozen environment (``env.json``) and the captured price bodies
   (``data/precos/**/*.json``) — so their stage hashes can be recomputed from this
   repository alone and compared with the values sealed in the study's run manifest.
   The remaining stages contain files that are deliberately not published (see
   ``docs/adr/ADR-001-scope-and-divergences.md``) and therefore cannot be recomputed here.

The Merkle construction follows RFC 6962 verbatim, including the domain-separation
bytes ``0x00`` for leaves and ``0x01`` for interior nodes: without them a leaf could be
passed off as an interior node (second-preimage confusion).

Usage::

    python3 make_provenance.py            # write checksums.sha256 + provenance.json
    python3 make_provenance.py --verify   # recompute and compare; non-zero on drift
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

LEAF = b"\x00"
NODE = b"\x01"

#: Stage hashes sealed by the study's internal chain, run
#: ``20260816-conteudo-r4-v26`` (ROOT ``d364fabf…``, chain head ``5507e814…``).
#: Only the stages whose files are published byte for byte are listed — the others
#: cannot be recomputed from this repository and are therefore not asserted here.
SELO_INTERNO = {
    "environment": {
        "kind": "file",
        "path": "env.json",
        "hash": "e116b39d689216d7ee6b936adc6133dd8532071fa07ce16c39fa2c379b1e543d",
    },
    "data": {
        "kind": "tree",
        "globs": ["data/precos/**/*.json"],
        "hash": "d1221100a76ce4e0bdd90dedd20e029d063a3b46d7a31f9bb706b63173d5ca95",
    },
}

#: Everything that is not source of truth for the published tree: caches, the two files
#: this script writes, and the workspace marker that is not part of the repository
#: (``.profile`` is git-ignored, so hashing it would make a fresh clone fail to verify).
IGNORAR = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".DS_Store",
           ".profile", "checksums.sha256", "provenance.json"}


def sha256_file(caminho: Path) -> str:
    """Return the SHA-256 of a file, read in one-megabyte chunks.

    Parameters
    ----------
    caminho : Path
        File to hash.

    Returns
    -------
    str
        Lowercase hexadecimal digest.
    """
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _mth(entradas: list[bytes]) -> bytes:
    """RFC 6962 Merkle Tree Hash over a list of canonical entries.

    Parameters
    ----------
    entradas : list of bytes
        Canonical leaf payloads, already in the order they must be hashed.

    Returns
    -------
    bytes
        The 32-byte tree hash. The empty list hashes to ``SHA-256("")``.
    """
    if not entradas:
        return hashlib.sha256(b"").digest()
    if len(entradas) == 1:
        return hashlib.sha256(LEAF + entradas[0]).digest()
    k = 1
    while k * 2 < len(entradas):
        k *= 2
    return hashlib.sha256(NODE + _mth(entradas[:k]) + _mth(entradas[k:])).digest()


def _entrada(caminho_rel: str, digest_hex: str) -> bytes:
    """Build the canonical Merkle entry ``relpath || 0x00 || raw file hash``.

    Parameters
    ----------
    caminho_rel : str
        Path relative to the repository root, with forward slashes.
    digest_hex : str
        Hexadecimal SHA-256 of the file contents.

    Returns
    -------
    bytes
        The canonical entry payload.
    """
    return caminho_rel.encode("utf-8") + b"\x00" + bytes.fromhex(digest_hex)


def tree_hash(pares: list[tuple[str, str]]) -> str:
    """Merkle root over ``(relative path, file hash)`` pairs, sorted by path.

    Parameters
    ----------
    pares : list of (str, str)
        Path/digest pairs; order is irrelevant, the function sorts them.

    Returns
    -------
    str
        Lowercase hexadecimal Merkle root.
    """
    return _mth([_entrada(p, h) for p, h in sorted(pares, key=lambda x: x[0])]).hex()


def arquivos(raiz: Path = RAIZ) -> list[Path]:
    """List every published file, excluding caches and the generated integrity files.

    Parameters
    ----------
    raiz : Path
        Repository root.

    Returns
    -------
    list of Path
        Sorted absolute paths.
    """
    saida = []
    for p in sorted(raiz.rglob("*")):
        if p.is_file() and not any(parte in IGNORAR for parte in p.parts):
            saida.append(p)
    return saida


def estagio_selado(nome: str, raiz: Path = RAIZ) -> str:
    """Recompute one sealed stage hash from the files published here.

    Parameters
    ----------
    nome : str
        Stage name, a key of :data:`SELO_INTERNO`.
    raiz : Path
        Repository root.

    Returns
    -------
    str
        Lowercase hexadecimal stage hash, comparable with the sealed value.
    """
    spec = SELO_INTERNO[nome]
    if spec["kind"] == "file":
        return sha256_file(raiz / spec["path"])
    pares = []
    for padrao in spec["globs"]:
        for p in sorted(raiz.glob(padrao)):
            pares.append((str(p.relative_to(raiz)), sha256_file(p)))
    return tree_hash(pares)


def construir(raiz: Path = RAIZ) -> dict:
    """Compute the full integrity record for the published tree.

    Parameters
    ----------
    raiz : Path
        Repository root.

    Returns
    -------
    dict
        Record with the per-file digests, the tree hash and the sealed-stage bridge.
    """
    pares = [(str(p.relative_to(raiz)), sha256_file(p)) for p in arquivos(raiz)]
    ponte = {}
    for nome, spec in SELO_INTERNO.items():
        obtido = estagio_selado(nome, raiz)
        ponte[nome] = {"sealed": spec["hash"], "recomputed": obtido,
                       "match": obtido == spec["hash"]}
    return {
        "hash_alg": "sha256",
        "merkle": "RFC 6962 MTH, domain separation 0x00 leaf / 0x01 node",
        "nfiles": len(pares),
        "tree_hash": tree_hash(pares),
        "sealed_chain": {
            "run_id": "20260816-conteudo-r4-v26",
            "root": "d364fabf30d3e0a3c827c70e1903417e83b9df2c3b35460662565ba91b68bdcf",
            "chain_head": "5507e814f37258d553202062f685cbeb6b0836c9ecee7be6470ef3db4458c34e",
            "stages_verifiable_here": ponte,
        },
        "files": dict(pares),
    }


def escrever(raiz: Path = RAIZ) -> dict:
    """Write ``checksums.sha256`` and ``provenance.json`` to the repository root.

    Parameters
    ----------
    raiz : Path
        Repository root.

    Returns
    -------
    dict
        The record that was written.
    """
    rec = construir(raiz)
    (raiz / "checksums.sha256").write_text(
        "".join(f"{h}  {p}\n" for p, h in sorted(rec["files"].items())), encoding="utf-8")
    (raiz / "provenance.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rec


def conferir(raiz: Path = RAIZ) -> list[str]:
    """Recompute everything and report every mismatch found.

    Parameters
    ----------
    raiz : Path
        Repository root.

    Returns
    -------
    list of str
        Human-readable problems; empty means the tree verifies.
    """
    gravado = json.loads((raiz / "provenance.json").read_text(encoding="utf-8"))
    atual = construir(raiz)
    problemas = []
    for caminho, digest in sorted(gravado["files"].items()):
        if caminho not in atual["files"]:
            problemas.append(f"missing file: {caminho}")
        elif atual["files"][caminho] != digest:
            problemas.append(f"content drift: {caminho}")
    for caminho in sorted(set(atual["files"]) - set(gravado["files"])):
        problemas.append(f"untracked file: {caminho}")
    if atual["tree_hash"] != gravado["tree_hash"]:
        problemas.append(f"tree_hash drift: {gravado['tree_hash']} -> {atual['tree_hash']}")
    for nome, ponte in atual["sealed_chain"]["stages_verifiable_here"].items():
        if not ponte["match"]:
            problemas.append(f"sealed stage '{nome}' does not match: "
                             f"{ponte['sealed']} != {ponte['recomputed']}")
    return problemas


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point.

    Parameters
    ----------
    argv : list of str, optional
        Arguments; defaults to ``sys.argv[1:]``.

    Returns
    -------
    int
        Zero on success, one on drift.
    """
    ap = argparse.ArgumentParser(description="Integrity of the published tree.")
    ap.add_argument("--verify", action="store_true",
                    help="recompute and compare instead of writing")
    args = ap.parse_args(argv)

    if args.verify:
        problemas = conferir()
        for p in problemas:
            print(f"[FAIL] {p}")
        if problemas:
            return 1
        rec = json.loads((RAIZ / "provenance.json").read_text(encoding="utf-8"))
        print(f"[OK] {rec['nfiles']} files verified")
        print(f"[OK] tree_hash {rec['tree_hash']}")
        for nome, ponte in rec["sealed_chain"]["stages_verifiable_here"].items():
            print(f"[OK] sealed stage '{nome}' recomputes to {ponte['sealed']}")
        return 0

    rec = escrever()
    print(f"[OK] {rec['nfiles']} files hashed")
    print(f"[OK] tree_hash {rec['tree_hash']}")
    for nome, ponte in rec["sealed_chain"]["stages_verifiable_here"].items():
        estado = "matches the sealed value" if ponte["match"] else "DOES NOT MATCH"
        print(f"[{'OK' if ponte['match'] else 'FAIL'}] stage '{nome}' {estado}: "
              f"{ponte['recomputed']}")
    return 0 if all(p["match"] for p in rec["sealed_chain"]["stages_verifiable_here"].values()) \
        else 1


if __name__ == "__main__":
    sys.exit(main())
