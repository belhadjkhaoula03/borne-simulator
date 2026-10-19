#!/usr/bin/env bash
# Test d'intégration de bout en bout sur la stack docker compose (mosquitto + app).
# Prouve : app démarrée, broker joint, bases SQLite formées et alimentées, commande MQTT OK.
set -euo pipefail

URL="${URL:-http://localhost:8080}"
TIMEOUT="${TIMEOUT:-90}"
COMPOSE="${COMPOSE:-docker compose}"

fail() { echo "❌ $*"; $COMPOSE logs --tail=60 || true; exit 1; }
jq_py() { python3 -c "import sys,json; d=json.load(sys.stdin); print($1)"; }

echo "▶ 1/5 Attente de l'application (readiness)…"
for _ in $(seq 1 "$TIMEOUT"); do
  curl -fs "$URL/api/ready" >/dev/null 2>&1 && break
  sleep 1
done
curl -fs "$URL/api/ready" >/dev/null || fail "l'application n'est pas prête après ${TIMEOUT}s"

echo "▶ 2/5 Toutes les bornes en ligne via MQTT…"
for _ in $(seq 1 "$TIMEOUT"); do
  n=$(curl -fs "$URL/api/bornes" | jq_py "sum(1 for b in d['bornes'] if b['statut']=='en_ligne' and b['dernier_releve'])" || echo 0)
  total=$(curl -fs "$URL/api/bornes" | jq_py "len(d['bornes'])" || echo 99)
  [ "$n" = "$total" ] && [ "$total" != "0" ] && break
  sleep 1
done
[ "$n" = "$total" ] || fail "seulement $n/$total bornes en ligne avec télémétrie"
echo "   $n/$total bornes en ligne"

echo "▶ 3/5 Base de données formée et alimentée…"
curl -fs "$URL/api/systeme" | jq_py "d['base_de_donnees']['moteur']" | grep -qx SQLite || fail "moteur de base inattendu"
$COMPOSE exec -T app python - <<'PY' || fail "inspection des bases SQLite impossible"
import glob, sqlite3, sys
fichiers = sorted(glob.glob("/data/borne_*.db"))
total = 0
for f in fichiers:
    c = sqlite3.connect(f)
    n = c.execute("SELECT COUNT(*) FROM consommation").fetchone()[0]
    res = [r[0] for r in c.execute("SELECT DISTINCT ressource FROM consommation ORDER BY 1")]
    print(f"   {f}: {n} relevés, ressources={res}")
    total += n
if not fichiers or total == 0:
    sys.exit("aucune donnée en base")
PY

echo "▶ 4/5 Commande MQTT aller-retour (couper → activer)…"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$URL/api/bornes/A07/commandes/couper")
[ "$code" = "202" ] || fail "POST couper a renvoyé $code"
for _ in $(seq 1 15); do
  p=$(curl -fs "$URL/api/bornes" | jq_py "[b for b in d['bornes'] if b['id']=='A07'][0]['prise_active']")
  [ "$p" = "False" ] && break; sleep 1
done
[ "$p" = "False" ] || fail "la borne A07 n'a pas confirmé la coupure"
curl -fs -X POST "$URL/api/bornes/A07/commandes/activer" >/dev/null
echo "   A07 a confirmé la coupure via MQTT"

echo "▶ 5/5 Portail web servi…"
curl -fs "$URL/" | grep -q "Portail client" || fail "page d'accueil absente"

echo "✅ Smoke test OK — base SQLite formée, bornes connectées, portail opérationnel."
