import { decryptBytes, decryptJson } from "./crypto.js";

const KEYS = { key: "jr-key", swipes: "jr-swipes", undo: "jr-undo", outbox: "jr-outbox", device: "jr-device", prefs: "jr-prefs", seen: "jr-seen" };
const read = (k, fallback) => { try { return JSON.parse(localStorage.getItem(k)) ?? fallback; } catch { return fallback; } };
const write = (k, v) => localStorage.setItem(k, JSON.stringify(v));

export const store = {
  feed: null,
  priv: null,
  key: localStorage.getItem(KEYS.key) || "",
  swipes: read(KEYS.swipes, {}),
  undo: read(KEYS.undo, []),
  outbox: read(KEYS.outbox, []),
  prefs: read(KEYS.prefs, { view: "cards" }),
  device: localStorage.getItem(KEYS.device) || (() => { const id = (navigator.userAgent.includes("iPhone") ? "iphone-" : navigator.userAgent.includes("Android") ? "android-" : "web-") + Math.random().toString(36).slice(2, 8); localStorage.setItem(KEYS.device, id); return id; })(),
  focus: null,
  listeners: new Set(),
  syncState: "local",
};

export const emit = () => store.listeners.forEach(fn => fn());
export const savePrefs = () => write(KEYS.prefs, store.prefs);

async function fetchText(path) {
  const response = await fetch(path + (path.includes("?") ? "&" : "?") + "t=" + Math.floor(Date.now() / 60000), { cache: "no-cache" });
  if (!response.ok) throw new Error(`${path} ${response.status}`);
  return response.text();
}

export function readHash() {
  const raw = location.hash.slice(1);
  const params = Object.fromEntries(raw.split("&").filter(Boolean).map(part => { const i = part.indexOf("="); return i < 0 ? [part, ""] : [part.slice(0, i), decodeURIComponent(part.slice(i + 1))]; }));
  if (params.k) {
    store.key = params.k;
    localStorage.setItem(KEYS.key, params.k);
    delete params.k;
    const rest = Object.entries(params).map(([k, v]) => v ? `${k}=${encodeURIComponent(v)}` : k).join("&");
    history.replaceState(null, "", location.pathname + location.search + (rest ? "#" + rest : ""));
  }
  return params;
}

export async function load() {
  store.feed = JSON.parse(await fetchText("feed.json"));
  if (store.key) {
    try {
      store.priv = await decryptJson(store.key, await fetchText("private.enc"));
    } catch {
      store.priv = null;
    }
  }
  if (store.priv?.sync?.token) await pull();
  flush();
}

export const unlocked = () => !!store.priv;

export async function fileBlob(name, type) {
  const bytes = await decryptBytes(store.key, await fetchText(`files/${name}.enc`));
  return new Blob([bytes], { type });
}

let photo = null;
export async function photoUrl() {
  if (photo !== null) return photo;
  try { photo = URL.createObjectURL(await fileBlob("photo", "image/png")); } catch { photo = ""; }
  return photo;
}

export function allCards() {
  const map = new Map();
  for (const card of [...(store.feed?.deck || []), ...(store.feed?.removed || [])]) map.set(card.id, card);
  return map;
}

export function cardFor(id) {
  const live = allCards().get(id);
  if (live) return live;
  const snap = store.swipes[id]?.snap;
  return snap ? { ...snap, listing: { status: "removed", label: "No longer listed", note: "It dropped out of every source. It has probably been filled or taken down." } } : null;
}

export function decision(id) { return store.swipes[id]?.d || null; }

function snapshot(card) {
  return card ? { id: card.id, title: card.title, company: card.company, city: card.city, location: card.location, image: card.image, logo: card.logo, art: card.art,
    url: card.url, apply_url: card.apply_url, tier: card.tier, tier_label: card.tier_label, score: card.score, work_mode: card.work_mode, greece_remote: card.greece_remote,
    listing: card.listing, languages: card.languages, posted: card.posted, deadline: card.deadline, has_docs: card.has_docs, files: card.files } : null;
}

export function decide(id, d, { trackUndo = true } = {}) {
  const card = cardFor(id);
  store.swipes[id] = { d, at: new Date().toISOString(), snap: snapshot(card) };
  if (trackUndo) {
    store.undo.push(id);
    store.undo = store.undo.slice(-60);
    write(KEYS.undo, store.undo);
  }
  write(KEYS.swipes, store.swipes);
  queue({ action: "swipe", job_id: id, decision: d, at: store.swipes[id].at, snapshot: store.swipes[id].snap });
  emit();
}

export function undoLast() {
  const id = store.undo.pop();
  write(KEYS.undo, store.undo);
  if (!id) return null;
  delete store.swipes[id];
  write(KEYS.swipes, store.swipes);
  queue({ action: "undo", job_id: id });
  emit();
  return id;
}

export function clearDecision(id) {
  delete store.swipes[id];
  write(KEYS.swipes, store.swipes);
  queue({ action: "undo", job_id: id });
  emit();
}

export function sendEvent(action, fields) { queue({ action, ...fields }); }

function queue(item) {
  store.outbox.push({ ...item, device: store.device });
  write(KEYS.outbox, store.outbox);
  flush();
}

let flushing = false;
export async function flush() {
  const sync = store.priv?.sync;
  if (!sync?.token || flushing || !store.outbox.length || !navigator.onLine) { updateSyncState(); return; }
  flushing = true;
  try {
    while (store.outbox.length) {
      const item = store.outbox[0];
      const response = await fetch(sync.url, { method: "POST", headers: { "Content-Type": "application/json", "x-radar-token": sync.token }, body: JSON.stringify(item) });
      if (!response.ok && response.status !== 400) throw new Error("sync " + response.status);
      store.outbox.shift();
      write(KEYS.outbox, store.outbox);
    }
  } catch { /* retried on the next action or when back online */ }
  flushing = false;
  updateSyncState();
}

async function pull() {
  const sync = store.priv.sync;
  try {
    const response = await fetch(sync.url, { headers: { "x-radar-token": sync.token } });
    if (!response.ok) throw new Error();
    const remote = await response.json();
    const pendingIds = new Set(store.outbox.map(o => o.job_id));
    const remoteIds = new Set();
    for (const s of remote.swipes) {
      remoteIds.add(s.job_id);
      const local = store.swipes[s.job_id];
      if (!local || new Date(s.at) > new Date(local.at)) store.swipes[s.job_id] = { d: s.decision, at: s.at, snap: local?.snap || snapshot(allCards().get(s.job_id)) };
    }
    for (const id of Object.keys(store.swipes)) if (!remoteIds.has(id) && !pendingIds.has(id) && store.swipes[id].synced) delete store.swipes[id];
    for (const id of remoteIds) if (store.swipes[id]) store.swipes[id].synced = true;
    for (const f of remote.facts || []) store.priv.facts[f.key] = f.value;
    write(KEYS.swipes, store.swipes);
    store.syncState = "synced";
  } catch { store.syncState = "offline"; }
}

function updateSyncState() {
  if (!store.priv?.sync?.token) store.syncState = "local";
  else if (store.outbox.length) store.syncState = navigator.onLine ? "syncing" : "offline";
  else store.syncState = "synced";
}

window.addEventListener("online", flush);
