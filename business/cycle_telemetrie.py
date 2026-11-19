import logging
from datetime import datetime, timedelta

from domaine.entites import ConsommationSession, EtatBorne, QuantiteEnergie

log = logging.getLogger(__name__)


class CycleTelemetrie:
    def __init__(self, acces, mesureur, calculateur, envoyeur, rapporter_etat, intervalle_s):
        self._acces, self._mesureur, self._calc = acces, mesureur, calculateur
        self._envoyeur, self._rapporter = envoyeur, rapporter_etat
        self._intervalle = intervalle_s

    def executer(self):
        maintenant = datetime.now().astimezone()
        a_envoyer, a_rapporter = self._acces.executer(
            lambda borne: self._decider(borne, maintenant))
        if a_rapporter:
            self._rapporter.executer()
        if a_envoyer:
            self._envoyeur.envoyer_session(a_envoyer)

    def _decider(self, borne, maintenant):
        if borne.etat != EtatBorne.ACTIVE:
            return None, False

        reservation = borne.reservation_active(maintenant)
        if reservation is None:
            ouverte = borne.session is not None
            borne.terminer_session()
            return None, ouverte

        if borne.tarif is None:
            log.warning("Aucun tarif reçu : pas de mesure")
            return None, False

        nouvelle = (borne.session is None
                    or borne.session.reservation_id != reservation.id)
        if nouvelle:
            borne.demarrer_session(reservation, maintenant)
            log.info("Session %s ouverte pour %s",
                     borne.session.id, reservation.client_id)

        debut = max(reservation.debut, maintenant - timedelta(seconds=self._intervalle))
        consommations = []
        for type_energie, kwh in self._mesureur.mesurer(debut, maintenant).items():
            montant = self._calc.calculer(QuantiteEnergie(kwh), borne.tarif, maintenant)
            tarif = borne.tarif.prix_a(maintenant.timetz().replace(tzinfo=None))
            consommations.append(ConsommationSession(
                type_energie,
                kwh,
                round((maintenant - debut).total_seconds() / 60, 2),
                debut,
                maintenant,
                tarif,
                montant,
            ))
        borne.session.consommations = consommations
        return borne.session, nouvelle
