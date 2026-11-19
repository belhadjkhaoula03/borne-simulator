"""Création d'un client paho compatible 1.x et 2.x."""
from paho.mqtt import client as mqtt


def creer_client(client_id: str) -> mqtt.Client:
    # paho 2.x exige callback_api_version ; paho 1.x ne le connaît pas
    if hasattr(mqtt, "CallbackAPIVersion"):
        return mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
    return mqtt.Client(client_id=client_id)
