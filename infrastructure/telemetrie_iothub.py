import json

from azure.iot.device import Message


class TelemetrieIoTHub:
    def __init__(self, client, device_id):
        self._client, self._device_id = client, device_id

    def envoyer_session(self, session):
        payload = {
            "deviceId": self._device_id,
            "clientId": session.client_id,
            "sessionId": session.id,
            "consommations": [{
                "typeEnergie": consommation.type_energie,
                "energieKwh": consommation.energie_kwh,
                "dureeMinutes": consommation.duree_minutes,
                "debut": consommation.debut.isoformat(),
                "fin": consommation.fin.isoformat(),
                "tarifApplique": consommation.tarif_applique,
                "montant": consommation.montant,
            } for consommation in session.consommations],
            "montantTotal": session.montant_total,
        }
        message = Message(json.dumps(payload), content_encoding="utf-8",
                          content_type="application/json")
        message.custom_properties["typeMessage"] = "telemetrie"
        self._client.send_message(message)


class RapporteurEtatIoTHub:
    def __init__(self, client):
        self._client = client

    def rapporter(self, etat: dict) -> None:
        self._client.patch_twin_reported_properties(etat)
