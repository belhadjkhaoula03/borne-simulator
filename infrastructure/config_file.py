"""Adaptateur de configuration : fichier JSON par borne (implémente IConfig).

Fail fast : toute configuration invalide lève ConfigurationInvalide et le
simulateur refuse de démarrer plutôt que de faire vivre une borne mal
configurée (modèle noté sur le schéma manuscrit).
"""
import json
from pathlib import Path

from domaine.interfaces import IConfig

# Schéma minimal exigé pour chaque fichier de borne.
CLES_MINIMALES = ("id_borne", "hote", "port", "ressources", "intervalle_releve")


class ConfigurationInvalide(Exception):
    """Levée quand un fichier de configuration est absent ou mal formé."""


class ConfigFileDAO(IConfig):
    def __init__(self, chemin: str | Path) -> None:
        self._chemin = Path(chemin)

    def lire(self) -> dict:
        if not self._chemin.exists():
            raise ConfigurationInvalide(f"Fichier de configuration introuvable : {self._chemin}")
        try:
            config = json.loads(self._chemin.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ConfigurationInvalide(f"Fichier JSON mal formé ({self._chemin}) : {e}") from e
        manquantes = [c for c in CLES_MINIMALES if c not in config]
        if manquantes:
            raise ConfigurationInvalide(f"Clés manquantes {manquantes} dans {self._chemin}")
        return config

    def modifier(self, config: dict) -> None:
        self._chemin.write_text(json.dumps(config, indent=2, ensure_ascii=False),
                                encoding="utf-8")
