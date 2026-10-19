from __future__ import annotations

import json
import logging
from typing import Callable

from paho.mqtt import client as mqtt

from domaine.interfaces import ICommunication

log = logging.getLogger(__name__)


class MqttCommunication(ICommunication):
    def __init__(
        self,
        id_borne: str,
        hote: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
        on_status_change: Callable[[bool], None] | None = None,
    ) -> None:
        self._id_borne = id_borne
        self._hote = hote
        self._port = port
        self._username = username
        self._password = password
        self._on_status_change = on_status_change
        self._handler: Callable[[str, str], None] | None = None
        self._connected = False

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"borne_{id_borne}",
        )

        if username is not None:
            self._client.username_pw_set(username, password)

        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.enable_logger(logger=log)

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        topic_etat = f"port/bornes/{id_borne}/etat"
        self._client.will_set(
            topic_etat,
            payload=json.dumps(
                {"statut": "hors_ligne"},
                ensure_ascii=False,
            ),
            qos=1,
            retain=True,
        )

    def connect(self) -> None:
        """Connecte le client MQTT et démarre la boucle réseau."""
        try:
            self._client.connect_async(
                self._hote,
                self._port,
                keepalive=60,
            )
            self._client.loop_start()

            log.info(
                "[%s] Connexion MQTT lancée vers %s:%s",
                self._id_borne,
                self._hote,
                self._port,
            )
        except Exception as exc:
            self._connected = False

            if self._on_status_change is not None:
                self._on_status_change(False)

            raise RuntimeError(
                f"Connexion MQTT impossible pour borne "
                f"{self._id_borne}: {exc}"
            ) from exc

    def disconnect(self) -> None:
        """Publie le statut hors ligne et déconnecte le client."""
        try:
            if self._client.is_connected():
                info = self._client.publish(
                    f"port/bornes/{self._id_borne}/etat",
                    json.dumps(
                        {"statut": "hors_ligne"},
                        ensure_ascii=False,
                    ),
                    qos=1,
                    retain=True,
                )

                info.wait_for_publish(timeout=2)
                self._client.disconnect()

        except Exception as exc:
            log.warning(
                "[%s] Déconnexion MQTT non propre : %s",
                self._id_borne,
                exc,
            )
        finally:
            self._connected = False
            self._client.loop_stop()

            if self._on_status_change is not None:
                self._on_status_change(False)

    def send(
        self,
        topic: str,
        message: str,
        qos: int = 1,
        retain: bool = False,
    ) -> None:
        """Publie un message MQTT."""
        if not self._client.is_connected():
            log.warning(
                "[%s] Envoi impossible sans connexion MQTT : %s",
                self._id_borne,
                topic,
            )
            return

        self._client.publish(
            topic,
            message,
            qos=qos,
            retain=retain,
        )

    def register_message_handler(
        self,
        handler: Callable[[str, str], None],
    ) -> None:
        """Enregistre le gestionnaire des messages reçus."""
        self._handler = handler

    def is_connected(self) -> bool:
        """Retourne l'état de connexion au broker."""
        return self._client.is_connected()

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata,
        flags,
        reason_code,
        properties,
    ) -> None:
        if reason_code == 0:
            self._connected = True

            if self._on_status_change is not None:
                self._on_status_change(True)

            client.subscribe(
                f"port/bornes/{self._id_borne}/commandes/+",
                qos=1,
            )
            client.subscribe(
                f"port/bornes/{self._id_borne}/config/souhaitee",
                qos=1,
            )
            client.publish(
                f"port/bornes/{self._id_borne}/etat",
                json.dumps(
                    {"statut": "en_ligne"},
                    ensure_ascii=False,
                ),
                qos=1,
                retain=True,
            )

            log.info(
                "[%s] Connecté à MQTT. Abonnements enregistrés.",
                self._id_borne,
            )
        else:
            self._connected = False

            if self._on_status_change is not None:
                self._on_status_change(False)

            log.warning(
                "[%s] Échec de connexion MQTT : %s",
                self._id_borne,
                reason_code,
            )

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata,
        disconnect_flags,
        reason_code,
        properties,
    ) -> None:
        self._connected = False

        if self._on_status_change is not None:
            self._on_status_change(False)

        if reason_code != 0:
            log.warning(
                "[%s] Déconnexion MQTT (reason_code=%s). "
                "Reconnexion automatique en cours.",
                self._id_borne,
                reason_code,
            )
        else:
            log.info("[%s] Déconnexion propre MQTT.", self._id_borne)

    def _on_message(
        self,
        client: mqtt.Client,
        userdata,
        msg: mqtt.MQTTMessage,
    ) -> None:
        if self._handler is None:
            return

        payload = (
            msg.payload.decode("utf-8", errors="replace")
            if msg.payload
            else ""
        )

        self._handler(msg.topic, payload)
