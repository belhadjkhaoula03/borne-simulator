"""Adaptateur SQLite : une base PAR borne (implémente IConnect + IDAOConsommation).

C'est la SEULE classe qui importe sqlite3. Le métier (Calculator,
GestionnaireBorne) ne manipule que l'interface IDAOConsommation : la base
pourra être remplacée sans toucher au métier (inversion de contrôle).

Concurrence : le thread de la borne écrit, le portail web lit (autre instance
de DaoSqlite sur le même fichier). Le mode WAL permet lecture et écriture
simultanées ; un verrou protège en plus chaque connexion, partagée entre
les threads du serveur web.
"""
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from domaine.entites import Consommation
from domaine.interfaces import IConnect, IDAOConsommation

_SCHEMA = """
CREATE TABLE IF NOT EXISTS consommation (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    id_reservation TEXT NOT NULL,
    date_debut     TEXT NOT NULL,
    date_fin       TEXT NOT NULL,
    quantite       REAL NOT NULL,
    ressource      TEXT NOT NULL DEFAULT ''
);
"""
_INDEX = ("CREATE INDEX IF NOT EXISTS idx_conso_res "
          "ON consommation (id_reservation, ressource, id);")
_COLONNES = "id, id_reservation, date_debut, date_fin, quantite, ressource"


def _vers_entite(ligne: tuple) -> Consommation:
    return Consommation(id=ligne[0], id_reservation=ligne[1],
                        date_debut=datetime.fromisoformat(ligne[2]),
                        date_fin=datetime.fromisoformat(ligne[3]),
                        quantite=ligne[4], ressource=ligne[5])


class DaoSqlite(IConnect, IDAOConsommation):
    def __init__(self, chemin_base: str | Path) -> None:
        self._chemin = Path(chemin_base)
        self._connexion: sqlite3.Connection | None = None
        self._verrou = threading.Lock()

    @property
    def chemin(self) -> Path:
        return self._chemin

    @staticmethod
    def version_moteur() -> str:
        return sqlite3.sqlite_version

    # ---------------------------------------------------------------- IConnect
    def connecter(self) -> bool:
        self._chemin.parent.mkdir(parents=True, exist_ok=True)
        self._connexion = sqlite3.connect(str(self._chemin), check_same_thread=False,
                                          timeout=10)
        self._connexion.execute("PRAGMA journal_mode=WAL")
        self._connexion.executescript(_SCHEMA)   # création auto du schéma au 1er démarrage
        self._migrer()
        self._connexion.execute(_INDEX)
        self._connexion.commit()
        return True

    def _migrer(self) -> None:
        """Ajoute la colonne `ressource` aux bases créées par la v0.1."""
        colonnes = {r[1] for r in self._connexion.execute("PRAGMA table_info(consommation)")}
        if "ressource" not in colonnes:
            self._connexion.execute(
                "ALTER TABLE consommation ADD COLUMN ressource TEXT NOT NULL DEFAULT ''")

    def deconnecter(self) -> None:
        with self._verrou:
            if self._connexion is not None:
                self._connexion.close()
                self._connexion = None

    def _conn(self) -> sqlite3.Connection:
        if self._connexion is None:
            raise RuntimeError("connecter() doit être appelé avant d'utiliser le DAO")
        return self._connexion

    # ------------------------------------------------------ IDAOConsommation
    def save(self, consommation: Consommation) -> None:
        with self._verrou:
            conn = self._conn()
            conn.execute(
                "INSERT INTO consommation"
                " (id_reservation, date_debut, date_fin, quantite, ressource)"
                " VALUES (?, ?, ?, ?, ?)",
                (consommation.id_reservation, consommation.date_debut.isoformat(),
                 consommation.date_fin.isoformat(), consommation.quantite,
                 consommation.ressource))
            conn.commit()

    def get_all(self, id_reservation: str) -> List[Consommation]:
        with self._verrou:
            curseur = self._conn().execute(
                f"SELECT {_COLONNES} FROM consommation WHERE id_reservation = ?",
                (id_reservation,))
            return [_vers_entite(ligne) for ligne in curseur.fetchall()]

    def get_recent(self, id_reservation: str, ressource: str, limit: int) -> List[Consommation]:
        with self._verrou:
            curseur = self._conn().execute(
                f"SELECT {_COLONNES} FROM consommation"
                " WHERE id_reservation = ? AND ressource = ? ORDER BY id DESC LIMIT ?",
                (id_reservation, ressource, limit))
            lignes = curseur.fetchall()
        return [_vers_entite(ligne) for ligne in reversed(lignes)]

    def totaux(self, id_reservation: str) -> Dict[str, float]:
        with self._verrou:
            curseur = self._conn().execute(
                "SELECT ressource, SUM(quantite) FROM consommation"
                " WHERE id_reservation = ? AND ressource != '' GROUP BY ressource",
                (id_reservation,))
            return {ligne[0]: float(ligne[1]) for ligne in curseur.fetchall()}

    def compter(self) -> int:
        with self._verrou:
            return int(self._conn().execute("SELECT COUNT(*) FROM consommation").fetchone()[0])
