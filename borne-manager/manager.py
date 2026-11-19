import json
import os
import sys
from datetime import datetime

from azure.iot.hub import IoTHubRegistryManager
from azure.iot.hub.models import Twin, TwinProperties

DEVICE = os.environ.get("BORNE_DEVICE_ID", "borne-001")

cs = os.environ.get("IOTHUB_SERVICE_CONNECTION_STRING")
if not cs:
    sys.exit("IOTHUB_SERVICE_CONNECTION_STRING manquante")
mgr = IoTHubRegistryManager.from_connection_string(cs)


def ecrire_desired(desired: dict, tentatives: int = 3):
    """Écrit des propriétés désirées avec l'ETag ; relit et réessaie si 412."""
    for _ in range(tentatives):
        twin = mgr.get_twin(DEVICE)                       # 1. lire (ETag courant)
        patch = Twin(properties=TwinProperties(desired=desired))
        try:
            mgr.update_twin(DEVICE, patch, twin.etag)     # 2. écrire avec l'ETag
            return
        except Exception as e:
            if "412" in str(e):                           # quelqu'un a modifié le Twin
                print("Twin modifié entre-temps, nouvelle tentative...")
                continue
            raise
    print("Échec : le Twin change trop souvent.")


def publier_tarifs(pleines: float, creuses: float, debut: str, fin: str):
    ecrire_desired({"tarifs": {
        "prixHeuresPleines": pleines,
        "prixHeuresCreuses": creuses,
        "plagesCreuses": [{"debut": debut, "fin": fin}],   # HH:mm
    }})


def ajouter_reservation(res_id: str, client_id: str, debut_iso: str, minutes: float):
    ecrire_desired({"reservations": {res_id: {
        "clientId": client_id,
        "debut": debut_iso,                                # ISO 8601 avec fuseau
        "dureeMinutes": minutes,
    }}})


def supprimer_reservation(res_id: str):
    ecrire_desired({"reservations": {res_id: None}})       # None = null = suppression


def afficher_twin():
    twin = mgr.get_twin(DEVICE)
    print("--- desired ---")
    print(json.dumps(twin.properties.desired, indent=2, default=str))
    print("--- reported ---")
    print(json.dumps(twin.properties.reported, indent=2, default=str))


def menu():
    while True:
        print("\n1 Tarifs   2 Ajouter réservation   3 Supprimer réservation")
        print("4 Afficher le Twin   0 Quitter")
        c = input("> ").strip()
        if c == "1":
            publier_tarifs(float(input("Prix pleines : ")), float(input("Prix creuses : ")),
                           input("Début creuses (HH:mm) : "), input("Fin creuses (HH:mm) : "))
        elif c == "2":
            rid = input("reservationId : ")
            cli = input("clientId : ")
            d = input("Début ISO (vide = maintenant) : ").strip() \
                or datetime.now().astimezone().isoformat(timespec="seconds")
            ajouter_reservation(rid, cli, d, float(input("Durée (min) : ")))
        elif c == "3":
            supprimer_reservation(input("reservationId : "))
        elif c == "4":
            afficher_twin()
        elif c == "0":
            break


if __name__ == "__main__":
    menu()