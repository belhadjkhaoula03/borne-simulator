"""Réception des propriétés désirées du Device Twin (étape 8)."""
import logging
from datetime import datetime, time

from domaine.entites import PlageHoraire, TarifHoraire, ReservationCreneau
from domaine.proprietes_desirees import ProprietesDesirees

log = logging.getLogger(__name__)


def convertir(desired: dict) -> ProprietesDesirees:
    """Convertit le JSON 'desired' du Twin en objets du domaine.
    Fonction pure : testable sans Azure."""
    version = desired.get("$version", 0)

    tarif = None
    t = desired.get("tarifs")
    if t:
        plages = tuple(
            PlageHoraire(time.fromisoformat(p["debut"]),
                         time.fromisoformat(p["fin"]))
            for p in t.get("plagesCreuses", [])
        )
        tarif = TarifHoraire(t["prixHeuresPleines"], t["prixHeuresCreuses"], plages)

    reservations = []
    for rid, r in (desired.get("reservations") or {}).items():
        if r is None:                       # réservation supprimée : ignorée
            continue
        reservations.append(ReservationCreneau(
            id=rid,
            client_id=r["clientId"],
            debut=datetime.fromisoformat(r["debut"]),
            duree_minutes=r["dureeMinutes"],
        ))
    return ProprietesDesirees(tarif, tuple(reservations), version)


class RecepteurTwinIoTHub:
    def __init__(self, client):
        self._client = client

    def demarrer(self, on_nouvelle_config):
        # 1. s'abonner d'abord, pour ne manquer aucune modification
        self._client.on_twin_desired_properties_patch_received = \
            lambda patch: self._lire(on_nouvelle_config)
        # 2. lire au démarrage : récupère ce qui a changé hors ligne
        self._lire(on_nouvelle_config)

    def _lire(self, on_nouvelle_config):
        twin = self._client.get_twin()      # toujours le Twin COMPLET
        on_nouvelle_config(convertir(twin.get("desired", {})))