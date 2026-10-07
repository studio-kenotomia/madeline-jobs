import { Editor, StarterKit, Underline, TextAlign, TextStyle, Color, Link, docx } from "./vendor/editor.js";
import { store, fileBlob, photoUrl, cardFor } from "./store.js";
import { esc, toast, download } from "./ui.js";
import { icon } from "./icons.js";

const TEMPLATES = {
  "professional-operations": { accent: "#1f3a5f", font: "Georgia, serif" },
  "modern-executive": { accent: "#2d2d2d", font: "'Helvetica Neue', Arial, sans-serif" },
  "research-policy": { accent: "#3b4a2f", font: "Palatino, Georgia, serif" },
  "environment-projects": { accent: "#24584a", font: "'Helvetica Neue', Arial, sans-serif" },
  "international-mobility": { accent: "#7a3b1d", font: "Georgia, serif" },
};
const FORBIDDEN = [
  [/greek\s*\(?(b1|b2|c1|c2|fluent|native|proficient|advanced)/i, "Greek is A2. The text says something higher."],
  [/(fluent|native|proficient) (in )?greek/i, "Greek is A2. The text says something higher."],
  [/professional gis|gis (specialist|analyst|officer)|years of gis/i, "GIS is academic training, not a paid GIS job."],
  [/(professional|paid) (esg|sustainability|research)|esg (analyst|consultant|specialist) at/i, "The master's is not paid ESG or research employment."],
  [/environmental scientist|biologist|ecologist/i, "She is not a working scientist."],
  [/lawyer|attorney|legal counsel|law firm/i, "Her visa role was at a placement agency, not a law firm."],
  [/dive (certificate|certification)|open water|driving licen[cs]e|driver'?s licen[cs]e/i, "No dive or driving qualification is on her CVs."],
  [/biology degree|degree in biology/i, "She has no biology degree."],
  [/grant[- ]writ(er|ing) experience|experienced grant/i, "No grant-writing experience."],
  [/\bphd\b|doctorate/i, "No doctorate."],
  [/(managed|led|supervised) (a )?team/i, "No team-management experience on her CVs."],
  [/chatbot|subscription|refund|late payment|app feedback/i, "Unconfirmed claims about refunds, subscriptions, app feedback or a chatbot."],
  [/atlas\.ti/i, "ATLAS.ti is not confirmed on the CVs here."],
  [/\b\d{2,}\s*(%|percent|cases|clients|applications|candidates|files)\b/i, "An unsupported number or metric appears."],
];

function lint(text, kind) {
  const issues = [];
  const low = text.toLowerCase();
  for (const role of store.priv.profile.experience || []) {
    const employer = role.employer.toLowerCase(), title = role.title.toLowerCase();
    if ((kind === "cv" || /sales/.test(title)) && low.includes(employer) && !low.includes(title)) issues.push(`${role.employer} appears without the real title ${role.title}.`);
    if (new RegExp(`(operations|account|office) (manager|coordinator|lead) (at|with) ${employer.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`).test(low)) issues.push(`The ${role.employer} title was altered.`);
  }
  if (store.priv.facts?.r1_tech_claims === "confirmed") FORBIDDEN.splice(11, 1);
  for (const [pattern, message] of FORBIDDEN) {
    const hit = low.match(pattern);
    if (hit && !new RegExp("(no|not|without)[^.]{0,40}" + hit[0].replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).test(low)) issues.push(message);
  }
  return [...new Set(issues)];
}

function cvBody(model) {
  const out = [];
  for (const s of model.sections) {
    out.push(`<h2>${esc(s.title)}</h2>`);
    if (s.type === "summary") out.push(`<p>${esc(s.text)}</p>`);
    else if (s.type === "experience") for (const e of s.entries) out.push(`<h3>${esc(e.title)} — ${esc(e.employer)}</h3><p><em>${esc(e.note ? e.note + " · " : "")}${esc(e.place)} · ${esc(e.dates)}</em></p><ul>${e.bullets.map(b => `<li><p>${esc(b.text)}</p></li>`).join("")}</ul>`);
    else if (s.type === "education") for (const e of s.entries) out.push(`<h3>${esc(e.credential)}</h3><p><em>${esc(e.school)}${e.place ? " · " + esc(e.place) : ""}${e.dates ? " · " + esc(e.dates) : ""}</em></p>${e.lines.length ? `<ul>${e.lines.map(l => `<li><p>${esc(l)}</p></li>`).join("")}</ul>` : ""}`);
    else out.push(`<p>${s.items.map(i => esc(i.label)).join(" · ")}</p>`);
  }
  return out.join("");
}

function coverBody(model, title, company) {
  return `<p>${esc(model.name)}<br>${esc(model.contact)}</p>${title ? `<p>Re: ${esc(title)}${company ? ", " + esc(company) : ""}</p>` : ""}<p>${esc(model.greeting)}</p>` +
    model.paragraphs.map(p => `<p>${esc(p.text)}</p>`).join("") + `<p>${esc(model.signoff)}<br>${esc(model.name)}</p>`;
}

const draftKey = id => `jr-draft-${id}`;
const loadDraft = id => { try { return JSON.parse(localStorage.getItem(draftKey(id)) || "null"); } catch { return null; } };
const storeDraft = (id, d) => localStorage.setItem(draftKey(id), JSON.stringify({ ...d, at: new Date().toISOString() }));

const editor = (el, html, onUpdate) => new Editor({ element: el, content: html, onUpdate: ({ editor }) => onUpdate(editor),
  extensions: [StarterKit, Underline, TextStyle, Color, Link.configure({ openOnClick: false }), TextAlign.configure({ types: ["heading", "paragraph"] })] });

const toolbar = extra => `<div class="toolbar">
  <button data-cmd="undo" title="Undo">↶</button><button data-cmd="redo" title="Redo">↷</button>
  <button data-cmd="bold"><b>B</b></button><button data-cmd="italic"><i>I</i></button><button data-cmd="underline"><u>U</u></button>
  <select data-cmd="block"><option value="p">Text</option><option value="h2">Section</option><option value="h3">Entry</option></select>
  <button data-cmd="bullet">•</button><button data-cmd="left">⟸</button><button data-cmd="center">≡</button><button data-cmd="right">⟹</button>
  <input type="color" data-cmd="color" value="#1b1b1b" title="Colour"><button data-cmd="link">Link</button>${extra || ""}</div>`;

function bindToolbar(bar, get) {
  bar.querySelectorAll("[data-cmd]").forEach(el => {
    const run = () => {
      const c = get().chain().focus(), cmd = el.dataset.cmd;
      if (cmd === "undo") c.undo().run(); else if (cmd === "redo") c.redo().run();
      else if (cmd === "bold") c.toggleBold().run(); else if (cmd === "italic") c.toggleItalic().run(); else if (cmd === "underline") c.toggleUnderline().run();
      else if (cmd === "bullet") c.toggleBulletList().run(); else if (["left", "center", "right"].includes(cmd)) c.setTextAlign(cmd).run();
      else if (cmd === "color") c.setColor(el.value).run();
      else if (cmd === "block") el.value === "p" ? c.setParagraph().run() : c.setHeading({ level: el.value === "h2" ? 2 : 3 }).run();
      else if (cmd === "link") { const url = prompt("Link address"); url ? c.setLink({ href: url }).run() : c.unsetLink().run(); }
    };
    if (el.tagName === "SELECT" || el.type === "color") el.onchange = run; else el.onclick = run;
  });
}

function moveSection(ed, dir) {
  const nodes = ed.getJSON().content || [];
  const { from } = ed.state.selection;
  let current = -1;
  ed.state.doc.forEach((node, offset, index) => { if (offset <= from) current = index; });
  const starts = nodes.map((n, i) => n.type === "heading" && n.attrs?.level === 2 ? i : -1).filter(i => i >= 0);
  const si = starts.filter(s => s <= current).length - 1;
  if (si < 0) return toast("Tap inside a section first.");
  const ranges = starts.map((s, i) => nodes.slice(s, starts[i + 1] ?? nodes.length));
  const target = si + dir;
  if (target < 0 || target >= ranges.length) return;
  [ranges[si], ranges[target]] = [ranges[target], ranges[si]];
  ed.commands.setContent({ type: "doc", content: [...nodes.slice(0, starts[0]), ...ranges.flat()] }, true);
}

const ALIGN = { left: docx.AlignmentType.LEFT, center: docx.AlignmentType.CENTER, right: docx.AlignmentType.RIGHT };
function runs(node, base = {}) {
  return (node.content || []).flatMap(ch => {
    if (ch.type === "hardBreak") return [new docx.TextRun({ break: 1 })];
    if (ch.type !== "text") return [];
    const m = Object.fromEntries((ch.marks || []).map(x => [x.type, x.attrs || true]));
    const run = new docx.TextRun({ text: ch.text, bold: !!m.bold || base.bold, italics: !!m.italic, underline: m.underline ? {} : undefined, color: m.textStyle?.color?.replace("#", "") || base.color, size: base.size });
    return [m.link?.href ? new docx.ExternalHyperlink({ link: m.link.href, children: [new docx.TextRun({ text: ch.text, style: "Hyperlink" })] }) : run];
  });
}
function blocks(json, accent) {
  const out = [];
  for (const n of json.content || []) {
    const alignment = ALIGN[n.attrs?.textAlign];
    if (n.type === "heading") {
      const h2 = n.attrs.level === 2;
      out.push(new docx.Paragraph({ alignment, spacing: { before: h2 ? 200 : 100, after: 40 }, border: h2 ? { bottom: { color: "CCCCCC", style: docx.BorderStyle.SINGLE, size: 4, space: 1 } } : undefined, children: runs(n, { bold: true, color: h2 ? accent : undefined, size: h2 ? 21 : 22 }) }));
    } else if (n.type === "paragraph") out.push(new docx.Paragraph({ alignment, spacing: { after: 60 }, children: runs(n, { size: 21 }) }));
    else if (n.type === "bulletList" || n.type === "orderedList") for (const item of n.content || []) for (const p of item.content || []) out.push(new docx.Paragraph({ bullet: { level: 0 }, spacing: { after: 20 }, children: runs(p, { size: 21 }) }));
  }
  return out;
}

async function exportDocx(kind, ed, settings, filename) {
  const accent = (TEMPLATES[settings.template] || TEMPLATES["professional-operations"]).accent.replace("#", "");
  const p = store.priv.profile;
  const children = [];
  if (kind === "cv") {
    const top = [new docx.Paragraph({ children: [new docx.TextRun({ text: p.name, bold: true, size: 40, color: accent })] }),
      new docx.Paragraph({ children: [new docx.TextRun({ text: `Thessaloniki, Greece · ${p.phone} · ${p.email}`, size: 20 })] }),
      new docx.Paragraph({ children: [new docx.TextRun({ text: "Dutch and British national · EU right to work", size: 20 })] })];
    if (settings.photo !== "off") {
      try {
        const data = new Uint8Array(await (await fetch(await photoUrl())).arrayBuffer());
        const image = [new docx.Paragraph({ children: [new docx.ImageRun({ type: "png", data, transformation: { width: 96, height: 118 } })] })];
        const cells = settings.photo === "right" ? [top, image] : [image, top];
        children.push(new docx.Table({ width: { size: 100, type: docx.WidthType.PERCENTAGE }, borders: docx.TableBorders.NONE,
          rows: [new docx.TableRow({ children: cells.map((c, i) => new docx.TableCell({ children: c, borders: docx.TableBorders.NONE, width: { size: (settings.photo === "right" ? i === 1 : i === 0) ? 18 : 82, type: docx.WidthType.PERCENTAGE } })) })] }));
      } catch { children.push(...top); }
    } else children.push(...top);
  }
  children.push(...blocks(ed.getJSON(), accent));
  const doc = new docx.Document({ styles: { default: { document: { run: { font: "Calibri", size: 21 } } } },
    sections: [{ properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 794, bottom: 794, left: 850, right: 850 } } }, children }] });
  download(await docx.Packer.toBlob(doc), filename);
}

function fitPaper(root) {
  const width = root.querySelector(".paper-wrap").clientWidth;
  const scale = Math.min(1, width / 794);
  root.querySelectorAll(".paper").forEach(p => {
    p.style.setProperty("--paper-scale", scale);
    p.style.transform = scale < 1 ? `scale(${scale})` : "";
    p.parentElement.style.height = scale < 1 ? `${p.offsetHeight * scale + 12}px` : "";
  });
}

export async function open(root, id) {
  const priv = store.priv;
  let model, cover, title = "", company = "", files = [], ai = "unknown", frozen = false;
  if (id === "base") { model = priv.base.cv_model; title = "Base CV"; }
  else if (id.startsWith("radar:")) { const r = priv.radar_docs[decodeURIComponent(id.slice(6))]; if (r) { model = r.cv_model; cover = r.cover_model; company = decodeURIComponent(id.slice(6)); title = "Speculative application"; } }
  else {
    const d = priv.docs[id];
    const card = cardFor(id);
    if (d) { model = d.cv_model; cover = d.cover_model; files = d.files || []; frozen = d.frozen; }
    title = card?.title || ""; company = card?.company || ""; ai = card?.ai_policy || "unknown";
  }
  if (!model) { root.innerHTML = `<div class="page"><h1>No CV yet</h1><p class="lead">Tailored CVs are made for her top matches in the next cycle.</p><a class="btn" href="#liked">Back</a></div>`; return; }
  const saved = loadDraft(id) || {};
  const settings = { template: saved.template || model.template, photo: saved.photo || "left", pages: saved.pages || 1 };
  const docs = priv.docs[id];
  if (settings.pages === 2) model = (id === "base" ? priv.base.cv_model_2 : docs?.cv_model_2) || model;
  const tpl = TEMPLATES[settings.template] || TEMPLATES["professional-operations"];
  const photo = await photoUrl();
  const p = priv.profile;
  root.innerHTML = `<div class="page">
    <p><a href="${id === "base" ? "#me" : id.startsWith("radar:") ? "#radar" : `#liked&open=${esc(id)}`}" class="btn slim">← Back</a></p>
    <h1>${esc(title || "CV")}</h1><p class="lead">${esc(company)}${frozen ? " · this is the version that was sent" : ""}</p>
    ${ai === "prohibited" ? `<div class="panel" style="background:#fff2d9">This employer bans AI-written answers. Send the CV as a factual document and write the form answers in her own words.</div>` : ""}
    <div class="filters wrap">
      <select id="tpl">${Object.entries(priv.templates).map(([k, v]) => `<option value="${k}" ${k === settings.template ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
      <select id="photo"><option value="left">Photo left</option><option value="right">Photo right</option><option value="off">No photo</option></select>
      <select id="pages"><option value="1">One page</option><option value="2">Two pages</option></select>
      <button class="f" id="reset">Rebuild from her facts</button></div>
    <div class="chips" style="gap:8px;margin:6px 0 10px">
      <button class="btn slim hot" id="cv-docx">${icon("download")}Word</button><button class="btn slim" id="cv-print">${icon("download")}PDF</button>
      ${files.includes("cv_pdf") ? `<button class="btn slim" id="cv-orig">${icon("doc")}Original PDF</button>` : ""}<button class="btn slim" id="save">${icon("check")}Save draft</button></div>
    <div class="lint" id="cv-lint"></div>
    ${toolbar(`<button data-move="-1">↑ Section</button><button data-move="1">↓ Section</button>`)}
    <div class="paper-wrap"><div class="paper" id="cv-paper" style="--accent:${tpl.accent};font-family:${tpl.font}">
      <div class="cvhead ${settings.photo === "right" ? "right" : ""}">${settings.photo !== "off" && photo ? `<img src="${photo}" alt="">` : ""}<div><h1>${esc(p.name)}</h1><div style="font-size:13px">Thessaloniki, Greece · ${esc(p.phone)} · ${esc(p.email)}<br>Dutch and British national · EU right to work</div></div></div>
      <div id="cv-ed"></div></div></div>
    ${cover ? `<h1 style="margin-top:22px">Cover letter</h1><div class="chips" style="gap:8px;margin:6px 0 10px"><button class="btn slim hot" id="cl-docx">${icon("download")}Word</button><button class="btn slim" id="cl-print">${icon("download")}PDF</button></div>
      <div class="lint" id="cl-lint"></div>${toolbar("")}<div class="paper-wrap"><div class="paper letter" id="cl-paper"><div id="cl-ed"></div></div></div>` : ""}
    <p class="muted small">Edits are saved on this phone. ${saved.at ? "Last saved " + new Date(saved.at).toLocaleString() + "." : ""}</p></div>`;
  root.querySelector("#photo").value = settings.photo;
  root.querySelector("#pages").value = String(settings.pages);
  let cvEd, clEd;
  const check = () => {
    const a = lint(cvEd.getText(), "cv");
    root.querySelector("#cv-lint").innerHTML = a.length ? a.map(x => `<div class="crit">✕ ${esc(x)}</div>`).join("") : `<div class="okmsg small">✓ Every line matches her real CVs.</div>`;
    if (clEd) { const b = lint(clEd.getText(), "cover"); root.querySelector("#cl-lint").innerHTML = b.length ? b.map(x => `<div class="crit">✕ ${esc(x)}</div>`).join("") : `<div class="okmsg small">✓ No factual problems.</div>`; return a.length + b.length; }
    return a.length;
  };
  cvEd = editor(root.querySelector("#cv-ed"), saved.cv && !frozen ? saved.cv : cvBody(model), () => { check(); fitPaper(root); });
  if (cover) clEd = editor(root.querySelector("#cl-ed"), saved.cover && !frozen ? saved.cover : coverBody(cover, id === "base" ? "" : title, company), () => { check(); fitPaper(root); });
  const bars = root.querySelectorAll(".toolbar");
  bindToolbar(bars[0], () => cvEd);
  if (clEd) bindToolbar(bars[1], () => clEd);
  bars[0].querySelectorAll("[data-move]").forEach(b => b.onclick = () => moveSection(cvEd, Number(b.dataset.move)));
  check();
  fitPaper(root);
  window.addEventListener("resize", () => fitPaper(root), { once: true });
  const persist = () => storeDraft(id, { cv: cvEd.getHTML(), cover: clEd?.getHTML(), template: root.querySelector("#tpl").value, photo: root.querySelector("#photo").value, pages: Number(root.querySelector("#pages").value) });
  root.querySelector("#save").onclick = () => { persist(); toast("Draft saved on this phone"); };
  for (const sel of ["#tpl", "#photo", "#pages"]) root.querySelector(sel).onchange = () => { persist(); open(root, id); };
  root.querySelector("#reset").onclick = () => { if (confirm("Throw away edits and rebuild from her real CV facts?")) { localStorage.removeItem(draftKey(id)); open(root, id); } };
  const stem = (p.name || "CV").replace(/\W+/g, "_"), tag = (company || "").replace(/\W+/g, "_");
  const current = () => ({ template: root.querySelector("#tpl").value, photo: root.querySelector("#photo").value });
  root.querySelector("#cv-docx").onclick = () => { if (check()) return toast("Fix the red lines first."); exportDocx("cv", cvEd, current(), `${stem}_CV${tag ? "_" + tag : ""}.docx`); };
  const print = sel => { const paper = root.querySelector(sel); const t = paper.style.transform; paper.style.transform = ""; paper.classList.add("print-target"); window.print(); setTimeout(() => { paper.classList.remove("print-target"); paper.style.transform = t; }, 600); };
  root.querySelector("#cv-print").onclick = () => print("#cv-paper");
  root.querySelector("#cv-orig")?.addEventListener("click", async () => download(await fileBlob(`${id}-cv_pdf`, "application/pdf"), `${stem}_CV_${tag}.pdf`));
  root.querySelector("#cl-docx")?.addEventListener("click", () => exportDocx("cover", clEd, current(), `${stem}_Cover_letter${tag ? "_" + tag : ""}.docx`));
  root.querySelector("#cl-print")?.addEventListener("click", () => print("#cl-paper"));
}
