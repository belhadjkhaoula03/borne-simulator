import logging
import os

from azure.iot.device import IoTHubDeviceClient

log = logging.getLogger(__name__)


class ConnexionIoTHub:
    def __init__(self):
        cs = os.environ.get("IOTHUB_DEVICE_CONNECTION_STRING")
        if not cs:
            raise RuntimeError("IOTHUB_DEVICE_CONNECTION_STRING manquante")
        self._client = IoTHubDeviceClient.create_from_connection_string(cs)
        self._client.on_connection_state_change = lambda: log.info(
            "Connecté : %s", self._client.connected)

    @property
    def client(self):
        return self._client

    def connecter(self):
        self._client.connect()

    def deconnecter(self):
        self._client.shutdown()