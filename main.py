"""Point d'entrée : assemble les couches, démarre les bornes et le portail web.

    python main.py                      # bornes simulées + portail http://localhost:8080
    WEB_ENABLED=false python main.py    # bornes seules (journaux uniquement)

Toute la configuration d'exécution passe par l'environnement (voir settings.py).
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))

from business.calculator import Calculator  # noqa: E402
from business.gestionnaire_borne import GestionnaireBorne  # noqa: E402
from infrastructure.config_file import ConfigFileDAO, ConfigurationInvalide  # noqa: E402
from infrastructure.dao_sqlite import DaoSqlite  # noqa: E402
from infrastructure.mqtt_communication import MqttCommunication  # noqa: E402
from infrastructure.settings import Settings  # noqa: E402

MAX_BORNES = 5
log = logging.getLogger("BorneSimulator")


def charger_config_globale(chemin: Path) -> dict:
    """Lit config/simulator.json et valide (fail fast)."""
    if not chemin.exists():
        raise ConfigurationInvalide(f"Fichier de configuration global introuvable : {chemin}")
    try:
        config = json.loads(chemin.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigurationInvalide(f"Fichier JSON mal formé ({chemin}) : {e}") from e
    n = config.get("nombre_bornes")
    if not isinstance(n, int) or not (1 <= n <= MAX_BORNES):
        raise ConfigurationInvalide(
            f"nombre_bornes invalide ({n!r}) : il faut un entier entre 1 et {MAX_BORNES}.")
    if "broker" not in config or "hote" not in config["broker"]:
        raise ConfigurationInvalide("La configuration globale doit contenir broker.hote.")
    ids = config.get("bornes", [])
    if len(ids) < n:
        raise ConfigurationInvalide(
            f"nombre_bornes={n} mais seulement {len(ids)} identifiants listés dans 'bornes'.")
    return config


def resoudre_broker(settings: Settings, config_globale: dict, config_borne: dict) -> dict:
    """Priorité : variables d'environnement > fichier de la borne > configuration globale."""
    broker = config_globale["broker"]
    return {
        "hote": settings.mqtt_host or config_borne.get("hote") or broker["hote"],
        "port": int(settings.mqtt_port or config_borne.get("port") or broker.get("port", 1883)),
        "username": settings.mqtt_username
        or (config_borne.get("identifiants") or {}).get("username") or None,
        "password": settings.mqtt_password
        or (config_borne.get("identifiants") or {}).get("password") or None,
    }


def construire_bornes(settings: Settings, config_globale: dict, arret: threading.Event,
                      tableau_bord: dict, verrou: threading.Lock) -> list[GestionnaireBorne]:
    """Crée et démarre une borne (un thread) par identifiant activé."""
    n = config_globale["nombre_bornes"]
    gestionnaires: list[GestionnaireBorne] = []
    for id_borne in config_globale["bornes"][:n]:
        chemin_config = settings.config_dir / "bornes" / f"borne_{id_borne}.json"
        config_borne = ConfigFileDAO(chemin_config).lire()  # fail fast
        tableau_bord[id_borne] = {"statut": "DÉMARRAGE", "dernier_releve": "—"}

        dao = DaoSqlite(settings.data_dir / f"borne_{id_borne}.db")  # SA base
        calculator = Calculator(dao)
        broker = resoudre_broker(settings, config_globale, config_borne)

        def faire_maj_statut(borne: str):
            def cb(connecte: bool) -> None:
                with verrou:
                    tableau_bord[borne]["statut"] = "CONNECTÉE" if connecte else "DÉCONNECTÉE"
            return cb

        communication = MqttCommunication(
            id_borne, hote=broker["hote"], port=broker["port"],
            username=broker["username"], password=broker["password"],
            on_status_change=faire_maj_statut(id_borne))
        gestionnaire = GestionnaireBorne(config_borne, communication, dao, calculator,
                                         arret, tableau_bord, verrou)
        gestionnaire.start()  # UN THREAD NATIF PAR BORNE
        gestionnaires.append(gestionnaire)
        log.info("[%s] Thread %s démarré (broker %s:%s, base %s).", id_borne,
                 gestionnaire.name, broker["hote"], broker["port"], dao.chemin.name)
    return gestionnaires


def afficher_tableau_bord(tableau: dict, verrou: threading.Lock) -> None:
    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 74)
    print("  BORNE SIMULATOR — Tableau de bord")
    print("=" * 74)
    with verrou:
        lignes = sorted(tableau.items())
    for id_borne, infos in lignes:
        print(f"  {id_borne:<10} {infos.get('statut', '?'):<16} "
              f"Dernier relevé : {infos.get('dernier_releve', '—')}")
    print("-" * 74)
    print("  Statut de la connexion borne <-> MQTT en temps réel. Ctrl+C pour arrêter.")


def demarrer_portail(settings: Settings, config_globale: dict,
                     gestionnaires: list[GestionnaireBorne]):
    """Démarre le serveur web dans un thread dédié et le renvoie avec son thread.

    Uvicorn est volontairement lancé hors du thread principal : sinon il installe ses
    propres gestionnaires de signaux et ré-émet SIGTERM à la fin, ce qui tuerait le
    processus avant l'arrêt propre des bornes. Ici, main() reste propriétaire des signaux.
    """
    import uvicorn

    from presentation.api import creer_app
    from presentation.etat_live import EtatLive

    configs, daos = {}, {}
    for id_borne in config_globale["bornes"][:config_globale["nombre_bornes"]]:
        configs[id_borne] = ConfigFileDAO(
            settings.config_dir / "bornes" / f"borne_{id_borne}.json").lire()
        daos[id_borne] = DaoSqlite(settings.data_dir / f"borne_{id_borne}.db")
    broker = resoudre_broker(settings, config_globale, next(iter(configs.values())))
    etat = EtatLive(broker["hote"], broker["port"], broker["username"], broker["password"])
    app = creer_app(configs, etat, daos, pret=lambda: all(g.is_alive() for g in gestionnaires))
    serveur = uvicorn.Server(uvicorn.Config(app, host=settings.web_host, port=settings.web_port,
                                            log_level="warning",
                                            timeout_graceful_shutdown=5))
    thread = threading.Thread(target=serveur.run, name="Portail-Web", daemon=True)
    thread.start()
    return serveur, thread


def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s — %(message)s")
    try:
        config_globale = charger_config_globale(settings.config_dir / "simulator.json")
    except ConfigurationInvalide as e:
        log.error("Échec au démarrage (fail fast) : %s", e)
        sys.exit(1)

    niveau = (settings.niveau_log or config_globale.get("niveau_log", "INFO")).upper()
    logging.getLogger().setLevel(getattr(logging, niveau, logging.INFO))
    log.info("Démarrage du simulateur : %d borne(s), base de données : SQLite %s",
             config_globale["nombre_bornes"], DaoSqlite.version_moteur())

    arret = threading.Event()
    verrou = threading.Lock()
    tableau_bord: dict = {}
    try:
        gestionnaires = construire_bornes(settings, config_globale, arret, tableau_bord, verrou)
    except ConfigurationInvalide as e:
        log.error("Échec au démarrage (fail fast) : %s", e)
        arret.set()
        sys.exit(1)

    # SIGTERM (Kubernetes/Docker) et Ctrl+C déclenchent le même arrêt propre.
    signal.signal(signal.SIGTERM, lambda *_: arret.set())
    signal.signal(signal.SIGINT, lambda *_: arret.set())
    serveur = None
    try:
        if settings.web_enabled:
            log.info("Portail client : http://%s:%d", settings.web_host, settings.web_port)
            serveur, thread_web = demarrer_portail(settings, config_globale, gestionnaires)
        afficher = settings.console_dashboard and not settings.web_enabled and sys.stdout.isatty()
        while not arret.is_set():
            if afficher:
                afficher_tableau_bord(tableau_bord, verrou)
            arret.wait(2)
    finally:
        log.info("Arrêt demandé : signal envoyé aux %d thread(s)...", len(gestionnaires))
        arret.set()
        if serveur is not None:
            serveur.should_exit = True
            thread_web.join(timeout=10)
        for g in gestionnaires:
            g.join(timeout=5)
        log.info("Toutes les bornes sont arrêtées proprement. Au revoir.")


if __name__ == "__main__":
    main()
