#!/usr/bin/env python3
"""Fixe l'image (nom@digest) dans k8s/kustomization.yaml — utilisé par la CI.

    python scripts/set_image.py k8s/kustomization.yaml ghcr.io/org/borne-simulator@sha256:...
"""
import re
import sys


def appliquer(contenu: str, reference: str) -> str:
    nom, sep, digest = reference.partition("@")
    if not sep or not digest.startswith("sha256:"):
        raise SystemExit(f"Référence invalide (attendu nom@sha256:...) : {reference!r}")
    bloc = f"images:\n  - name: borne-simulator\n    newName: {nom}\n    digest: {digest}\n"
    resultat, n = re.subn(r"^images:.*\Z", bloc, contenu, flags=re.S | re.M)
    if n != 1:
        raise SystemExit("Section 'images:' introuvable dans le kustomization")
    return resultat


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    chemin, ref = sys.argv[1:]
    with open(chemin, encoding="utf-8") as f:
        contenu = f.read()
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(appliquer(contenu, ref))
    print(f"Image fixée : {ref}")
