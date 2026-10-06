import { decryptBytes, decryptJson } from "./crypto.js";

const REPO = "studio-kenotomia/madeline-jobs";
const LOCAL = !/github\.io$|studio-kenotomia\.com$/.test(location.hostname);
const state = { pass: "", data: null, local: JSON.parse(localStorage.getItem("mj-local") || "{}"), bridge: null };

export const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
const $ = selector => document.querySelector(selector);
const saveLocal = () => localStorage.setItem("mj-local", JSON.stringify(state.local));

function ago(iso) {
  if (!iso) return "never";
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 48 * 60) return `${Math.round(minutes / 60)} h ago`;
  return `${Math.round(minutes / 1440)} days ago`;
}

export function allJobs() {
  const d = state.data;
  const seen = new Map();
  for (const list of [...Object.values(d.tiers), ...Object.values(d.overflow || {}), d.tracked]) for (const job of list) seen.set(job.id, job);
  return [...seen.values()];
}
export const findJob = id => allJobs().find(j => j.id === id) || state.data.archive.find(j => j.id === id);
const localStatus = id => state.local[id]?.status;

export async function command(title, optimistic) {
  if (optimistic) { state.local[optimistic.id] = { ...(state.local[optimistic.id] || {}), ...optimistic.patch }; saveLocal(); }
  if (LOCAL) {
    const response = await fetch("api/command", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title }) });
    if (response.ok) return toast("Sent. The cloud run applies it within a minute or two.");
  }
  const url = `https://github.com/${REPO}/issues/new?` + new URLSearchParams({ title, body: "Sent from the job dashboard. Only issues opened by the repository owner are applied." });
  window.open(url, "_blank", "noopener");
  toast("GitHub opens with the command filled in. Press Create, and the next run applies it.");
}

function toast(text) {
  const el = document.createElement("div");
  el.className = "banner";
  el.style.cssText = "position:fixed;left:12px;right:12px;bottom:12px;z-index:20";
  el.textContent = text;
  document.body.append(el);
  setTimeout(() => el.remove(), 5000);
}

async function fetchText(path) {
  const response = await fetch(path + "?t=" + Date.now(), { cache: "no-store" });
  if (!response.ok) throw new Error(`${path} ${response.status}`);
  return response.text();
}

export async function fileBlob(name, type) {
  const bytes = await decryptBytes(state.pass, await fetchText(`files/${name}.enc`));
  return new Blob([bytes], { type });
}

export async function photoUrl() {
  if (state.photo) return state.photo;
  try {
    state.photo = URL.createObjectURL(await fileBlob("photo", "image/png"));
  } catch { state.photo = ""; }
  return state.photo;
}

async function unlock(pass) {
  state.data = await decryptJson(pass, await fetchText("payload.enc"));
  state.pass = pass;
  if (LOCAL) {
    try { state.bridge = await (await fetch("api/bridge/status")).json(); } catch { state.bridge = null; }
  }
}

function statusLine() {
  const h = state.data.health;
  const parts = [
    `Last search ${ago(h.last_cycle)}`,
    `${h.healthy}/${h.total} sources healthy`,
    h.email ? `Next digest ${h.next_digest}` : "Email not connected",
    state.bridge ? (state.bridge.online ? "Apply Bridge online" : "Apply Bridge offline") : "Apply Bridge runs on the Mac",
  ];
  $("#status-line").textContent = parts.join(" · ");
}

function tierLabel(tier) {
  return { exceptional: "Exceptional", apply: "Apply today", worth: "Worth considering", verify: "Verify location", stretch: "Stretch", archive: "Archive" }[tier] || tier;
}

function money(salary) {
  if (!salary || !salary.published || !salary.min) return "";
  return `${salary.min}${salary.max && salary.max !== salary.min ? "–" + salary.max : ""} ${salary.currency || ""} ${salary.period || ""}`.trim();
}

export function card(job, { compact = false } = {}) {
  const status = localStatus(job.id) || job.status;
  const remote = { onsite: "Thessaloniki", confirmed: "Remote, Greece allowed", likely: "Remote, Greece likely", unclear: "Remote, Greece unclear" }[job.greece_remote] || "";
  const badges = (job.badges || []).map(b => `<span class="badge ${/Just|Posted today|Closing/.test(b) ? "hot" : ""}">${esc(b)}</span>`).join("");
  const reasons = (job.reasons || []).slice(0, compact ? 2 : 3).map(r => `<li>${esc(r)}</li>`).join("");
  const risk = [...(job.blockers || []).map(b => `<li class="block">${esc(b)}</li>`), ...(job.gaps || []).slice(0, 1).map(g => `<li class="gap">${esc(g)}</li>`), ...(job.unknowns || []).slice(0, 1).map(u => `<li class="gap">${esc(u)}</li>`)].join("");
  const pay = money(job.salary);
  const docs = { draft: "CV draft ready", needs_fix: "CV needs a fix", frozen_submitted_version: "Sent version frozen", not_generated: "No CV yet" }[job.doc_status] || "";
  return `<article class="card" data-id="${esc(job.id)}">
    <div class="row" style="justify-content:space-between"><span class="tier ${esc(job.tier)}">${esc(tierLabel(job.tier))}</span><strong>${esc(job.score)}</strong></div>
    <h3>${esc(job.title)}</h3>
    <div class="meta">${esc(job.company)} · ${esc(job.location || "")}${remote ? " · " + esc(remote) : ""}</div>
    <div class="meta small">First seen ${esc(ago(job.first_seen))} · posted ${esc(job.posted || "unknown")}${job.deadline ? " · deadline " + esc(job.deadline) : ""}${pay ? " · " + esc(pay) : ""}${docs ? " · " + esc(docs) : ""}${status && status !== "none" ? " · <b>" + esc(status) + "</b>" : ""}</div>
    <div class="badges">${badges}</div>
    <ul class="tight">${reasons}${risk}</ul>
    <div class="actions">
      <a class="btn primary" href="#job=${esc(job.id)}">Open analysis</a>
      <a class="btn" href="#job=${esc(job.id)}&tab=docs">Documents</a>
      <a class="btn" href="#job=${esc(job.id)}&tab=apply">Apply</a>
      ${compact ? "" : `<button data-act="saved">Save</button><button data-act="skipped">Skip</button>`}
    </div>
  </article>`;
}

function bindCards(root) {
  root.querySelectorAll("article.card button[data-act]").forEach(button => {
    button.onclick = () => {
      const id = button.closest("article").dataset.id;
      command(`status ${id} ${button.dataset.act}`, { id, patch: { status: button.dataset.act } });
      render();
    };
  });
}

function viewToday() {
  const d = state.data;
  const visible = list => list.filter(j => !["skipped", "submitted"].includes(localStatus(j.id)));
  const section = (key, title, empty) => {
    const list = visible(d.tiers[key] || []);
    const more = visible((d.overflow || {})[key] || []);
    return `<h2>${title} <span class="count">${list.length}${more.length ? " + " + more.length : ""}</span></h2>` + (list.length ? list.map(j => card(j)).join("") : `<p class="muted">${empty}</p>`) +
      (more.length ? `<p><button data-more="${key}">Show ${more.length} more in ${title.toLowerCase()}</button></p><div class="hidden" id="more-${key}">${more.map(j => card(j)).join("")}</div>` : "");
  };
  const facts = Object.entries(d.facts).filter(([k, v]) => ["role2_end", "travel_weeks", "us_night_hours", "r1_tech_claims"].includes(k) && ["unknown", "unconfirmed"].includes(String(v)));
  const radar = (d.radar || []).slice(0, 3).map(r => `<article class="card"><span class="tier verify">No confirmed opening</span><h3>${esc(r.company)}</h3><p>${esc(r.why)}</p><p class="muted small">${esc(r.angle)} Confidence: ${esc(r.confidence)}.</p><div class="actions"><a class="btn" href="#radar=${encodeURIComponent(r.company)}">Prepare a speculative package</a>${r.url ? `<a class="btn" href="${esc(r.url)}" target="_blank" rel="noopener">Company site</a>` : ""}</div></article>`).join("");
  const tracked = d.tracked.filter(j => j.status && j.status !== "none");
  const why = d.why_not;
  const dropped = Object.values(why.day || {}).reduce((a, b) => a + b, 0);
  $("#view").innerHTML = `
    ${facts.length ? `<div class="banner">${facts.length} fact${facts.length > 1 ? "s" : ""} still unconfirmed. Defaults stay conservative. <a href="#facts">Review</a></div>` : ""}
    ${!d.health.email ? `<div class="banner">Email alerts are not connected yet. Searching still runs every 20 minutes.</div>` : ""}
    ${section("exceptional", "Exceptional", "None right now. That is normal.")}
    ${section("apply", "Apply today", "Nothing strong enough today.")}
    ${section("worth", "Worth considering", "None in this band.")}
    ${(d.tiers.verify || []).length ? section("verify", "Verify location first", "") : ""}
    <h2>Opportunity radar <span class="count">${(d.radar || []).length}</span></h2>${radar || `<p class="muted">No company has enough independent signals yet.</p>`}
    ${tracked.length ? `<h2>Prepared and applied</h2>` + tracked.map(j => card(j, { compact: true })).join("") : ""}
    <h2><button id="toggle-stretch">Show stretch roles (${(d.tiers.stretch || []).length})</button></h2>
    <div id="stretch" class="hidden">${(d.tiers.stretch || []).map(j => card(j, { compact: true })).join("")}</div>
    <p class="muted small">${why.raw_day} listings read in the last 24 hours. ${dropped} were dropped automatically. <a href="#whynot">See why</a>.</p>`;
  $("#toggle-stretch").onclick = () => $("#stretch").classList.toggle("hidden");
  document.querySelectorAll("[data-more]").forEach(b => b.onclick = () => { $("#more-" + b.dataset.more).classList.toggle("hidden"); b.remove(); });
  bindCards($("#view"));
}

function viewSearch(query = "") {
  const d = state.data;
  const pool = [...allJobs(), ...d.archive];
  const q = query.toLowerCase();
  const hits = pool.filter(j => !q || `${j.title} ${j.company} ${j.location}`.toLowerCase().includes(q)).slice(0, 120);
  $("#view").innerHTML = `<h2>Search everything tracked</h2>
    <div class="row"><input type="search" id="q" value="${esc(query)}" placeholder="Title, company or place" style="flex:1"><button id="go">Search</button></div>
    <h2>Add a job by link</h2>
    <div class="row"><input type="url" id="import-url" placeholder="https://… a listing a friend sent" style="flex:1"><button id="import">Import</button></div>
    <p class="muted small">The next run fetches it, scores it and prepares documents if it qualifies.</p>
    <h2>${hits.length} result${hits.length === 1 ? "" : "s"}</h2>
    ${hits.map(j => `<div class="src"><span><a href="#job=${esc(j.id)}">${esc(j.title)}</a> <span class="muted">· ${esc(j.company)} · ${esc(j.location || "")}</span></span><span class="tier ${esc(j.tier)}">${esc(j.score)} ${esc(tierLabel(j.tier))}${j.open_status && j.open_status !== "open" ? " · " + esc(j.open_status) : ""}</span></div>`).join("")}`;
  $("#go").onclick = () => viewSearch($("#q").value);
  $("#q").onkeydown = e => { if (e.key === "Enter") viewSearch($("#q").value); };
  $("#import").onclick = () => { const url = $("#import-url").value.trim(); if (/^https?:\/\//.test(url)) command(`import ${url}`); };
}

function viewRadar(company) {
  const d = state.data;
  const pick = company ? d.radar.find(r => r.company === company) : null;
  if (pick) {
    import("./studio.js").then(m => m.speculative(pick, d, state));
    return;
  }
  $("#view").innerHTML = `<h2>Opportunity radar</h2><p class="muted">Companies with no confirmed suitable opening, shown only with at least two independent signals or an explicit invitation for CVs.</p>
    ${(d.radar || []).map(r => `<article class="card"><span class="tier verify">${esc(r.label)}</span><h3>${esc(r.company)}</h3><ul class="tight">${r.signals.map(s => `<li>${esc(s)}</li>`).join("")}</ul><p class="muted small">${esc(r.angle)}</p><div class="actions"><a class="btn primary" href="#radar=${encodeURIComponent(r.company)}">Prepare speculative CV and message</a></div></article>`).join("") || "<p class='muted'>Nothing yet.</p>"}
    <h2>Company watch list <span class="count">${d.companies.length}</span></h2>
    ${d.companies.slice(0, 80).map(c => `<div class="src"><span>${esc(c.name)} ${c.thessaloniki ? "<span class='badge'>Thessaloniki</span>" : ""}<br><span class="muted small">${esc((c.signals || []).slice(0, 2).join(" "))}</span></span><span class="muted small">${esc(c.ats || "")} · ${c.history} roles seen</span></div>`).join("")}`;
}

function viewSources() {
  const d = state.data;
  const groups = { healthy: [], degraded: [], failing: [], pending: [] };
  for (const s of d.sources) (groups[s.status] || groups.pending).push(s);
  const row = s => `<div class="src"><span><b>${esc(s.label)}</b><br><span class="muted small">every ${s.interval} min · last success ${esc(ago(s.last_success))} · ${s.items ?? "–"} items · next ${esc(s.next_run ? ago(s.next_run).replace(" ago", "") : "soon")}${s.note ? " · " + esc(s.note) : ""}</span>${s.warning ? `<br><span class="gap small">${esc(s.warning)}</span>` : ""}${s.error ? `<br><span class="fail small">${esc(s.error)}</span>` : ""}</span><span class="${s.status === "healthy" ? "ok" : s.status === "failing" ? "fail" : "deg"}">${esc(s.status)}</span></div>`;
  $("#view").innerHTML = `<h2>Automated and healthy <span class="count">${groups.healthy.length}</span></h2>${groups.healthy.map(row).join("")}
    <h2>Degraded <span class="count">${groups.degraded.length}</span></h2>${groups.degraded.map(row).join("") || "<p class='muted'>None.</p>"}
    <h2>Failing <span class="count">${groups.failing.length}</span></h2>${groups.failing.map(row).join("") || "<p class='muted'>None.</p>"}
    <h2>Waiting for first run <span class="count">${groups.pending.length}</span></h2>${groups.pending.map(row).join("") || "<p class='muted'>None.</p>"}
    <h2>Manual only, on purpose</h2>${d.manual.map(m => `<div class="src"><span><a href="${esc(m.url)}" target="_blank" rel="noopener">${esc(m.name)}</a><br><span class="muted small">${esc(m.why)}</span></span><span class="muted">manual</span></div>`).join("")}
    <h2>Planned, needs a key</h2><div class="src"><span>Web-search discovery (Brave Search API)<br><span class="muted small">Finds employers the system does not know yet. Add a BRAVE_API_KEY secret to turn it on.</span></span><span class="${d.health.search_api ? "ok" : "muted"}">${d.health.search_api ? "on" : "off"}</span></div>
    <h2>Recent runs</h2>${d.runs.slice().reverse().slice(0, 12).map(r => `<div class="src"><span>${esc(new Date(r.at).toLocaleString())} · ${r.sources.length} sources · ${r.raw} read · ${r.new} new<br><span class="muted small">${esc((r.mail || []).join(" "))}</span></span><span class="muted">${r.duration}s</span></div>`).join("")}`;
}

function viewWhyNot() {
  const w = state.data.why_not;
  const names = { "excluded:sales": "Sales", "excluded:customer_service": "Customer service or support", "excluded:engineering": "Engineering or IT", "excluded:hospitality": "Hospitality", "excluded:retail": "Retail", "excluded:trades": "Trades, driving, warehouse", "excluded:teaching": "Teaching", "excluded:health": "Health care", "excluded:finance_specialist": "Accounting or finance specialist", "excluded:legal": "Legal", "excluded:marketing": "Marketing", "excluded:moderation": "Content moderation", geography: "Wrong city, or remote that excludes Greece", seniority: "Too senior", not_target_role: "Not an office role she targets", specialist_requirement: "Needs a degree or licence she lacks" };
  const rows = Object.entries(w.day || {}).sort((a, b) => b[1] - a[1]);
  $("#view").innerHTML = `<h2>The last 24 hours</h2><p>${w.raw_day} listings read. ${rows.reduce((a, [, n]) => a + n, 0)} dropped. ${w.ranked_day ? "" : ""}</p>
    ${rows.map(([k, n]) => `<div class="src"><span>${esc(names[k] || k)}</span><span>${n}</span></div>`).join("")}
    <h2>Recent examples</h2><p class="muted small">Proof the filter works. Open any to check it was dropped for the right reason.</p>
    ${w.examples.slice().reverse().map(e => `<div class="src"><span><a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.title)}</a> <span class="muted">· ${esc(e.company)} · ${esc(e.source)}</span></span><span class="muted small">${esc(names[e.reason] || e.reason)}</span></div>`).join("")}`;
}

function viewFacts() {
  const f = state.data.facts;
  const roles = state.data.profile.experience || [];
  const second = roles[1] || { employer: "the second role" };
  const first = roles[0] || { employer: "the first role" };
  const opts = (key, values) => `<select data-key="${key}">${values.map(([v, label]) => `<option value="${v}" ${String(f[key]) === v ? "selected" : ""}>${label}</option>`).join("")}</select>`;
  $("#view").innerHTML = `<h2>Facts to confirm</h2><p class="muted">Nothing here blocks the search. Until you answer, the system uses the conservative choice.</p>
    <div class="card"><b>When did ${esc(second.employer)} end?</b><p class="muted small">CVs disagree: April, May, or current. Default April 2026.</p>${opts("role2_end", [["april-2026", "April 2026"], ["may-2026", "May 2026"], ["current", "Still there"]])}</div>
    <div class="card"><b>Can she travel abroad 2–4 times a year for one to two weeks?</b><p class="muted small">Canonical and similar remote companies require it.</p>${opts("travel_weeks", [["unknown", "Unknown"], ["yes", "Yes"], ["no", "No"]])}</div>
    <div class="card"><b>Would she work US hours (evening and night in Greece)?</b>${opts("us_night_hours", [["unknown", "Unknown"], ["yes", "Yes"], ["no", "No"]])}</div>
    <div class="card"><b>${esc(first.employer)}: refunds, subscriptions, app feedback and chatbot work</b><p class="muted small">Only on one CV that is not in this workspace. Unused until confirmed.</p>${opts("r1_tech_claims", [["unconfirmed", "Unconfirmed"], ["confirmed", "Confirmed, OK to use"], ["no", "Not accurate"]])}</div>
    <div class="card"><b>Salary floor (EUR per month, optional)</b><div class="row"><input type="search" data-key="salary_floor_eur_month" value="${esc(f.salary_floor_eur_month || "")}" placeholder="e.g. 1100"></div></div>
    <div class="card"><b>Phone number on CVs</b><p class="muted small">${esc(state.data.profile.phone)} ${state.data.profile.phone_confirmed ? "(confirmed)" : "(likely current, from her Thessaloniki CV)"}</p></div>
    <button class="primary" id="save-facts">Save answers</button>`;
  $("#save-facts").onclick = () => {
    for (const el of document.querySelectorAll("[data-key]")) {
      const value = el.value.trim();
      if (value && String(f[el.dataset.key]) !== value) command(`facts ${el.dataset.key}=${value}`);
    }
  };
}

async function viewJob(id, tab) {
  const job = findJob(id);
  if (!job) { $("#view").innerHTML = `<p>This job is no longer in the list. <a href="#">Back</a></p>`; return; }
  const studio = await import("./studio.js");
  studio.jobView(job, tab || "opportunity", state);
}

export function render() {
  const hash = decodeURIComponent(location.hash.slice(1));
  const params = Object.fromEntries(hash.split("&").map(p => p.split("=")));
  window.scrollTo(0, 0);
  if (params.job) return viewJob(params.job, params.tab);
  if ("search" in params) return viewSearch();
  if ("radar" in params) return viewRadar(params.radar || "");
  if ("sources" in params) return viewSources();
  if ("whynot" in params) return viewWhyNot();
  if ("facts" in params) return viewFacts();
  viewToday();
}

async function start(pass, remember) {
  $("#gate-msg").textContent = "Opening…";
  try {
    await unlock(pass);
  } catch (error) {
    $("#gate-msg").textContent = "That passphrase did not open the list.";
    localStorage.removeItem("mj-pass");
    return;
  }
  if (remember) localStorage.setItem("mj-pass", pass);
  $("#gate").classList.add("hidden");
  $("#app").classList.remove("hidden");
  statusLine();
  render();
}

window.addEventListener("hashchange", () => state.data && render());
$("#gate-form").onsubmit = event => { event.preventDefault(); start($("#pass").value, $("#remember").checked); };
const remembered = localStorage.getItem("mj-pass");
if (remembered) start(remembered, true);
setInterval(async () => { if (state.pass && document.visibilityState === "visible") { try { await unlock(state.pass); statusLine(); } catch {} } }, 5 * 60 * 1000);
export { state, LOCAL, REPO, ago, tierLabel, money, toast };
