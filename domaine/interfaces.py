"""Interfaces (contrats) du domaine : CE DONT le métier a besoin.

Le métier dépend uniquement de ces interfaces, jamais des technologies
(paho-mqtt, sqlite3). Grâce à l'inversion de contrôle, demain un fournisseur
Azure IoT Hub implémentera ICommunication et le métier n'y verra que du feu.
"""
from abc import ABC, abstractmethod
from typing import Callable, Dict, List

from domaine.entites import Consommation


class ICommunication(ABC):
    """Contrat de communication borne <-> serveur (MQTT aujourd'hui,
    Azure IoT Hub demain)."""

    @abstractmethod
    def connect(self) -> None:
        """Établit la connexion au serveur de communication."""

    @abstractmethod
    def disconnect(self) -> None:
        """Ferme proprement la connexion (message testament inclus)."""

    @abstractmethod
    def send(self, topic: str, message: str, qos: int = 1, retain: bool = False) -> None:
        """Publie un message JSON sur un topic."""

    @abstractmethod
    def register_message_handler(self, handler: Callable[[str, str], None]) -> None:
        """Enregistre le callback appelé à chaque message reçu (topic, payload)."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Indique si la connexion est actuellement établie."""


class IConfig(ABC):
    """Accès à la configuration propre d'une borne (fichier JSON)."""

    @abstractmethod
    def lire(self) -> dict:
        """Retourne la configuration de la borne."""

    @abstractmethod
    def modifier(self, config: dict) -> None:
        """Persiste une nouvelle version de la configuration."""


class IConnect(ABC):
    """Connexion au support de persistance (ex. base SQLite)."""

    @abstractmethod
    def connecter(self) -> bool:
        """Ouvre la connexion au support de persistance."""

    @abstractmethod
    def deconnecter(self) -> None:
        """Ferme la connexion."""


class IDAOConsommation(ABC):
    """Persistance des consommations."""

    @abstractmethod
    def save(self, consommation: Consommation) -> None:
        """Enregistre une consommation."""

    @abstractmethod
    def get_all(self, id_reservation: str) -> List[Consommation]:
        """Retourne toutes les consommations d'une réservation."""

    @abstractmethod
    def get_recent(self, id_reservation: str, ressource: str, limit: int) -> List[Consommation]:
        """Retourne les `limit` dernières consommations d'une ressource,
        en ordre chronologique croissant (la plus récente en dernier)."""

    @abstractmethod
    def totaux(self, id_reservation: str) -> Dict[str, float]:
        """Retourne le cumul de quantité par ressource pour une réservation."""

    @abstractmethod
    def compter(self) -> int:
        """Nombre total de relevés stockés."""
