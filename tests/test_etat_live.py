import json
from types import SimpleNamespace

import pytest

from presentation.etat_live import EtatLive


@pytest.fixture
def live():
    return EtatLive("localhost", 1883)


def msg(topic, corps):
    return SimpleNamespace(topic=topic, payload=json.dumps(corps).encode())


def test_etat_telemetrie_et_reponse_de_commande(live):
    v0 = live.version
    live._on_message(None, None, msg("port/bornes/A07/etat", {"statut": "en_ligne"}))
    live._on_message(None, None, msg("port/bornes/A07/telemetrie",
                                     {"prise_active": True, "ressources": {}}))
    snap = live.snapshot("A07")
    assert snap["statut"] == "en_ligne" and snap["prise_active"] is True and "maj" in snap
    live._on_message(None, None, msg("port/bornes/A07/commandes/couper/reponse",
                                     {"statut": "coupee"}))
    assert live.snapshot("A07")["prise_active"] is False
    assert live.version > v0


def test_messages_illisibles_ignores(live):
    live._on_message(None, None, SimpleNamespace(topic="port/bornes/A07/etat", payload=b"{oops"))
    live._on_message(None, None, SimpleNamespace(topic="x", payload=b"[]"))
    assert live.snapshot("A07") == {}


def test_commande_inconnue_refusee(live):
    with pytest.raises(ValueError):
        live.publier_commande("A07", "detruire")
