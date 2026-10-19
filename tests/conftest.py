"""Doublures de test : aucun broker ni matériel nécessaire."""
import threading

import pytest

from domaine.interfaces import ICommunication
from infrastructure.dao_sqlite import DaoSqlite

CONFIG_BORNE = {
    "id_borne": "T01", "hote": "x", "port": 1883, "intervalle_releve": 1,
    "id_reservation": "RES-T01", "ressources": ["ELECTRICITE", "EAU"],
    "profil_simulation": {
        "ELECTRICITE": {"min": 1.0, "max": 2.0, "prix_unitaire_simule": 0.5},
        "EAU": {"min": 3.0, "max": 4.0, "prix_unitaire_simule": 0.01},
    },
}


class FauxMqtt(ICommunication):
    def __init__(self):
        self.envoyes: list[tuple[str, str, bool]] = []
        self.handler = None
        self.connecte = True

    def connect(self): self.connecte = True
    def disconnect(self): self.connecte = False
    def is_connected(self): return self.connecte
    def register_message_handler(self, handler): self.handler = handler

    def send(self, topic, message, qos=1, retain=False):
        self.envoyes.append((topic, message, retain))


@pytest.fixture
def dao(tmp_path):
    d = DaoSqlite(tmp_path / "t.db")
    d.connecter()
    yield d
    d.deconnecter()


@pytest.fixture
def mqtt():
    return FauxMqtt()


@pytest.fixture
def borne(dao, mqtt):
    from business.calculator import Calculator
    from business.gestionnaire_borne import GestionnaireBorne
    return GestionnaireBorne(dict(CONFIG_BORNE), mqtt, dao, Calculator(dao),
                             threading.Event(), {}, threading.Lock())
