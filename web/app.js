import { icon } from "./icons.js";
import { store, load, readHash, flush } from "./store.js";
import { discover, liked, historyView, browse, me, sourcesView, whyNot, radarView, updateBadge, closeSheet, toast } from "./ui.js";

const $ = s => document.querySelector(s);
const NAV = [["discover", "Discover", "cards"], ["liked", "Liked", "heart"], ["history", "Passed", "history"], ["browse", "Browse", "grid"], ["me", "Me", "user"]];

function nav(active) {
  $("#nav").innerHTML = NAV.map(([id, label, ic]) => `<a href="#${id}" class="${active === id ? "on" : ""}">${icon(ic)}<span>${label}</span>${id === "liked" ? '<span class="dot hidden" id="liked-dot"></span>' : ""}</a>`).join("");
  updateBadge();
}

async function route() {
  const params = readHash();
  closeSheet();
  const view = $("#view");
  view.scrollTop = 0;
  const name = Object.keys(params).find(k => ["discover", "liked", "history", "browse", "me", "sources", "whynot", "radar", "edit"].includes(k)) || "discover";
  nav(["sources", "whynot", "radar"].includes(name) ? "me" : name === "edit" ? "liked" : name);
  if (name === "discover") return discover(view, params);
  if (name === "liked") return liked(view, params);
  if (name === "history") return historyView(view);
  if (name === "browse") return browse(view);
  if (name === "me") return me(view);
  if (name === "sources") return sourcesView(view);
  if (name === "whynot") return whyNot(view);
  if (name === "radar") return radarView(view);
  if (name === "edit") {
    if (!store.priv) { toast("Open the link from her email once to unlock CV editing."); location.hash = "me"; return; }
    const studio = await import("./studio.js");
    return studio.open(view, params.edit);
  }
}

async function start() {
  $("#brand-mark").innerHTML = icon("flame");
  $("#top-browse").innerHTML = icon("search");
  $("#top-me").innerHTML = icon("user");
  readHash();
  try {
    await load();
  } catch (error) {
    $("#view").innerHTML = `<div class="empty"><div><h2>Can't reach the job list</h2><p class="muted">Check the connection and pull down to refresh.</p></div></div>`;
    return;
  }
  store.listeners.add(updateBadge);
  window.addEventListener("hashchange", route);
  await route();
  setInterval(async () => {
    if (document.visibilityState !== "visible") return;
    const before = store.feed?.generated_at;
    try { await load(); } catch { return; }
    if (store.feed.generated_at !== before && !location.hash.startsWith("#discover") && location.hash !== "") route();
  }, 5 * 60 * 1000);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") flush(); });
}

document.addEventListener("error", event => {
  const img = event.target;
  if (!(img instanceof HTMLImageElement)) return;
  if (img.dataset.fallback && img.getAttribute("src") !== img.dataset.fallback) img.src = img.dataset.fallback;
  else if (img.hasAttribute("data-hide-on-error")) { const box = img.parentElement; img.remove(); if (box?.dataset.initials) box.textContent = box.dataset.initials; }
}, true);

if ("serviceWorker" in navigator && location.protocol === "https:") navigator.serviceWorker.register("sw.js").catch(() => {});
start();
