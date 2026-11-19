import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from business.acces_borne import AccesBorne
from business.cycle_telemetrie import CycleTelemetrie
from business.rapporter_etat import RapporterEtat
from domaine.entites import (
    Borne,
    ConsommationSession,
    EtatBorne,
    ReservationCreneau,
    TarifHoraire,
)
from infrastructure.telemetrie_iothub import TelemetrieIoTHub


class AccesObserve:
    def __init__(self, borne):
        self.borne = borne
        self.verrouille = False

    def executer(self, action):
        self.verrouille = True
        try:
            return action(self.borne)
        finally:
            self.verrouille = False


def test_borne_session_et_desactivation():
    maintenant = datetime.now(timezone.utc)
    borne = Borne("B1")
    reservation = ReservationCreneau("R1", "C1", maintenant, 15)
    borne.remplacer_reservations([reservation])

    session = borne.demarrer_session(reservation, maintenant)
    session.consommations.append(ConsommationSession(
        "Electricite16A", 1.0, 10.0, maintenant, maintenant, 0.2, 0.2))

    assert session.montant_total == 0.2
    assert borne.desactiver() is True
    assert borne.session is None
    assert borne.terminer_session() is None
    assert borne.desactiver() is False
    assert borne.activer() is True
    assert borne.etat == EtatBorne.ACTIVE


def test_cycle_mesure_et_envoi_hors_verrou(monkeypatch):
    maintenant = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("business.cycle_telemetrie.datetime",
                        SimpleNamespace(now=lambda: maintenant))
    borne = Borne("B1")
    reservation = ReservationCreneau(
        "R1", "C1", maintenant - timedelta(minutes=1), 10)
    borne.remplacer_reservations([reservation])
    borne.appliquer_tarif(TarifHoraire(0.3, 0.2))
    acces = AccesObserve(borne)

    class Mesureur:
        def mesurer(self, debut, fin):
            assert debut == maintenant - timedelta(seconds=10)
            return {"Electricite16A": 0.5}

    class Calculateur:
        def calculer(self, quantite, tarif, instant):
            return 0.15

    class Envoyeur:
        session = None

        def envoyer_session(self, session):
            assert not acces.verrouille
            self.session = session

    class Rapporteur:
        appels = 0

        def executer(self):
            assert not acces.verrouille
            self.appels += 1

    envoyeur, rapporteur = Envoyeur(), Rapporteur()
    CycleTelemetrie(acces, Mesureur(), Calculateur(), envoyeur, rapporteur, 10).executer()

    assert envoyeur.session.reservation_id == "R1"
    assert envoyeur.session.consommations[0].montant == 0.15
    assert rapporteur.appels == 1


def test_cycle_termine_session_sans_reservation():
    borne = Borne("B1")
    acces = AccesBorne(borne)
    borne.session = borne.demarrer_session(
        ReservationCreneau("R1", "C1", datetime.now(timezone.utc), 10),
        datetime.now(timezone.utc))
    borne.remplacer_reservations([])
    rapports = []
    rapporteur_etat = RapporterEtat(acces, SimpleNamespace(rapporter=rapports.append))

    CycleTelemetrie(
        acces,
        SimpleNamespace(mesurer=lambda debut, fin: {}),
        SimpleNamespace(),
        SimpleNamespace(envoyer_session=lambda session: None),
        rapporteur_etat,
        10,
    ).executer()

    assert borne.session is None
    assert rapports == [{"etat": "Active", "versionDesireeTraitee": 0}]
    rapporteur_etat.executer(12)
    assert rapports[-1]["versionDesireeTraitee"] == 12


def test_rapporteur_et_telemetrie_iothub():
    maintenant = datetime.now(timezone.utc)
    session = Borne("B1").demarrer_session(
        ReservationCreneau("R1", "C1", maintenant, 5), maintenant)
    session.consommations = [ConsommationSession(
        "Electricite16A", 0.5, 5, maintenant, maintenant, 0.3, 0.15)]

    class Client:
        sent = None

        def send_message(self, message):
            self.sent = message

    client = Client()
    TelemetrieIoTHub(client, "B1").envoyer_session(session)
    payload = json.loads(client.sent.data)

    assert payload["sessionId"] == session.id
    assert payload["consommations"][0]["typeEnergie"] == "Electricite16A"
    assert payload["montantTotal"] == 0.15
    assert client.sent.custom_properties["typeMessage"] == "telemetrie"
