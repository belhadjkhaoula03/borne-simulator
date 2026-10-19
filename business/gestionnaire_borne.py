"""Gestionnaire de borne : cycle de vie complet d'une borne virtuelle.

CHOIX STRUCTURANT — un thread natif Python par borne (threading.Thread) :
  * le besoin est un parallélisme LOGIQUE simple et isolé (I/O réseau MQTT),
    pas un parallélisme CPU ; les threads donnent le modèle mental
    « 1 borne = 1 fil d'exécution » demandé pédagogiquement ;
  * l'isolation est par conception : chaque thread n'accède qu'à SES objets
    (sa config, sa connexion, sa base) — aucun verrou métier nécessaire ;
  * l'arrêt propre est géré par un threading.Event (pas de processus zombie).
"""
import json
import logging
import random
import threading
import uuid
from datetime import datetime, timezone

from business.calculator import Calculator
from domaine.entites import UNITES, Consommation
from domaine.interfaces import ICommunication, IDAOConsommation

log = logging.getLogger(__name__)

TOPIC_TELEMETRIE = "port/bornes/{id}/telemetrie"
TOPIC_CONFIG_APPLIQUEE = "port/bornes/{id}/config/appliquee"


class GestionnaireBorne(threading.Thread):
    """Fait vivre une borne de sa connexion à sa déconnexion propre."""

    def __init__(self, config: dict, communication: ICommunication,
                 dao_consommation: IDAOConsommation, calculator: Calculator,
                 arret: threading.Event, tableau_bord: dict,
                 verrou: threading.Lock) -> None:
        super().__init__(name=f"Thread-{config['id_borne']}", daemon=True)
        self._config = config
        self._communication = communication
        self._dao = dao_consommation
        self._calculator = calculator
        self._arret = arret            # threading.Event : arrêt propre, sans zombie
        self._tableau_bord = tableau_bord
        self._verrou = verrou          # verrou pour l'objet partagé (tableau de bord)
        self._id_borne = config["id_borne"]
        self._id_reservation = config.get("id_reservation", f"RES-{self._id_borne}")
        self._ressources = list(config.get("ressources", []))
        self._cumul = {r: 0.0 for r in self._ressources}
        self._prise_active = True

    # ------------------------------------------------------------------ cycle
    def run(self) -> None:
        """Boucle de vie : connexion -> relevés périodiques -> déconnexion."""
        self._dao.connecter()
        self._restaurer_cumul()
        self._communication.register_message_handler(self._traiter_message)
        self._communication.connect()
        intervalle = int(self._config.get("intervalle_releve", 10))
        try:
            self._cycle_releve()  # premier relevé immédiat (pratique pour la démo)
            while not self._arret.wait(intervalle):
                self._cycle_releve()
        finally:
            # Garantit la déconnexion propre même en cas d'erreur inattendue.
            log.info("[%s] Arrêt du thread : déconnexion propre.", self._id_borne)
            self._communication.disconnect()
            self._dao.deconnecter()
            self._maj_tableau({"statut": "ARRÊTÉE"})

    def _restaurer_cumul(self) -> None:
        """Reprend les cumuls déjà en base : un redémarrage ne remet pas les compteurs à zéro."""
        for res, total in self._dao.totaux(self._id_reservation).items():
            if res in self._cumul:
                self._cumul[res] = round(total, 3)

    def _cycle_releve(self) -> None:
        """Un relevé ne doit jamais tuer le thread de la borne : on journalise et on continue."""
        try:
            self._publier_releve()
        except Exception:
            log.exception("[%s] Échec du relevé (le thread continue).", self._id_borne)

    # ------------------------------------------------------------- télémetrie
    def _publier_releve(self) -> None:
        """Génère des valeurs aléatoires, les persiste et publie la télémétrie.

        Flux d'un relevé de bout en bout :
        1. minuterie (attente de l'intervalle) ; 2. lecture des valeurs aléatoires ;
        3. insertion SQLite via IDAO ; 4. Calculator disponible pour la commande ;
        5. composition du message JSON ; 6. envoi via ICommunication ;
        7. publication MQTT ; 8. journalisation + tableau de bord.
        """
        maintenant = datetime.now(timezone.utc)
        profils = self._config.get("profil_simulation", {})
        detail = {}
        for res in self._ressources:
            profil = profils.get(res, {"min": 0.0, "max": 1.0, "prix_unitaire_simule": 1.0})
            prix = float(profil.get("prix_unitaire_simule", 1.0))
            if self._prise_active:
                qte = round(random.uniform(float(profil.get("min", 0.0)),
                                           float(profil.get("max", 1.0))), 3)
                self._cumul[res] = round(self._cumul[res] + qte, 3)
                # Persistance via l'interface : le métier ne connaît jamais sqlite3.
                self._dao.save(Consommation(
                    id=None, id_reservation=self._id_reservation,
                    date_debut=maintenant, date_fin=maintenant,
                    quantite=qte, ressource=res))
            else:
                qte = 0.0  # prise coupée : plus de consommation, rien n'est enregistré
            detail[res] = {
                "quantite_instantanee": qte,
                "quantite_cumulee": self._cumul[res],
                "cout_cumule_simule": round(self._cumul[res] * prix, 4),
                "unite": UNITES.get(res, "m3"),
            }
        message = {
            "horodatage": maintenant.isoformat(),
            "borne": self._id_borne,
            "id_reservation": self._id_reservation,
            "prise_active": self._prise_active,
            "ressources": detail,
        }
        self._communication.send(TOPIC_TELEMETRIE.format(id=self._id_borne),
                                 json.dumps(message, ensure_ascii=False), qos=1)
        self._maj_tableau({"dernier_releve": maintenant.strftime("%H:%M:%S")})
        log.info("[%s] Relevé publié : %s", self._id_borne, detail)

    # --------------------------------------------------------------- messages
    def _traiter_message(self, topic: str, payload: str) -> None:
        """Callback appelé par la couche communication à chaque message reçu."""
        try:
            self._dispatcher(topic, payload)
        except Exception:
            log.exception("[%s] Erreur lors du traitement de %s", self._id_borne, topic)

    def _dispatcher(self, topic: str, payload: str) -> None:
        try:
            contenu = json.loads(payload) if payload else {}
        except json.JSONDecodeError:
            contenu = {}
        if not isinstance(contenu, dict):
            contenu = {}
        correlation = contenu.get("correlation_id", str(uuid.uuid4()))
        base = f"port/bornes/{self._id_borne}"

        if topic.endswith("config/souhaitee"):
            version = contenu.get("version", "inconnue")
            log.info("[%s] Config souhaitée reçue (version %s) : %s",
                     self._id_borne, version, contenu)
            self._communication.send(
                TOPIC_CONFIG_APPLIQUEE.format(id=self._id_borne),
                json.dumps({"version": version, "statut": "appliquee",
                            "correlation_id": correlation,
                            "horodatage": datetime.now(timezone.utc).isoformat()}),
                qos=1, retain=True)
        elif topic.endswith("commandes/obtenir_consommation"):
            try:
                quantite = self._calculator.calculer_temps_reel(self._id_reservation)
                par_ressource = self._calculator.cumul_par_ressource(self._id_reservation)
                corps = {"quantite": str(quantite), "id_reservation": self._id_reservation,
                         "cumul_par_ressource": {r: str(q) for r, q in par_ressource.items()}}
            except ValueError as e:
                corps = {"erreur": str(e)}
            corps.update({"correlation_id": correlation,
                          "horodatage": datetime.now(timezone.utc).isoformat()})
            self._communication.send(f"{base}/commandes/obtenir_consommation/reponse",
                                     json.dumps(corps, ensure_ascii=False), qos=1)
        elif topic.endswith("commandes/activer"):
            self._prise_active = True
            log.info("[%s] Commande ACTIVER reçue : prise activée.", self._id_borne)
            self._communication.send(f"{base}/commandes/activer/reponse",
                                     json.dumps({"statut": "active",
                                                 "correlation_id": correlation}), qos=1)
        elif topic.endswith("commandes/couper"):
            self._prise_active = False
            log.info("[%s] Commande COUPER reçue : prise coupée.", self._id_borne)
            self._communication.send(f"{base}/commandes/couper/reponse",
                                     json.dumps({"statut": "coupee",
                                                 "correlation_id": correlation}), qos=1)
        else:
            log.warning("[%s] Message non traité sur %s", self._id_borne, topic)

    # -------------------------------------------------------------- tableau
    def _maj_tableau(self, infos: dict) -> None:
        # Tout objet partagé entre threads passe sous threading.Lock.
        with self._verrou:
            self._tableau_bord.setdefault(self._id_borne, {}).update(infos)
