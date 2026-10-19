import pytest
from fastapi.testclient import TestClient

from presentation.api import creer_app
from tests.conftest import CONFIG_BORNE


class FauxEtat:
    def __init__(self):
        self.connecte, self.version, self.commandes = True, 1, []
        self.etat = {}

    def demarrer(self): pass
    def arreter(self): pass
    def snapshot(self, id_borne): return self.etat.get(id_borne, {})

    def publier_commande(self, id_borne, commande):
        if not self.connecte:
            raise ConnectionError("Broker MQTT injoignable")
        self.commandes.append((id_borne, commande))
        return "corr-1"


@pytest.fixture
def etat():
    return FauxEtat()


@pytest.fixture
def client(dao, etat):
    app = creer_app({"T01": CONFIG_BORNE}, etat, {"T01": dao})
    with TestClient(app) as c:
        yield c


def test_sondes(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/ready").status_code == 200


def test_readiness_echoue_si_thread_mort(dao, etat):
    app = creer_app({"T01": CONFIG_BORNE}, etat, {"T01": dao}, pret=lambda: False)
    with TestClient(app) as c:
        assert c.get("/api/ready").status_code == 503
        assert c.get("/api/health").status_code == 200       # liveness indépendante


def test_bornes_sans_telemetrie_reprend_les_totaux_en_base(client, dao):
    from datetime import datetime, timezone

    from domaine.entites import Consommation
    t = datetime.now(timezone.utc)
    dao.save(Consommation(None, "RES-T01", t, t, 10.0, "EAU"))
    data = client.get("/api/bornes").json()
    eau = data["bornes"][0]["ressources"]["EAU"]
    assert eau == {"instantanee": None, "cumul": 10.0, "cout": 0.1, "unite": "litres"}
    assert data["bornes"][0]["statut"] == "inconnu"


def test_bornes_avec_telemetrie_live(client, etat):
    etat.etat["T01"] = {"statut": "en_ligne", "prise_active": False, "telemetrie": {
        "horodatage": "2026-01-01T00:00:00+00:00",
        "ressources": {"EAU": {"quantite_instantanee": 1.0, "quantite_cumulee": 5.0,
                               "cout_cumule_simule": 0.05, "unite": "litres"}}}}
    b = client.get("/api/bornes").json()["bornes"][0]
    assert b["statut"] == "en_ligne" and b["prise_active"] is False
    assert b["ressources"]["EAU"]["cumul"] == 5.0
    assert b["ressources"]["ELECTRICITE"]["cumul"] == 0.0    # absente de la télémétrie -> base


def test_historique(client, dao):
    from datetime import datetime, timezone

    from domaine.entites import Consommation
    t = datetime.now(timezone.utc)
    for q in (1, 2, 3):
        dao.save(Consommation(None, "RES-T01", t, t, q, "EAU"))
    h = client.get("/api/bornes/T01/historique?limit=2").json()
    assert [p["q"] for p in h["EAU"]] == [2, 3] and h["ELECTRICITE"] == []
    assert client.get("/api/bornes/T01/historique?limit=0").status_code == 422
    assert client.get("/api/bornes/NOPE/historique").status_code == 404


def test_commande(client, etat):
    r = client.post("/api/bornes/T01/commandes/couper")
    assert r.status_code == 202 and r.json() == {"correlation_id": "corr-1"}
    assert etat.commandes == [("T01", "couper")]


def test_commande_invalide_ou_borne_inconnue(client):
    assert client.post("/api/bornes/T01/commandes/exploser").status_code == 422
    assert client.post("/api/bornes/NOPE/commandes/couper").status_code == 404


def test_commande_broker_indisponible(client, etat):
    etat.connecte = False
    assert client.post("/api/bornes/T01/commandes/couper").status_code == 503


def test_systeme_indique_le_moteur_de_base_de_donnees(client):
    s = client.get("/api/systeme").json()
    assert s["base_de_donnees"]["moteur"] == "SQLite"
    assert s["base_de_donnees"]["bases"][0] == {"borne": "T01", "fichier": "t.db", "releves": 0}


def test_portail_et_entetes_de_securite(client):
    r = client.get("/")
    assert r.status_code == 200 and "Portail client" in r.text
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"
    assert client.get("/static/app.js").status_code == 200
