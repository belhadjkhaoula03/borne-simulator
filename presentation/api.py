"""API REST + flux temps réel (SSE) + portail client statique."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from domaine.entites import UNITES

STATIC = Path(__file__).parent / "static"
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; "
       "script-src 'self'; connect-src 'self'; frame-ancestors 'none'")


def creer_app(configs: dict[str, dict], etat, daos: dict, pret: Callable[[], bool] = lambda: True
              ) -> FastAPI:
    """`configs` : id -> config JSON de la borne ; `daos` : id -> DaoSqlite (lecture)."""

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        for dao in daos.values():
            dao.connecter()
        etat.demarrer()
        yield
        etat.arreter()
        for dao in daos.values():
            dao.deconnecter()

    app = FastAPI(title="Portail bornes — port de plaisance", version="1.0.0",
                  lifespan=lifespan, docs_url="/api/docs", redoc_url=None)

    @app.middleware("http")
    async def entetes_securite(request: Request, call_next):
        reponse = await call_next(request)
        reponse.headers["Content-Security-Policy"] = CSP
        reponse.headers["X-Content-Type-Options"] = "nosniff"
        reponse.headers["X-Frame-Options"] = "DENY"
        reponse.headers["Referrer-Policy"] = "no-referrer"
        return reponse

    def _borne(id_borne: str) -> dict:
        if id_borne not in configs:
            raise HTTPException(404, f"Borne inconnue : {id_borne}")
        return configs[id_borne]

    def _vue(id_borne: str) -> dict:
        cfg = configs[id_borne]
        live = etat.snapshot(id_borne)
        tel = live.get("telemetrie")
        totaux = None
        ressources = {}
        for res in cfg["ressources"]:
            prix = float(cfg.get("profil_simulation", {}).get(res, {})
                         .get("prix_unitaire_simule", 1.0))
            mesure = (tel or {}).get("ressources", {}).get(res)
            if mesure:
                ressources[res] = {"instantanee": mesure["quantite_instantanee"],
                                   "cumul": mesure["quantite_cumulee"],
                                   "cout": mesure["cout_cumule_simule"],
                                   "unite": mesure["unite"]}
            else:  # pas encore de télémétrie reçue : on reprend le cumul stocké en base
                if totaux is None:
                    totaux = daos[id_borne].totaux(cfg.get("id_reservation", f"RES-{id_borne}"))
                cumul = round(totaux.get(res, 0.0), 3)
                ressources[res] = {"instantanee": None, "cumul": cumul,
                                   "cout": round(cumul * prix, 4), "unite": UNITES.get(res, "m3")}
        return {"id": id_borne,
                "reservation": cfg.get("id_reservation"),
                "intervalle": cfg.get("intervalle_releve"),
                "statut": live.get("statut", "inconnu"),
                "prise_active": live.get("prise_active"),
                "dernier_releve": tel.get("horodatage") if tel else None,
                "ressources": ressources}

    def _snapshot() -> dict:
        bornes = [_vue(i) for i in configs]
        return {"broker_connecte": etat.connecte, "bornes": bornes,
                "cout_total": round(sum(r["cout"] for b in bornes
                                        for r in b["ressources"].values()), 2)}

    # ------------------------------------------------------------------ sondes
    @app.get("/api/health", tags=["exploitation"])
    def health() -> dict:
        """Liveness : le processus répond."""
        return {"status": "ok"}

    @app.get("/api/ready", tags=["exploitation"])
    def ready() -> JSONResponse:
        """Readiness : tous les threads de bornes sont vivants."""
        ok = pret()
        return JSONResponse({"status": "ready" if ok else "not_ready",
                             "broker_connecte": etat.connecte}, status_code=200 if ok else 503)

    # ------------------------------------------------------------------ données
    @app.get("/api/bornes", tags=["bornes"])
    def lister_bornes() -> dict:
        return _snapshot()

    @app.get("/api/bornes/{id_borne}/historique", tags=["bornes"])
    def historique(id_borne: str, limit: int = Query(40, ge=1, le=500)) -> dict:
        """Derniers relevés par ressource (ordre chronologique) pour tracer les courbes."""
        cfg = _borne(id_borne)
        reservation = cfg.get("id_reservation", f"RES-{id_borne}")
        return {res: [{"t": c.date_fin.isoformat(), "q": c.quantite}
                      for c in daos[id_borne].get_recent(reservation, res, limit)]
                for res in cfg["ressources"]}

    @app.post("/api/bornes/{id_borne}/commandes/{commande}", status_code=202, tags=["bornes"])
    def commander(id_borne: str, commande: Literal["activer", "couper"]) -> dict:
        """Envoie la commande à la borne via MQTT ; l'état est confirmé par sa réponse."""
        _borne(id_borne)
        try:
            return {"correlation_id": etat.publier_commande(id_borne, commande)}
        except ConnectionError as e:
            raise HTTPException(503, str(e)) from e

    @app.get("/api/systeme", tags=["exploitation"])
    def systeme() -> dict:
        """Infrastructure : moteur de base de données et volume de données."""
        bases = [{"borne": i, "fichier": d.chemin.name, "releves": d.compter()}
                 for i, d in daos.items()]
        return {"base_de_donnees": {"moteur": "SQLite", "version": daos[next(iter(daos))]
                                    .version_moteur(), "organisation": "une base par borne",
                                    "bases": bases},
                "broker": {"type": "MQTT (Eclipse Mosquitto)", "connecte": etat.connecte},
                "donnees": "simulées (aucun matériel)"}

    @app.get("/api/stream", tags=["bornes"])
    async def flux(request: Request) -> StreamingResponse:
        """Server-Sent Events : un instantané complet à chaque changement d'état."""
        async def generateur():
            derniere, ecoule = -1, 0.0
            while not await request.is_disconnected():
                if etat.version != derniere:
                    derniere = etat.version
                    yield f"event: snapshot\ndata: {json.dumps(_snapshot())}\n\n"
                    ecoule = 0.0
                elif ecoule >= 15:
                    yield ": keep-alive\n\n"
                    ecoule = 0.0
                await asyncio.sleep(0.5)
                ecoule += 0.5
        return StreamingResponse(generateur(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ------------------------------------------------------------------ portail
    @app.get("/", include_in_schema=False)
    def accueil() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
