"""Paramètres d'exécution lus dans l'environnement (12-factor).

Les variables d'environnement l'emportent sur les fichiers JSON : la même image
Docker tourne en local, en CI et sous Kubernetes sans être reconstruite.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def _booleen(valeur: str | None, defaut: bool) -> bool:
    if valeur is None:
        return defaut
    return valeur.strip().lower() in {"1", "true", "yes", "oui", "on"}


@dataclass(frozen=True)
class Settings:
    config_dir: Path = RACINE / "config"
    data_dir: Path = RACINE / "data"
    mqtt_host: str | None = None        # prioritaire sur les fichiers JSON
    mqtt_port: int | None = None
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    niveau_log: str | None = None
    web_enabled: bool = True
    web_host: str = "0.0.0.0"
    web_port: int = 8080
    console_dashboard: bool = False     # tableau de bord terminal (mode sans web)

    @classmethod
    def from_env(cls, env: dict | None = None) -> "Settings":
        e = os.environ if env is None else env
        return cls(
            config_dir=Path(e.get("CONFIG_DIR", RACINE / "config")),
            data_dir=Path(e.get("DATA_DIR", RACINE / "data")),
            mqtt_host=e.get("MQTT_HOST") or None,
            mqtt_port=int(e["MQTT_PORT"]) if e.get("MQTT_PORT") else None,
            mqtt_username=e.get("MQTT_USERNAME") or None,
            mqtt_password=e.get("MQTT_PASSWORD") or None,
            niveau_log=(e.get("LOG_LEVEL") or None),
            web_enabled=_booleen(e.get("WEB_ENABLED"), True),
            web_host=e.get("WEB_HOST", "0.0.0.0"),
            web_port=int(e.get("WEB_PORT", "8080")),
            console_dashboard=_booleen(e.get("CONSOLE_DASHBOARD"), False),
        )
