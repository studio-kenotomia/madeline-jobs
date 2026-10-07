import { icon } from "./icons.js";
import { store, emit, decide, undoLast, clearDecision, decision, cardFor, allCards, sendEvent, unlocked, fileBlob, savePrefs } from "./store.js";

const $ = s => document.querySelector(s);
export const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export function ago(iso, short = false) {
  if (!iso) return "unknown";
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.round(ms / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 36) return `${h} h ago`;
  const d = Math.round(h / 24);
  return short ? `${d}d ago` : `${d} day${d === 1 ? "" : "s"} ago`;
}
const dateLabel = iso => {
  if (!iso) return "";
  const d = new Date(iso + (iso.length === 10 ? "T12:00:00" : ""));
  const days = Math.round((d - Date.now()) / 86400000);
  const pretty = d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
  if (days < 0) return `${pretty} (passed)`;
  if (days === 0) return `${pretty} (today)`;
  if (days <= 7) return `${pretty} (${days} day${days === 1 ? "" : "s"})`;
  return pretty;
};
function postedDays(card) {
  if (!card.posted) return null;
  return Math.round((Date.now() - new Date(card.posted + "T12:00:00Z")) / 86400000);
}
function postedLabel(card) {
  const days = postedDays(card);
  const foundRecently = card.first_seen && Date.now() - new Date(card.first_seen) < 7 * 86400000;
  if (days == null) return `Found ${ago(card.first_seen)}`;
  if (days <= 0) return "Posted today";
  if (days === 1) return "Posted yesterday";
  if (days < 45) return `Posted ${days} days ago`;
  if (foundRecently) return `Found ${ago(card.first_seen)}`;
  return `Open since ${new Date(card.posted + "T12:00:00Z").toLocaleDateString(undefined, { month: "short", year: "numeric" })}`;
}
function postedFull(card) {
  const days = postedDays(card);
  const foundRecently = card.first_seen && Date.now() - new Date(card.first_seen) < 7 * 86400000;
  if (days == null) return "Date not stated";
  const source = new Date(card.posted + "T12:00:00Z").toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  if (days >= 45 && foundRecently) return `Source date ${source} · first seen here ${ago(card.first_seen)}`;
  return postedLabel(card).replace("Open since", "Since");
}
function prose(text) {
  const clean = String(text || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  if (!clean || clean.startsWith("{") || clean.startsWith("[") || /^https?:\/\/\S+$/.test(clean)) return "";
  return clean;
}
const money = s => s ? `${s.min}${s.max && s.max !== s.min ? "–" + s.max : ""} ${s.currency || ""}${s.period ? " / " + String(s.period).toLowerCase().replace("year", "yr").replace("month", "mo") : ""}` : "";
const initials = name => (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join("").toUpperCase();
const logoHTML = (card, cls = "logo") => `<div class="${cls}" data-initials="${esc(initials(card.company))}">${card.logo ? `<img src="${esc(card.logo)}" alt="" data-hide-on-error>` : esc(initials(card.company))}</div>`;
const imgSrc = card => card.image || card.art || "art/remote.jpg";
const workLabel = card => card.greece_remote === "onsite" ? (card.work_mode === "hybrid" ? "Hybrid · Thessaloniki" : "On-site · Thessaloniki") :
  card.work_mode === "remote" ? ({ confirmed: "Remote · Greece OK", likely: "Remote · Greece likely", unclear: "Remote · check country" }[card.greece_remote] || "Remote") : (card.city || card.location || "");

let toastTimer;
export function toast(html, ms = 3800) {
  let el = $(".toast");
  if (!el) { el = document.createElement("div"); el.className = "toast"; document.body.append(el); }
  el.innerHTML = html;
  requestAnimationFrame(() => el.classList.add("on"));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("on"), ms);
  return el;
}

function burst(x, y, char) {
  for (let i = 0; i < 6; i++) {
    const el = document.createElement("div");
    el.className = "burst";
    el.textContent = char;
    el.style.left = x + (Math.random() * 120 - 60) + "px";
    el.style.top = y + (Math.random() * 40 - 20) + "px";
    el.style.animationDelay = i * 60 + "ms";
    document.body.append(el);
    setTimeout(() => el.remove(), 1400);
  }
}

function languageChips(card, limit = 4) {
  return (card.languages || []).slice(0, limit).map(l => {
    const cls = l.ok ? "good" : l.level === "required" ? "bad" : "warn";
    const lvl = l.level === "required" ? "required" : l.level === "preferred" ? "a plus" : l.level === "implied" ? "" : "mentioned";
    return `<span class="chip ${cls}">${icon("lang")}${esc(l.name)}${lvl ? " · " + lvl : ""}${l.ok ? " ✓" : ""}</span>`;
  }).join("");
}

function factChips(card) {
  const chips = [`<span class="chip ${card.greece_remote === "onsite" || card.greece_remote === "confirmed" ? "good" : card.greece_remote === "unclear" ? "warn" : ""}">${icon(card.work_mode === "remote" ? "globe" : "pin")}${esc(workLabel(card))}</span>`];
  chips.push(`<span class="chip">${icon("cal")}${esc(postedLabel(card))}</span>`);
  if (card.deadline) chips.push(`<span class="chip ${/passed|today|\(\d day/.test(dateLabel(card.deadline)) ? "warn" : ""}">${icon("clock")}Closes ${esc(dateLabel(card.deadline))}</span>`);
  if (card.salary) chips.push(`<span class="chip good">${icon("euro")}${esc(money(card.salary))}</span>`);
  chips.push(`<span class="chip">${icon("users")}${card.applicants != null ? esc(card.applicants) + " applicants" : "Applicants not published"}</span>`);
  return chips.join("");
}

export function deckCard(card, { email = false } = {}) {
  const status = card.listing || {};
  const p = Math.max(0, Math.min(100, card.score || 0));
  const reasons = (card.reasons || []).slice(0, 2).map(r => `<li>${esc(r.replace(/^Strong: /, ""))}</li>`).join("");
  const risk = [...(card.blockers || []).map(b => `<li class="block">${esc(b)}</li>`), ...(card.gaps || []).slice(0, 1).map(g => `<li class="risk">${esc(g)}</li>`)].slice(0, 1).join("");
  const credit = card.image_kind === "location" ? `<div class="credit">Photo: Wikimedia Commons</div>` : "";
  return `<div class="photo ${card.image_kind === "company" ? "company" : ""}">
      <img class="hero" src="${esc(imgSrc(card))}" alt="" draggable="false" data-fallback="${esc(card.art || "art/remote.jpg")}">
      <div class="top">${logoHTML(card)}<div style="display:grid;justify-items:end;gap:8px">
        ${card.tier_label ? `<span class="ribbon ${esc(card.tier)}">${icon(card.tier === "exceptional" ? "sparkle" : card.tier === "apply" ? "flame" : "star")}${esc(card.tier_label)}</span>` : ""}
        <div class="score" style="--p:${p}%"><span>${p}</span></div></div></div>
      <div class="bottom">
        ${email ? `<span class="status-pill email">${icon("sparkle")}Recommended for you</span><br>` : ""}
        ${status.status && status.status !== "open" ? `<span class="status-pill ${esc(status.status)}">${esc(status.label)}</span>` : ""}
        <h2>${esc(card.title)}</h2>
        <div class="company">${esc(card.company || "Company not named")} · ${esc(card.city || "")}</div>
      </div>${credit}
    </div>
    <div class="info">
      <div class="chips">${factChips(card)}</div>
      <div class="chips">${languageChips(card)}</div>
      <ul class="why">${reasons}${risk}</ul>
      <div class="tap-hint">${icon("info")} Tap for details · swipe to decide</div>
    </div>
    <div class="stamp like">SAVE</div><div class="stamp nope">PASS</div><div class="stamp super">TOP PICK</div>`;
}

export function detailHTML(card, { hero = true, steps = false } = {}) {
  const status = card.listing || {};
  const req = (card.highlights || []).map(h => `<div><span>${esc(h.label)}${h.importance === "mandatory" ? " · required" : ""}</span><span class="m-${esc(h.match)}">${esc(h.match)}</span></div>`).join("");
  const watch = [...(card.blockers || []).map(b => `<li class="block">${esc(b)}</li>`), ...(card.gaps || []).map(g => `<li class="risk">${esc(g)}</li>`), ...(card.unknowns || []).map(u => `<li class="risk">${esc(u)}</li>`)].join("");
  return `${hero ? `<div class="sheet-hero"><img src="${esc(imgSrc(card))}" alt="" data-fallback="${esc(card.art || "art/remote.jpg")}">${logoHTML(card)}</div>` : ""}
    <span class="ribbon ${esc(card.tier)}" style="margin-bottom:8px">${esc(card.tier_label || "")} · ${esc(card.score)}</span>
    <h2>${esc(card.title)}</h2>
    <div class="muted">${esc(card.company || "")} · ${esc(card.location || card.city || "")}</div>
    <div style="margin-top:10px"><span class="status-pill ${esc(status.status || "open")}" style="${status.status === "open" ? "background:#e3f6ee;color:#0f6b48" : ""}">${esc(status.label || "Open")}</span>
      <span class="muted small">${esc(status.note || "")}</span></div>
    ${steps ? nextStepsHTML(card) : ""}
    ${card.scam?.length ? `<div class="panel" style="background:#fde6e9">Possible scam signals: ${esc(card.scam.join(", "))}. Check the company before sending anything.</div>` : ""}
    <div class="facts">
      <div class="fact"><b>Where</b><span>${esc(workLabel(card))}</span></div>
      <div class="fact"><b>From Greece</b><span>${esc({ onsite: "Lives there", confirmed: "Allowed", likely: "Probably allowed", unclear: "Ask first" }[card.greece_remote] || "—")}</span></div>
      <div class="fact"><b>Posted</b><span>${esc(postedFull(card))}</span></div>
      <div class="fact"><b>Found</b><span>${esc(ago(card.first_seen))}</span></div>
      <div class="fact"><b>Deadline</b><span>${esc(card.deadline ? dateLabel(card.deadline) : "None stated")}</span></div>
      <div class="fact"><b>Pay</b><span>${esc(money(card.salary) || "Not published")}</span></div>
      <div class="fact"><b>Applicants</b><span>${card.applicants != null ? esc(card.applicants) : "Not published"}</span></div>
      <div class="fact"><b>Type</b><span>${esc(card.employment_type || "Not stated")}</span></div>
    </div>
    <div class="sec">Languages</div><div class="chips">${languageChips(card, 8) || '<span class="muted small">No language named in the ad.</span>'}</div>
    <div class="sec">Why it fits her</div><ul class="why">${(card.reasons || []).map(r => `<li>${esc(r)}</li>`).join("") || "<li>Office role in her target area.</li>"}</ul>
    ${watch ? `<div class="sec">Watch out</div><ul class="why">${watch}</ul>` : ""}
    ${req ? `<div class="sec">What they ask for</div><div class="req">${req}</div>` : ""}
    ${(card.greek_gist || []).length ? `<div class="sec">The Greek ad says</div><div class="chips">${card.greek_gist.map(g => `<span class="chip blue">${esc(g)}</span>`).join("")}</div>` : ""}
    <div class="sec">About the role</div>
    <div class="desc" data-desc>${esc(prose(card.description) || "Open the listing for the full advertisement.")}</div>
    <p><button class="btn slim" data-more>Read the full ad</button></p>
    <p class="muted small">Source: ${esc(card.source)}${card.also_seen ? ` · also on ${card.also_seen} other site${card.also_seen > 1 ? "s" : ""}` : ""}${card.changes ? ` · changed ${card.changes}×` : ""}</p>`;
}

function nextStepsHTML(card) {
  const d = decision(card.id);
  const files = card.files || [];
  const ready = unlocked() && (card.has_docs || files.length);
  const fileBtn = (name, label, ic) => `<button class="btn slim" data-file="${name}" ${ready ? "" : "disabled"}>${icon(ic)}${label}</button>`;
  return `<div class="sec">Next steps</div>
    <div class="chips" style="gap:8px">
      ${fileBtn("cv_pdf", "CV PDF", "download")}${fileBtn("cv_docx", "CV Word", "doc")}${fileBtn("cover_pdf", "Cover letter", "doc")}
      <a class="btn slim" href="#edit=${esc(card.id)}" ${ready ? "" : 'aria-disabled="true" style="opacity:.45;pointer-events:none"'}>${icon("edit")}Edit CV</a>
      <a class="btn slim" href="${esc(card.apply_url || card.url)}" target="_blank" rel="noopener">${icon("external")}Open listing</a>
      ${d === "applied" ? `<span class="tag applied">Applied</span>` : `<button class="btn slim like" data-applied>${icon("check")}I applied</button>`}
      ${unlocked() && files.includes("cv_pdf") ? `<button class="btn slim" data-bridge>${icon("bolt")}${/^(127\.0\.0\.1|localhost)$/.test(location.hostname) ? "Fill the form on this Mac" : "Fill the form on the Mac"}</button>` : ""}
    </div>
    ${!unlocked() ? `<p class="muted small">Reload the page. Her CV downloads with the app.</p>` : !card.has_docs && !files.length ? `<p class="muted small">A tailored CV is written for her strongest matches. Save this one and it is prepared on the next update.</p>` : ""}
    ${card.ai_policy === "prohibited" ? `<p class="small" style="color:#8a5a00">This employer bans AI-written answers. Use the CV as a fact sheet and write the form answers in her own words.</p>` : ""}`;
}

/* bottom sheet */
let sheetCard = null;
export function openSheet(card, context = "deck", hooks = {}) {
  sheetCard = card;
  let scrim = $(".scrim"), sheet = $(".sheet");
  if (!scrim) { scrim = document.createElement("div"); scrim.className = "scrim"; document.body.append(scrim); scrim.onclick = closeSheet; }
  if (!sheet) { sheet = document.createElement("div"); sheet.className = "sheet"; document.body.append(sheet); }
  const d = decision(card.id);
  const liked = ["like", "superlike", "applied", "interview", "offer"].includes(d);
  const actions = context === "deck"
    ? `<button class="btn nope" data-act="pass">${icon("x")}Pass</button><a class="btn" href="${esc(card.url)}" target="_blank" rel="noopener">${icon("external")}Open</a><button class="btn like full" data-act="like">${icon("heart")}Save</button>`
    : context === "history"
      ? `<button class="btn" data-act="restore">${icon("restore")}Back to the deck</button><button class="btn like full" data-act="like">${icon("heart")}Save it</button>`
      : `<a class="btn full primary" href="${esc(card.apply_url || card.url)}" target="_blank" rel="noopener">${icon("external")}Go to the listing</a>${liked ? `<button class="btn" data-act="unlike">Remove</button>` : `<button class="btn like" data-act="like">${icon("heart")}Save</button>`}`;
  sheet.innerHTML = `<div class="grab"></div><div class="scroll">${detailHTML(card, { steps: liked || context === "liked" })}</div><div class="sheet-actions">${actions}</div>`;
  scrim.classList.remove("hidden");
  requestAnimationFrame(() => { scrim.classList.add("on"); sheet.classList.add("on"); });
  wireDetail(sheet, card);
  sheet.querySelectorAll("[data-act]").forEach(b => b.onclick = () => {
    const act = b.dataset.act;
    closeSheet();
    if (hooks[act]) return hooks[act](card);
    if (act === "like") { decide(card.id, "like"); toast(`${icon("heart")} Saved to Liked`); }
    if (act === "pass") decide(card.id, "pass");
    if (act === "restore" || act === "unlike") { clearDecision(card.id); toast(act === "restore" ? "Back in the deck" : "Removed from Liked"); }
  });
  let startY = null;
  const grab = sheet.querySelector(".grab");
  grab.onpointerdown = e => { startY = e.clientY; grab.setPointerCapture(e.pointerId); };
  grab.onpointermove = e => { if (startY != null && e.clientY - startY > 0) sheet.style.transform = `translateY(${e.clientY - startY}px)`; };
  grab.onpointerup = e => { const dy = e.clientY - (startY ?? e.clientY); startY = null; sheet.style.transform = ""; if (dy > 90) closeSheet(); };
}

export function closeSheet() {
  $(".scrim")?.classList.remove("on");
  $(".sheet")?.classList.remove("on");
  setTimeout(() => $(".scrim")?.classList.add("hidden"), 260);
  sheetCard = null;
}

export function wireDetail(root, card) {
  root.querySelector("[data-more]")?.addEventListener("click", e => { root.querySelector("[data-desc]").classList.add("open"); e.target.remove(); });
  root.querySelectorAll("[data-file]").forEach(b => b.onclick = async () => {
    const name = b.dataset.file;
    const type = name.endsWith("pdf") ? "application/pdf" : "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    const stem = (store.priv?.profile?.name || "CV").replace(/\W+/g, "_");
    if ((card.files || []).includes(name)) {
      try {
        const blob = await fileBlob(`${card.id}-${name}`, type);
        download(blob, `${stem}_${name.startsWith("cv") ? "CV" : "Cover_letter"}_${(card.company || "").replace(/\W+/g, "_")}.${name.endsWith("pdf") ? "pdf" : "docx"}`);
        return;
      } catch { /* the editor can still produce it */ }
    }
    if (card.has_docs) { toast("Opening her CV. Use Word or PDF there."); location.hash = `edit=${card.id}`; return; }
    toast("A tailored CV for this one is prepared on the next update.");
  });
  root.querySelector("[data-applied]")?.addEventListener("click", () => { decide(card.id, "applied"); toast(`${icon("check")} Marked as applied. Good luck!`); closeSheet(); });
  root.querySelector("[data-bridge]")?.addEventListener("click", async () => {
    if (/^(127\.0\.0\.1|localhost)$/.test(location.hostname)) {
      toast("Opening the employer form on this Mac…");
      try {
        const result = await (await fetch(`api/bridge/prepare/${card.id}`, { method: "POST", headers: { "Content-Type": "application/json" } })).json();
        toast(esc(result.message || "Done."), 9000);
      } catch { toast("The Mac bridge did not answer."); }
    } else {
      sendEvent("prepare", { job_id: card.id });
      toast("Queued. The Mac fills the form next time it is on, and stops before submitting.", 6000);
    }
  });
}

export function download(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
}

/* discover deck */
export function discover(root, params) {
  const cards = store.feed.deck.filter(c => !decision(c.id));
  let focus = params.job ? store.feed.deck.find(c => c.id === params.job) || allCards().get(params.job) : null;
  if (focus && decision(focus.id)) focus = null;
  const mode = store.prefs.deckFilter || "all";
  let queue = cards.filter(c => mode === "all" || (mode === "top" ? ["exceptional", "apply", "worth"].includes(c.tier) : mode === "thess" ? c.greece_remote === "onsite" : c.work_mode === "remote"));
  if (focus) queue = [focus, ...queue.filter(c => c.id !== focus.id)];
  const fresh = cards.filter(c => Date.now() - new Date(c.first_seen) < 86400000).length;
  root.innerHTML = `<div class="discover">
      <div class="deck-head">
        <div class="seg">${[["all", "For you"], ["top", "Best"], ["thess", "Thessaloniki"], ["remote", "Remote"]].map(([k, l]) => `<button data-mode="${k}" class="${mode === k ? "on" : ""}">${l}</button>`).join("")}</div>
        <span class="deck-meta">${queue.length} to see${fresh ? ` · ${fresh} new today` : ""}</span>
      </div>
      <div class="deck" id="deck"></div>
      <div class="actions">
        <button class="act sm undo" id="b-undo" title="Undo (Z)">${icon("undo")}</button>
        <button class="act lg nope" id="b-nope" title="Pass (←)">${icon("x")}</button>
        <button class="act sm super" id="b-super" title="Top pick (↑)">${icon("star")}</button>
        <button class="act lg like" id="b-like" title="Save (→)">${icon("heart")}</button>
        <button class="act sm open" id="b-open" title="Open the listing">${icon("external")}</button>
      </div>
      <aside class="side" id="side"></aside>
    </div>`;
  root.querySelectorAll("[data-mode]").forEach(b => b.onclick = () => { store.prefs.deckFilter = b.dataset.mode; savePrefs(); discover(root, {}); });
  const deck = root.querySelector("#deck");
  const side = root.querySelector("#side");
  let index = 0;

  function paint(enterFrom = null) {
    deck.innerHTML = "";
    const visible = queue.slice(index, index + 3);
    if (!visible.length) {
      deck.innerHTML = `<div class="empty"><div><div class="bubble">${icon("check", "i")}</div><h2 style="margin:0 0 6px">You're all caught up</h2>
        <p class="muted">New roles are checked every 20 minutes. Saved ones are in Liked.</p><p><a class="btn hot" href="#liked">${icon("heart")}See liked jobs</a></p>
        <p><button class="btn slim" id="see-history">${icon("history")}Look at passed jobs</button></p></div></div>`;
      deck.querySelector("#see-history").onclick = () => { location.hash = "history"; };
      side.innerHTML = "";
      return;
    }
    visible.slice().reverse().forEach((card, i, arr) => {
      const depth = arr.length - 1 - i;
      const el = document.createElement("article");
      el.className = "card" + (depth === 1 ? " behind" : depth === 2 ? " behind2" : "");
      el.dataset.id = card.id;
      el.innerHTML = deckCard(card, { email: focus && card.id === focus.id });
      deck.append(el);
      if (depth === 0) {
        if (enterFrom) {
          el.classList.add("dragging");
          el.style.transform = enterFrom;
          requestAnimationFrame(() => requestAnimationFrame(() => { el.classList.remove("dragging"); el.style.transform = ""; }));
        }
        attach(el, card);
      }
    });
    side.innerHTML = detailHTML(visible[0], { hero: false }) + nextStepsHTML(visible[0]);
    wireDetail(side, visible[0]);
    root.querySelector("#b-undo").disabled = !store.undo.length;
  }

  function attach(el, card) {
    let sx = 0, sy = 0, dx = 0, dy = 0, t0 = 0, active = false;
    const like = el.querySelector(".stamp.like"), nope = el.querySelector(".stamp.nope"), sup = el.querySelector(".stamp.super");
    el.onpointerdown = e => {
      if (e.target.closest("a,button")) return;
      active = true; sx = e.clientX; sy = e.clientY; dx = dy = 0; t0 = performance.now();
      el.classList.add("dragging"); el.setPointerCapture(e.pointerId);
    };
    el.onpointermove = e => {
      if (!active) return;
      dx = e.clientX - sx; dy = e.clientY - sy;
      el.style.transform = `translate(${dx}px, ${dy * 0.6}px) rotate(${dx * 0.055}deg)`;
      const up = dy < 0 && Math.abs(dy) > Math.abs(dx) ? Math.min(1, -dy / 120) : 0;
      like.style.opacity = up ? 0 : Math.max(0, Math.min(1, dx / 90));
      nope.style.opacity = up ? 0 : Math.max(0, Math.min(1, -dx / 90));
      sup.style.opacity = up;
    };
    el.onpointerup = el.onpointercancel = () => {
      if (!active) return;
      active = false;
      el.classList.remove("dragging");
      const dt = Math.max(1, performance.now() - t0), vx = dx / dt, width = deck.clientWidth;
      if (Math.abs(dx) < 6 && Math.abs(dy) < 6) { el.style.transform = ""; return openSheet(card, "deck", { like: () => fly("like"), pass: () => fly("pass") }); }
      if (dy < -deck.clientHeight * 0.22 && Math.abs(dy) > Math.abs(dx)) return fly("superlike", dx, dy);
      if (dx > width * 0.28 || vx > 0.65) return fly("like", dx, dy);
      if (dx < -width * 0.28 || vx < -0.65) return fly("pass", dx, dy);
      el.style.transform = ""; like.style.opacity = nope.style.opacity = sup.style.opacity = 0;
    };
  }

  function fly(kind, dx = 0, dy = 0) {
    const el = deck.querySelector(".card:last-child");
    const card = queue[index];
    if (!el || !card) return;
    const w = deck.clientWidth;
    el.classList.add("gone");
    const stamp = el.querySelector(kind === "like" ? ".stamp.like" : kind === "pass" ? ".stamp.nope" : ".stamp.super");
    if (stamp) stamp.style.opacity = 1;
    el.style.transition = "transform .42s cubic-bezier(.3,.7,.3,1), opacity .42s";
    el.style.transform = kind === "superlike" ? `translate(${dx}px, ${-window.innerHeight}px) rotate(${dx * 0.05}deg)` : `translate(${(kind === "like" ? 1 : -1) * w * 1.6}px, ${dy * 0.6 + 40}px) rotate(${kind === "like" ? 28 : -28}deg)`;
    el.style.opacity = 0;
    const rect = deck.getBoundingClientRect();
    if (kind !== "pass") burst(rect.left + rect.width / 2, rect.top + rect.height * 0.45, kind === "superlike" ? "⭐" : "💚");
    decide(card.id, kind);
    index += 1;
    setTimeout(() => paint(), 260);
    if (kind === "pass") {
      const t = toast(`<span>Passed</span><span class="quick">${[["too_sales", "Too sales"], ["too_senior", "Too senior"], ["greek_too_strong", "Greek"], ["remote_bad", "Location"], ["too_customer", "Customer-facing"]].map(([k, l]) => `<button data-fb="${k}">${l}</button>`).join("")}</span>`, 4200);
      t.querySelectorAll("[data-fb]").forEach(b => b.onclick = () => { sendEvent("feedback", { job_id: card.id, reason: b.dataset.fb }); toast("Thanks, the ranking learns from that."); });
    } else {
      const t = toast(`<span>${kind === "superlike" ? "Top pick saved" : "Saved to Liked"}</span><button data-go>Next steps</button>`);
      t.querySelector("[data-go]").onclick = () => { location.hash = `liked&open=${card.id}`; };
    }
    updateBadge();
  }

  root.querySelector("#b-like").onclick = () => fly("like");
  root.querySelector("#b-nope").onclick = () => fly("pass");
  root.querySelector("#b-super").onclick = () => fly("superlike", 0, -200);
  root.querySelector("#b-open").onclick = () => { const c = queue[index]; if (c) window.open(c.url, "_blank", "noopener"); };
  root.querySelector("#b-undo").onclick = () => {
    const id = undoLast();
    if (!id) return;
    const card = cardFor(id);
    if (!card) return;
    const pos = queue.findIndex(c => c.id === id);
    if (pos >= 0) {
      queue.splice(pos, 1);
      if (pos < index) index -= 1;
    }
    queue.splice(index, 0, card);
    paint("translate(-120%, 30px) rotate(-20deg)");
    toast(`${icon("undo")} Brought back`);
    updateBadge();
  };
  document.onkeydown = e => {
    if (!location.hash.startsWith("#discover") && location.hash !== "" && !location.hash.startsWith("#job")) return;
    if (e.target.closest("input,textarea,select,[contenteditable]")) return;
    if (e.key === "ArrowRight") fly("like");
    else if (e.key === "ArrowLeft") fly("pass");
    else if (e.key === "ArrowUp") fly("superlike", 0, -200);
    else if (e.key.toLowerCase() === "z" || e.key === "Backspace") root.querySelector("#b-undo").click();
    else if (e.key === " " && queue[index]) { e.preventDefault(); openSheet(queue[index], "deck", { like: () => fly("like"), pass: () => fly("pass") }); }
  };
  paint();
}

export function updateBadge() {
  const liked = Object.values(store.swipes).filter(s => ["like", "superlike"].includes(s.d)).length;
  const dot = $("#liked-dot");
  if (dot) { dot.textContent = liked; dot.classList.toggle("hidden", !liked); }
}

function rowCard(card, extra = "") {
  const d = decision(card.id);
  const st = card.listing?.status;
  const tags = [d === "superlike" ? '<span class="tag super">Top pick</span>' : "", d === "applied" ? '<span class="tag applied">Applied</span>' : "",
    st === "removed" ? `<span class="tag removed">${esc(card.listing.label)}</span>` : "", st === "updated" ? '<span class="tag updated">Updated</span>' : ""].join(" ");
  return `<div class="row-card" data-id="${esc(card.id)}">
    <div class="thumb"><img src="${esc(imgSrc(card))}" alt="" loading="lazy" data-fallback="${esc(card.art || "art/remote.jpg")}">${logoHTML(card, "mini-logo")}</div>
    <div><div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:3px">${tags}</div><h3>${esc(card.title)}</h3>
      <div class="sub">${esc(card.company || "")} · ${esc(workLabel(card))}</div>
      <div class="chips"><span class="chip">${esc(card.score ?? "")} · ${esc(card.tier_label || "")}</span>${card.deadline ? `<span class="chip warn">Closes ${esc(dateLabel(card.deadline))}</span>` : ""}</div></div>
    ${extra}</div>`;
}

function bindRows(root, context, hooks = {}) {
  root.querySelectorAll(".row-card, .tile").forEach(el => el.addEventListener("click", e => {
    if (e.target.closest("button,a")) return;
    const card = cardFor(el.dataset.id);
    if (card) openSheet(card, context, hooks);
  }));
}

export function liked(root, params) {
  const filter = store.prefs.likedFilter || "all";
  const entries = Object.entries(store.swipes).filter(([, s]) => ["like", "superlike", "applied", "interview", "offer"].includes(s.d)).sort((a, b) => (b[1].d === "superlike") - (a[1].d === "superlike") || new Date(b[1].at) - new Date(a[1].at));
  const cards = entries.map(([id]) => cardFor(id)).filter(Boolean).filter(c => filter === "all" || (filter === "todo" ? decision(c.id) !== "applied" && c.listing?.status !== "removed" : filter === "applied" ? decision(c.id) === "applied" : c.listing?.status === "removed"));
  root.innerHTML = `<div class="page"><h1>Liked</h1><p class="lead">${entries.length} saved. Tap one for her tailored CV, the listing, and the next step.</p>
    <div class="filters">${[["all", "All"], ["todo", "To apply"], ["applied", "Applied"], ["removed", "Removed or closed"]].map(([k, l]) => `<button class="f ${filter === k ? "on" : ""}" data-f="${k}">${l}</button>`).join("")}</div>
    <div class="rows">${cards.map(c => rowCard(c, `<div class="next-steps">
      <button class="btn slim" data-cv="${esc(c.id)}" ${unlocked() && (c.has_docs || (c.files || []).includes("cv_pdf")) ? "" : "disabled"}>${icon("download")}CV</button>
      <a class="btn slim" href="${esc(c.apply_url || c.url)}" target="_blank" rel="noopener">${icon("external")}Listing</a>
      ${decision(c.id) === "applied" ? "" : `<button class="btn slim like" data-applied="${esc(c.id)}">${icon("check")}Applied</button>`}</div>`)).join("") ||
      `<div class="panel"><h3>Nothing here yet</h3><p class="muted">Swipe right on a job in Discover and it lands here with its tailored CV.</p><a class="btn hot" href="#discover">${icon("cards")}Start swiping</a></div>`}</div></div>`;
  root.querySelectorAll("[data-f]").forEach(b => b.onclick = () => { store.prefs.likedFilter = b.dataset.f; savePrefs(); liked(root, {}); });
  root.querySelectorAll("[data-applied]").forEach(b => b.onclick = () => { decide(b.dataset.applied, "applied", { trackUndo: false }); toast(`${icon("check")} Marked as applied`); liked(root, {}); });
  root.querySelectorAll("[data-cv]").forEach(b => b.onclick = async () => {
    const card = cardFor(b.dataset.cv);
    if ((card.files || []).includes("cv_pdf")) {
      try { download(await fileBlob(`${card.id}-cv_pdf`, "application/pdf"), `${(store.priv?.profile?.name || "CV").replace(/\W+/g, "_")}_CV_${(card.company || "").replace(/\W+/g, "_")}.pdf`); return; } catch { /* editor fallback */ }
    }
    if (card.has_docs) { location.hash = `edit=${card.id}`; return; }
    toast("A tailored CV for this one is prepared on the next update.");
  });
  bindRows(root, "liked");
  if (params.open) { const card = cardFor(params.open); if (card) openSheet(card, "liked"); }
}

export function historyView(root) {
  const f = store.prefs.historyFilter || { when: "all", place: "all", q: "" };
  const now = Date.now();
  let entries = Object.entries(store.swipes).filter(([, s]) => s.d === "pass").sort((a, b) => new Date(b[1].at) - new Date(a[1].at));
  entries = entries.filter(([, s]) => f.when === "all" || now - new Date(s.at) < (f.when === "today" ? 86400000 : 7 * 86400000));
  let cards = entries.map(([id]) => cardFor(id)).filter(Boolean);
  if (f.place !== "all") cards = cards.filter(c => f.place === "thess" ? c.greece_remote === "onsite" : c.work_mode === "remote");
  if (f.q) cards = cards.filter(c => `${c.title} ${c.company}`.toLowerCase().includes(f.q.toLowerCase()));
  if (f.top) cards = cards.filter(c => ["exceptional", "apply", "worth"].includes(c.tier));
  root.innerHTML = `<div class="page"><h1>Passed</h1><p class="lead">Everything she swiped away. Bring any of them back.</p>
    <div class="search">${icon("search")}<input type="search" id="hq" placeholder="Search passed jobs" value="${esc(f.q)}"></div>
    <div class="filters">${[["all", "Any time"], ["today", "Today"], ["week", "This week"]].map(([k, l]) => `<button class="f ${f.when === k ? "on" : ""}" data-when="${k}">${l}</button>`).join("")}
      ${[["all", "Anywhere"], ["thess", "Thessaloniki"], ["remote", "Remote"]].map(([k, l]) => `<button class="f ${f.place === k ? "on" : ""}" data-place="${k}">${l}</button>`).join("")}
      <button class="f ${f.top ? "on" : ""}" data-top>Recommended only</button></div>
    <div class="rows">${cards.map(c => rowCard(c, `<div class="next-steps"><button class="btn slim" data-restore="${esc(c.id)}">${icon("restore")}Back to deck</button><button class="btn slim like" data-like="${esc(c.id)}">${icon("heart")}Save</button></div>`)).join("") || `<div class="panel muted">No passed jobs match.</div>`}</div></div>`;
  const save = () => { store.prefs.historyFilter = f; savePrefs(); historyView(root); };
  root.querySelector("#hq").oninput = e => { f.q = e.target.value; clearTimeout(root._t); root._t = setTimeout(save, 250); };
  root.querySelectorAll("[data-when]").forEach(b => b.onclick = () => { f.when = b.dataset.when; save(); });
  root.querySelectorAll("[data-place]").forEach(b => b.onclick = () => { f.place = b.dataset.place; save(); });
  root.querySelector("[data-top]").onclick = () => { f.top = !f.top; save(); };
  root.querySelectorAll("[data-restore]").forEach(b => b.onclick = () => { clearDecision(b.dataset.restore); toast("Back in the deck"); historyView(root); });
  root.querySelectorAll("[data-like]").forEach(b => b.onclick = () => { decide(b.dataset.like, "like", { trackUndo: false }); toast(`${icon("heart")} Saved`); historyView(root); });
  bindRows(root, "history");
}

export function browse(root) {
  const f = store.prefs.browse || { tier: "all", place: "all", sort: "priority", lang: false, fresh: false, q: "" };
  const view = store.prefs.browseView || "grid";
  let cards = store.feed.deck.slice();
  if (f.tier !== "all") cards = cards.filter(c => f.tier === "top" ? ["exceptional", "apply"].includes(c.tier) : f.tier === "worth" ? c.tier === "worth" : !["exceptional", "apply", "worth"].includes(c.tier));
  if (f.place !== "all") cards = cards.filter(c => f.place === "thess" ? c.greece_remote === "onsite" : c.work_mode === "remote");
  if (f.lang) cards = cards.filter(c => (c.languages || []).every(l => l.ok || l.level !== "required"));
  if (f.fresh) cards = cards.filter(c => Date.now() - new Date(c.first_seen) < 3 * 86400000);
  if (f.q) cards = cards.filter(c => `${c.title} ${c.company} ${c.location}`.toLowerCase().includes(f.q.toLowerCase()));
  if (f.sort === "new") cards.sort((a, b) => new Date(b.first_seen) - new Date(a.first_seen));
  if (f.sort === "deadline") cards.sort((a, b) => (a.deadline || "9999") .localeCompare(b.deadline || "9999"));
  const tile = c => `<button class="tile" data-id="${esc(c.id)}"><div class="img"><img src="${esc(imgSrc(c))}" alt="" loading="lazy" data-fallback="${esc(c.art || "art/remote.jpg")}"><span class="ribbon ${esc(c.tier)}">${esc(c.tier_label)}</span></div>
    <div class="body"><h3>${esc(c.title)}</h3><div class="sub muted small">${esc(c.company || "")} · ${esc(workLabel(c))}</div>
    <div class="chips" style="margin-top:6px">${decision(c.id) ? `<span class="tag ${decision(c.id) === "pass" ? "removed" : "liked"}">${decision(c.id) === "pass" ? "Passed" : "Saved"}</span>` : ""}<span class="chip">${esc(c.score)}</span>${languageChips(c, 2)}</div></div></button>`;
  root.innerHTML = `<div class="page"><h1>Browse</h1><p class="lead">Every open match, ranked. ${cards.length} shown.</p>
    <div class="search">${icon("search")}<input type="search" id="bq" placeholder="Title, company, place" value="${esc(f.q)}">
      <button class="icon-btn" id="bv" title="Switch view" style="box-shadow:none">${icon(view === "grid" ? "list" : "grid")}</button></div>
    <div class="filters">${[["all", "All"], ["top", "Highly recommended"], ["worth", "Worth a look"], ["other", "Other"]].map(([k, l]) => `<button class="f ${f.tier === k ? "on" : ""}" data-tier="${k}">${l}</button>`).join("")}
      ${[["all", "Anywhere"], ["thess", "Thessaloniki"], ["remote", "Remote"]].map(([k, l]) => `<button class="f ${f.place === k ? "on" : ""}" data-place="${k}">${l}</button>`).join("")}
      <button class="f ${f.lang ? "on" : ""}" data-lang>Her languages only</button><button class="f ${f.fresh ? "on" : ""}" data-fresh>New this week</button>
      ${[["priority", "Best first"], ["new", "Newest"], ["deadline", "Deadline"]].map(([k, l]) => `<button class="f ${f.sort === k ? "on" : ""}" data-sort="${k}">${l}</button>`).join("")}</div>
    <div class="${view === "grid" ? "grid" : "rows"}">${cards.map(c => view === "grid" ? tile(c) : rowCard(c)).join("") || `<div class="panel muted">Nothing matches these filters.</div>`}</div></div>`;
  const save = () => { store.prefs.browse = f; savePrefs(); browse(root); };
  root.querySelector("#bq").oninput = e => { f.q = e.target.value; clearTimeout(root._t); root._t = setTimeout(save, 250); };
  root.querySelector("#bv").onclick = () => { store.prefs.browseView = view === "grid" ? "list" : "grid"; savePrefs(); browse(root); };
  root.querySelectorAll("[data-tier]").forEach(b => b.onclick = () => { f.tier = b.dataset.tier; save(); });
  root.querySelectorAll("[data-place]").forEach(b => b.onclick = () => { f.place = b.dataset.place; save(); });
  root.querySelectorAll("[data-sort]").forEach(b => b.onclick = () => { f.sort = b.dataset.sort; save(); });
  root.querySelector("[data-lang]").onclick = () => { f.lang = !f.lang; save(); };
  root.querySelector("[data-fresh]").onclick = () => { f.fresh = !f.fresh; save(); };
  bindRows(root, "deck", { like: c => { decide(c.id, "like", { trackUndo: false }); toast(`${icon("heart")} Saved`); browse(root); }, pass: c => { decide(c.id, "pass", { trackUndo: false }); browse(root); } });
}

export function me(root) {
  const p = store.priv?.profile;
  const facts = store.priv?.facts || {};
  const h = store.feed.health;
  const swipeCount = Object.values(store.swipes);
  const opts = (key, values) => `<select data-fact="${key}">${values.map(([v, l]) => `<option value="${v}" ${String(facts[key]) === v ? "selected" : ""}>${l}</option>`).join("")}</select>`;
  const second = p?.experience?.[1]?.employer || "the second job", first = p?.experience?.[0]?.employer || "the first job";
  root.innerHTML = `<div class="page"><h1>${esc(p ? p.first_name || p.name : "Her job app")}</h1>
    <p class="lead">${swipeCount.filter(s => ["like", "superlike"].includes(s.d)).length} saved · ${swipeCount.filter(s => s.d === "applied").length} applied · ${swipeCount.filter(s => s.d === "pass").length} passed · ${({ synced: "synced across phones", syncing: "syncing…", offline: "offline, will sync later", local: "saved on this phone" })[store.syncState]}</p>
    <div class="panel"><h3>${icon("doc")} Her CV</h3>
      ${p ? `<p class="muted small">Edit the base CV and download it as Word or PDF. Tailored versions live on each liked job.</p><div class="chips" style="gap:8px"><a class="btn slim hot" href="#edit=base">${icon("edit")}Edit and download CV</a></div>`
        : `<p class="muted small">Her CV did not load. Reload the page. If it still fails, paste a link that contains the code:</p>
           <div class="row" style="display:flex;gap:8px"><input type="url" id="unlock-link" placeholder="Paste a link with the code" style="flex:1"><button class="btn slim primary" id="unlock">Unlock</button></div>`}
    </div>
    ${p ? `<div class="panel"><h3>${icon("shield")} Facts to confirm</h3><p class="muted small">Nothing waits for these. Until answered, CVs use the careful default.</p>
      <p class="small"><b>When did ${esc(second)} end?</b><br>${opts("role2_end", [["april-2026", "April 2026"], ["may-2026", "May 2026"], ["current", "Still there"]])}</p>
      <p class="small"><b>Can she travel abroad 2–4 times a year for 1–2 weeks?</b><br>${opts("travel_weeks", [["unknown", "Not sure"], ["yes", "Yes"], ["no", "No"]])}</p>
      <p class="small"><b>Would she work US hours (evenings in Greece)?</b><br>${opts("us_night_hours", [["unknown", "Not sure"], ["yes", "Yes"], ["no", "No"]])}</p>
      <p class="small"><b>${esc(first)}: refunds, subscriptions, app feedback, chatbot work</b><br>${opts("r1_tech_claims", [["unconfirmed", "Not confirmed"], ["confirmed", "Accurate, use it"], ["no", "Not accurate"]])}</p></div>` : ""}
    <div class="panel"><h3>${icon("bolt")} The search</h3>
      <p class="small">Last search ${esc(ago(h.last_cycle))} · ${h.healthy}/${h.total} sources healthy · ${esc(h.email ? "Next email briefing " + h.next_digest : "Email briefings not connected yet")}</p>
      <div class="chips" style="gap:8px"><a class="btn slim" href="#sources">Sources</a><a class="btn slim" href="#whynot">Why jobs were dropped</a><a class="btn slim" href="#radar">Companies to watch</a></div></div>
    <div class="panel"><h3>${icon("sparkle")} Put it on her home screen</h3>
      <p class="small muted">iPhone: tap Share, then “Add to Home Screen”. Android: tap the menu, then “Install app”. It then opens full-screen like a normal app.</p></div>
    <p class="muted small" style="margin:14px 4px">Location photos: Wikimedia Commons (${Object.values(store.feed.credits || {}).map(c => esc(c.author + ", " + c.license)).join("; ")}).</p></div>`;
  root.querySelectorAll("[data-fact]").forEach(s => s.onchange = () => { store.priv.facts[s.dataset.fact] = s.value; sendEvent("facts", { key: s.dataset.fact, value: s.value }); toast("Saved. CVs update in the next cycle."); });
  root.querySelector("#unlock")?.addEventListener("click", () => {
    const m = /[#&]k=([^&]+)/.exec(root.querySelector("#unlock-link").value);
    if (!m) return toast("That link has no unlock code in it.");
    localStorage.setItem("jr-key", decodeURIComponent(m[1]));
    location.reload();
  });
}

export function sourcesView(root) {
  const s = store.feed.sources;
  const group = st => s.filter(x => x.status === st);
  const row = x => `<div class="src-row"><span><b>${esc(x.label)}</b><br><span class="muted small">every ${x.interval} min · last good ${esc(ago(x.last_success))}${x.items != null ? ` · ${x.items} listings` : ""}${x.note ? " · " + esc(x.note) : ""}</span>${x.warning ? `<br><span class="deg small">${esc(x.warning)}</span>` : ""}${x.error ? `<br><span class="fail small">${esc(x.error)}</span>` : ""}</span><span class="${x.status === "healthy" ? "ok" : x.status === "failing" ? "fail" : "deg"}">${esc(x.status)}</span></div>`;
  root.innerHTML = `<div class="page"><h1>Sources</h1><p class="lead">${store.feed.health.healthy} of ${store.feed.health.total} healthy. Last search ${esc(ago(store.feed.health.last_cycle))}.</p>
    ${["degraded", "failing", "healthy", "pending"].map(st => group(st).length ? `<div class="panel"><h3>${{ healthy: "Healthy", degraded: "Degraded", failing: "Failing", pending: "Waiting" }[st]} (${group(st).length})</h3>${group(st).map(row).join("")}</div>` : "").join("")}
    <div class="panel"><h3>Manual only</h3>${store.feed.manual.map(m => `<div class="src-row"><span><a href="${esc(m.url)}" target="_blank" rel="noopener">${esc(m.name)}</a><br><span class="muted small">${esc(m.why)}</span></span><span class="muted">manual</span></div>`).join("")}</div></div>`;
}

export function whyNot(root) {
  const w = store.feed.why_not;
  const names = { "excluded:sales": "Sales", "excluded:customer_service": "Customer service", "excluded:engineering": "Engineering or IT", "excluded:hospitality": "Hospitality", "excluded:retail": "Retail", "excluded:trades": "Driving, warehouse, trades", "excluded:teaching": "Teaching", "excluded:health": "Health care", "excluded:finance_specialist": "Accounting", "excluded:legal": "Legal", "excluded:marketing": "Marketing", "excluded:moderation": "Moderation", "excluded:unpaid": "Unpaid", geography: "Wrong place or remote that excludes Greece", seniority: "Too senior", not_target_role: "Not an office role she targets", specialist_requirement: "Needs a degree or licence she lacks" };
  const rows = Object.entries(w.day || {}).sort((a, b) => b[1] - a[1]);
  root.innerHTML = `<div class="page"><h1>Why not?</h1><p class="lead">${w.raw_day} listings read in 24 hours. ${rows.reduce((a, [, n]) => a + n, 0)} dropped automatically.</p>
    <div class="panel">${rows.map(([k, n]) => `<div class="src-row"><span>${esc(names[k] || k)}</span><b>${n}</b></div>`).join("") || "<span class='muted'>No runs in the last day yet.</span>"}</div>
    <div class="panel"><h3>Recent examples</h3>${(w.examples || []).slice().reverse().map(e => `<div class="src-row"><span><a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.title)}</a><br><span class="muted small">${esc(e.company)} · ${esc(e.source)}</span></span><span class="muted small">${esc(names[e.reason] || e.reason)}</span></div>`).join("")}</div></div>`;
}

export function radarView(root) {
  const items = store.feed.radar || [];
  root.innerHTML = `<div class="page"><h1>Companies to watch</h1><p class="lead">No confirmed opening, but several independent signals say they are worth a speculative note.</p>
    ${items.map(r => `<div class="panel"><span class="tag super">No confirmed opening</span><h3 style="margin-top:6px">${esc(r.company)}</h3><ul class="why">${(r.signals || []).map(s => `<li>${esc(s)}</li>`).join("")}</ul><p class="small muted">${esc(r.angle)}</p>
      <div class="chips" style="gap:8px">${r.url ? `<a class="btn slim" href="${esc(r.url)}" target="_blank" rel="noopener">${icon("external")}Website</a>` : ""}${unlocked() ? `<a class="btn slim hot" href="#edit=radar:${encodeURIComponent(r.company)}">${icon("edit")}Speculative CV and note</a>` : ""}</div></div>`).join("") || "<div class='panel muted'>Nothing yet.</div>"}</div>`;
}
