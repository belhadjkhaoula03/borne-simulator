import importlib.util
from pathlib import Path

import pytest
import yaml

spec = importlib.util.spec_from_file_location(
    "set_image", Path(__file__).parent.parent / "scripts" / "set_image.py")
set_image = importlib.util.module_from_spec(spec)
spec.loader.exec_module(set_image)

KUSTOMIZATION = (Path(__file__).parent.parent / "k8s" / "kustomization.yaml").read_text()


def test_remplace_l_image_par_le_digest():
    ref = "ghcr.io/org/borne-simulator@sha256:" + "a" * 64
    doc = yaml.safe_load(set_image.appliquer(KUSTOMIZATION, ref))
    assert doc["images"] == [{"name": "borne-simulator", "newName": "ghcr.io/org/borne-simulator",
                              "digest": "sha256:" + "a" * 64}]
    assert doc["resources"] and doc["namespace"] == "borne"     # le reste est intact


def test_refuse_une_reference_sans_digest():
    with pytest.raises(SystemExit):
        set_image.appliquer(KUSTOMIZATION, "ghcr.io/org/borne-simulator:latest")
