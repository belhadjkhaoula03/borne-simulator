"""État temps réel des bornes, alimenté par MQTT (comme le ferait n'importe quel client).

Le portail ne parle JAMAIS directement aux threads des bornes : il s'abonne aux
mêmes topics que tout autre consommateur et envoie ses commandes par MQTT.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone

from paho.mqtt import client as mqtt

log = logging.getLogger(__name__)

COMMANDES = ("activer", "couper")


class EtatLive:
    def __init__(self, hote: str, port: int, username: str | None = None,
                 password: str | None = None) -> None:
        self._verrou = threading.Lock()
        self._bornes: dict[str, dict] = {}
        self._version = 0
        self._connecte = False
        self._client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                                   client_id=f"portail_{uuid.uuid4().hex[:8]}")
        if username:
            self._client.username_pw_set(username, password)
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._hote, self._port = hote, port

    # ------------------------------------------------------------ cycle de vie
    def demarrer(self) -> None:
        self._client.connect_async(self._hote, self._port, keepalive=60)
        self._client.loop_start()

    def arreter(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    # ------------------------------------------------------------------ lecture
    @property
    def connecte(self) -> bool:
        return self._connecte

    @property
    def version(self) -> int:
        """Incrémentée à chaque changement : le flux SSE n'émet que si elle bouge."""
        return self._version

    def snapshot(self, id_borne: str) -> dict:
        with self._verrou:
            return dict(self._bornes.get(id_borne, {}))

    # ------------------------------------------------------------------ commandes
    def publier_commande(self, id_borne: str, commande: str) -> str:
        if commande not in COMMANDES:
            raise ValueError(f"commande inconnue : {commande}")
        correlation = str(uuid.uuid4())
        info = self._client.publish(f"port/bornes/{id_borne}/commandes/{commande}",
                                    json.dumps({"correlation_id": correlation}), qos=1)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError("Broker MQTT injoignable")
        return correlation

    # ---------------------------------------------------------------- callbacks
    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code == 0:
            self._connecte = True
            client.subscribe([("port/bornes/+/etat", 1), ("port/bornes/+/telemetrie", 1),
                              ("port/bornes/+/commandes/+/reponse", 1)])
            log.info("Portail connecté au broker MQTT.")
        self._bump()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        self._connecte = False
        self._bump()

    def _on_message(self, client, userdata, msg) -> None:
        try:
            parties = msg.topic.split("/")
            corps = json.loads(msg.payload.decode("utf-8")) if msg.payload else {}
            if len(parties) < 4 or not isinstance(corps, dict):
                return
            id_borne, type_ = parties[2], parties[3]
            maintenant = datetime.now(timezone.utc).isoformat()
            with self._verrou:
                borne = self._bornes.setdefault(id_borne, {})
                if type_ == "etat":
                    borne["statut"] = corps.get("statut", "inconnu")
                elif type_ == "telemetrie":
                    borne["telemetrie"] = corps
                    borne["prise_active"] = corps.get("prise_active", True)
                    borne["maj"] = maintenant
                elif type_ == "commandes" and parties[-1] == "reponse":
                    statut = corps.get("statut")
                    if statut in ("active", "coupee"):
                        borne["prise_active"] = statut == "active"
            self._bump()
        except (ValueError, UnicodeDecodeError):
            log.warning("Message MQTT illisible sur %s", msg.topic)

    def _bump(self) -> None:
        with self._verrou:
            self._version += 1
