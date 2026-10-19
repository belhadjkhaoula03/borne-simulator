"use strict";

const NOMS = { ELECTRICITE: "Électricité", EAU: "Eau", GAZ: "Gaz" };
const nf = (d) => new Intl.NumberFormat("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });
const euro = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });
const heure = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const SVG = "http://www.w3.org/2000/svg";

const $ = (id) => document.getElementById(id);
const cartes = new Map();       // id borne -> { root, refs }
const histo = new Map();        // id borne -> dernier relevé dont on a chargé l'historique
let enCommande = new Set();

function el(tag, classe, texte) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texte !== undefined) e.textContent = texte;
  return e;
}

function toast(message) {
  const t = $("toast");
  t.textContent = message; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), 4000);
}

/* ------------------------------------------------------------- construction */
function creerCarte(borne) {
  const root = el("article", "card");
  const head = el("div", "card-head");
  const titre = el("div");
  titre.append(el("h2", null, `Borne ${borne.id}`),
               el("p", "sub", `Réservation ${borne.reservation ?? "—"} · relevé toutes les ${borne.intervalle ?? "?"} s`));
  const badge = el("span", "pill");
  head.append(titre, badge);
  root.append(head);

  const res = {};
  for (const nom of Object.keys(borne.ressources)) {
    const bloc = el("div", `res c-${nom}`);
    const label = el("span", "res-name");
    const sw = el("span", `swatch bg-${nom}`);
    label.append(sw, document.createTextNode(NOMS[nom] ?? nom));
    const now = el("span", "res-now");
    const meta = el("span", "res-meta");
    const svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("class", "spark");
    svg.setAttribute("viewBox", "0 0 200 40");
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", `Évolution ${NOMS[nom] ?? nom}`);
    const area = document.createElementNS(SVG, "path"); area.setAttribute("class", "area");
    const line = document.createElementNS(SVG, "path"); line.setAttribute("class", "line");
    svg.append(area, line);
    bloc.append(label, now, meta, el("span"), svg);
    root.append(bloc);
    res[nom] = { now, meta, area, line };
  }

  const foot = el("div", "card-foot");
  const socket = el("span", "socket");
  const bouton = el("button", "btn");
  bouton.type = "button";
  foot.append(socket, bouton);
  root.append(foot);
  bouton.addEventListener("click", () => commander(borne.id, bouton.dataset.cmd));

  $("grid").append(root);
  const refs = { badge, socket, bouton, res };
  cartes.set(borne.id, { root, refs });
  return cartes.get(borne.id);
}

/* ------------------------------------------------------------------ rendu */
function dessiner(ref, points) {
  if (points.length < 2) { ref.line.removeAttribute("d"); ref.area.removeAttribute("d"); return; }
  const qs = points.map((p) => p.q);
  const min = Math.min(...qs), max = Math.max(...qs), plage = max - min || 1;
  const xy = qs.map((q, i) => [(i / (qs.length - 1)) * 200, 36 - ((q - min) / plage) * 32]);
  const d = xy.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  ref.line.setAttribute("d", d);
  ref.area.setAttribute("d", `${d} L200 40 L0 40 Z`);
}

async function chargerHistorique(id, refs) {
  try {
    const r = await fetch(`/api/bornes/${encodeURIComponent(id)}/historique?limit=40`);
    if (!r.ok) return;
    const data = await r.json();
    for (const [nom, points] of Object.entries(data)) if (refs.res[nom]) dessiner(refs.res[nom], points);
  } catch { /* le prochain relevé réessaiera */ }
}

function rendreBorne(borne) {
  const { root, refs } = cartes.get(borne.id) ?? creerCarte(borne);
  const en = borne.statut === "en_ligne";
  root.classList.toggle("offline", borne.statut === "hors_ligne");
  refs.badge.className = `pill ${en ? "pill-ok" : borne.statut === "hors_ligne" ? "pill-bad" : "pill-wait"}`;
  refs.badge.replaceChildren(el("span", "dot"), document.createTextNode(
    en ? "En ligne" : borne.statut === "hors_ligne" ? "Hors ligne" : "En attente"));

  for (const [nom, v] of Object.entries(borne.ressources)) {
    const r = refs.res[nom]; if (!r) continue;
    r.now.replaceChildren(document.createTextNode(v.instantanee === null ? "—" : nf(2).format(v.instantanee)),
                          el("small", null, v.unite));
    r.meta.textContent = `Cumul ${nf(2).format(v.cumul)} ${v.unite} · ${euro.format(v.cout)}`;
  }

  const active = borne.prise_active;
  refs.socket.className = `socket ${active === true ? "on" : active === false ? "off" : "unk"}`;
  refs.socket.textContent = active === true ? "● Prise active" : active === false ? "● Prise coupée" : "● Prise —";
  const cmd = active === false ? "activer" : "couper";
  refs.bouton.dataset.cmd = cmd;
  refs.bouton.textContent = active === false ? "Activer la prise" : "Couper la prise";
  refs.bouton.classList.toggle("btn-danger", cmd === "couper");
  refs.bouton.disabled = !en || enCommande.has(borne.id);

  if (borne.dernier_releve && histo.get(borne.id) !== borne.dernier_releve) {
    histo.set(borne.id, borne.dernier_releve);
    chargerHistorique(borne.id, refs);
  }
}

function rendre(snap) {
  $("empty").hidden = snap.bornes.length > 0;
  snap.bornes.forEach(rendreBorne);
  const en = snap.bornes.filter((b) => b.statut === "en_ligne").length;
  $("kpi-online").textContent = `${en} / ${snap.bornes.length}`;
  $("kpi-cost").textContent = euro.format(snap.cout_total);
  const dates = snap.bornes.map((b) => b.dernier_releve).filter(Boolean).sort();
  $("kpi-last").textContent = dates.length ? heure.format(new Date(dates[dates.length - 1])) : "—";
  const live = $("live");
  live.className = `pill ${snap.broker_connecte ? "pill-ok" : "pill-bad"}`;
  $("live-text").textContent = snap.broker_connecte ? "Temps réel actif" : "Broker MQTT indisponible";
}

/* --------------------------------------------------------------- commandes */
async function commander(id, cmd) {
  enCommande.add(id);
  const c = cartes.get(id); if (c) c.refs.bouton.disabled = true;
  try {
    const r = await fetch(`/api/bornes/${encodeURIComponent(id)}/commandes/${cmd}`, { method: "POST" });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Erreur ${r.status}`);
  } catch (e) {
    toast(`Commande impossible : ${e.message}`);
  } finally {
    setTimeout(() => { enCommande.delete(id); if (c) c.refs.bouton.disabled = false; }, 1500);
  }
}

/* ----------------------------------------------------------------- système */
async function chargerSysteme() {
  try {
    const s = await (await fetch("/api/systeme")).json();
    const db = s.base_de_donnees;
    const total = db.bases.reduce((a, b) => a + b.releves, 0);
    const p = $("sys");
    p.replaceChildren(
      el("strong", null, "Base de données : "),
      document.createTextNode(`${db.moteur} ${db.version} — ${db.organisation} (${db.bases.length} fichiers, ${nf(0).format(total)} relevés) · `),
      el("strong", null, "Messagerie : "),
      document.createTextNode(s.broker.type));
  } catch { /* non bloquant */ }
}

/* ---------------------------------------------------------------- temps réel */
function connecter() {
  const es = new EventSource("/api/stream");
  es.addEventListener("snapshot", (e) => rendre(JSON.parse(e.data)));
  es.onerror = () => {
    $("live").className = "pill pill-wait";
    $("live-text").textContent = "Reconnexion…";
  };
}

connecter();
chargerSysteme();
setInterval(chargerSysteme, 30000);
