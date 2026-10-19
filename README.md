# Borne Simulator — bornes de port de plaisance + portail client

Simulateur de bornes de services (électricité, eau, gaz) avec **portail web client en temps réel**,
livré en conteneur et déployé sur **Kubernetes** par **GitHub Actions**.
Toutes les données sont **générées aléatoirement** : aucun matériel n'est nécessaire.

| Brique | Technologie |
|---|---|
| Simulateur | Python 3.11+, un thread par borne |
| Messagerie | **MQTT — Eclipse Mosquitto 2** (conteneur) |
| **Base de données** | **SQLite** (une base par borne, mode WAL) — voir ci-dessous |
| Portail client | FastAPI + page HTML/CSS/JS sans dépendance (temps réel via SSE) |
| Conteneur | Docker (image non-root, healthcheck) |
| Orchestration | Kubernetes (manifestes Kustomize) |
| CI/CD | GitHub Actions : lint → tests → image → smoke test → GHCR → déploiement |

## Quelle base de données ?

**SQLite**, embarquée dans l'application (module `sqlite3` de la bibliothèque standard — pas de serveur à installer).
Elle est **formée automatiquement au premier démarrage** : `DaoSqlite.connecter()` crée le fichier, la table
`consommation`, l'index, et migre les anciennes bases (v0.1) si besoin.

- **Une base par borne** : `data/borne_A07.db`, `borne_B12.db`, `borne_C03.db` (isolation par conception).
- Table `consommation(id, id_reservation, date_debut, date_fin, quantite, ressource)`.
- Mode **WAL** : le portail lit pendant que la borne écrit.
- Sous Kubernetes les fichiers vivent sur un **PersistentVolumeClaim** (`/data`) : ils survivent aux redéploiements,
  et les cumuls reprennent là où ils s'étaient arrêtés.
- Contrepartie assumée : SQLite = **un seul écrivain** → le Deployment est à `replicas: 1` (stratégie `Recreate`).
  Pour passer à l'échelle, il suffirait d'écrire un `DaoPostgres` implémentant `IDAOConsommation` : le métier ne change pas.

## Architecture

```
            ┌────────────── Pod borne-app ──────────────┐        ┌── Pod mosquitto ──┐
Navigateur ─┤ Portail FastAPI ◄─ MQTT (abonné) ─────────┼─────►  │  Broker MQTT 1883 │
  (SSE/REST)│        │                                  │        └───────▲───────────┘
            │        └─ lecture SQLite (WAL)            │                │ publish/subscribe
            │ Bornes A07/B12/C03 (1 thread chacune) ────┼────────────────┘
            │        └─ écriture SQLite  ──► /data (PVC)│
            └───────────────────────────────────────────┘
```

Architecture en oignon conservée : `domaine/` (entités, interfaces) ← `business/` (Calculator, GestionnaireBorne) ←
`infrastructure/` (MQTT, SQLite, config, settings) et `presentation/` (API + portail). Le portail ne parle jamais
directement aux threads : il s'abonne en MQTT et envoie ses commandes en MQTT, comme tout autre client.

## Lancer en local

**Avec Docker (recommandé)** — Mosquitto + application :

```bash
docker compose up --build
# Portail : http://localhost:8080      Documentation API : http://localhost:8080/api/docs
```

**Sans Docker** (un Mosquitto doit écouter sur `localhost:1883`) :

```bash
python -m venv .venv && source .venv/bin/activate     # Windows : .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python main.py                                         # portail sur http://localhost:8080
WEB_ENABLED=false python main.py                       # bornes seules (journaux)
```

### Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `MQTT_HOST` / `MQTT_PORT` | fichiers JSON | Broker (**prioritaire** sur les JSON — c'est ce qui permet `mosquitto` en conteneur) |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | — | Identifiants MQTT |
| `DATA_DIR` | `./data` | Dossier des bases SQLite (`/data` dans l'image) |
| `CONFIG_DIR` | `./config` | Dossier de configuration JSON |
| `WEB_ENABLED` / `WEB_PORT` | `true` / `8080` | Portail web |
| `LOG_LEVEL` | `INFO` | Niveau de journalisation |

## API

| Route | Usage |
|---|---|
| `GET /` | Portail client |
| `GET /api/bornes` | État de toutes les bornes (statut, prise, ressources, coûts) |
| `GET /api/bornes/{id}/historique?limit=40` | Derniers relevés par ressource |
| `POST /api/bornes/{id}/commandes/{activer\|couper}` | Commande envoyée à la borne via MQTT (202) |
| `GET /api/stream` | Flux temps réel (Server-Sent Events) |
| `GET /api/systeme` | Moteur de base de données, nombre de relevés, broker |
| `GET /api/health` · `GET /api/ready` | Sondes liveness / readiness (Kubernetes) |

## Tests

```bash
pytest --cov                       # 43 tests, couverture ≈ 90 % (seuil CI : 80 %)
ruff check .                       # lint
./scripts/smoke_test.sh            # intégration complète sur la stack docker compose
```

Les tests unitaires n'ont besoin ni de broker ni de réseau (doublures `FauxMqtt`, SQLite temporaire).
Le **smoke test** vérifie, sur la vraie image : application prête, bornes en ligne via MQTT, **bases SQLite formées et
alimentées**, commande `couper`/`activer` aller-retour, portail servi.

## CI/CD (`.github/workflows/ci-cd.yml`)

```
push / PR ──► test (py3.11 + 3.12 : ruff, pytest, couverture ≥ 80 %)
          └─► build : image Docker ► smoke test (Mosquitto + app + SQLite) ► push GHCR (hors PR)
              └─► deploy (main / tags v*) : kubectl apply ► rollout ► vérification ► rollback si échec
```

- Sur **pull request** : lint, tests et build + smoke test, **sans** publication ni déploiement.
- Sur **main** : l'image est poussée sur `ghcr.io/<owner>/<repo>` (tags `sha-xxxxxxx`, `latest`) puis déployée **par digest**
  (immuable) — ce qui tourne en production est exactement ce qui a passé le smoke test.
- Le job de déploiement termine par une **vérification dans le pod** : application prête, broker connecté, et état de la
  base SQLite (moteur, version, nombre de relevés par fichier) — repris dans le résumé du run GitHub.

### Mise en place (une seule fois)

1. **Secret `KUBE_CONFIG`** (Settings → Secrets → Actions) : `base64 -w0 ~/.kube/config` d'un compte de service limité au namespace `borne`.
2. **Environment `production`** (Settings → Environments) : optionnel, permet d'exiger une approbation avant déploiement.
3. **Image GHCR** : rendre le package public, ou créer un `imagePullSecret` dans le namespace `borne`.
4. **Ingress** : adapter l'hôte dans `k8s/ingress.yaml` (`bornes.example.com`) ou utiliser
   `kubectl -n borne port-forward svc/borne-app 8080:80`.

### Déployer à la main

```bash
python scripts/set_image.py k8s/kustomization.yaml ghcr.io/<owner>/borne-simulator@sha256:<digest>
kubectl apply -k k8s
kubectl -n borne get pods
```

## Sécurité

- Image **non-root** (UID 10001), système de fichiers racine en lecture seule, capabilities supprimées, seccomp `RuntimeDefault`.
- En-têtes de sécurité (CSP stricte, `X-Frame-Options`, …) ; le portail n'utilise aucun script ni style externe.
- Le broker Mosquitto est en `ClusterIP` : **non exposé** hors du cluster. Il est configuré en `allow_anonymous true` pour la démo ;
  en production, activer `password_file` et fournir `MQTT_USERNAME`/`MQTT_PASSWORD` via un `Secret` Kubernetes.
- **Le portail n'a pas d'authentification** (les commandes couper/activer sont ouvertes). Avant toute exposition publique,
  placer un fournisseur d'identité devant l'Ingress (oauth2-proxy, SSO, basic-auth de l'Ingress…).

## Topics MQTT

| Sens | Topic | Contenu |
|---|---|---|
| borne → | `port/bornes/<id>/etat` (retained) | `en_ligne` / `hors_ligne` (Last Will) |
| borne → | `port/bornes/<id>/telemetrie` | relevé JSON périodique |
| → borne | `port/bornes/<id>/commandes/{activer,couper,obtenir_consommation}` | `{"correlation_id": "..."}` |
| borne → | `port/bornes/<id>/commandes/<cmd>/reponse` | réponse corrélée |
| ↔ borne | `port/bornes/<id>/config/{souhaitee,appliquee}` | accusé de configuration (non appliquée aux paramètres) |

## Comportement du simulateur

- Prise **coupée** → la borne ne consomme plus et n'enregistre plus rien (consommation instantanée = 0).
- Au redémarrage, les cumuls sont **relus depuis la base** (les compteurs ne retombent pas à zéro).
- Une erreur sur un relevé est journalisée sans arrêter le thread de la borne.
- Arrêt propre sur `SIGTERM`/`Ctrl+C` : déconnexion MQTT (statut `hors_ligne`), fermeture des bases.
- Limite : la configuration souhaitée (`config/souhaitee`) est acquittée mais pas appliquée aux paramètres actifs.
