import { Editor, StarterKit, Underline, TextAlign, TextStyle, Color, Link, docx } from "./vendor/editor.js";
import { esc, command, fileBlob, photoUrl, state as appState, LOCAL, ago, tierLabel, money, toast } from "./app.js";

const $ = s => document.querySelector(s);
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
  [/atlas\.ti/i, "ATLAS.ti is not confirmed on the CVs in this workspace."],
  [/\b\d{2,}\s*(%|percent|cases|clients|applications|candidates|files)\b/i, "An unsupported number or metric appears."],
];

export function lint(text, kind = "cv") {
  const issues = [];
  const low = text.toLowerCase();
  for (const role of appState.data.profile.experience || []) {
    const employer = role.employer.toLowerCase(), title = role.title.toLowerCase();
    if ((kind === "cv" || /sales/.test(title)) && low.includes(employer) && !low.includes(title)) issues.push(`${role.employer} appears without the real title ${role.title}.`);
    if (new RegExp(`(operations|account|office) (manager|coordinator|lead) (at|with) ${employer.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`).test(low)) issues.push(`The ${role.employer} title was altered.`);
  }
  for (const [pattern, message] of FORBIDDEN) {
    const hit = low.match(pattern);
    if (hit && !new RegExp("(no|not|without)[^.]{0,40}" + hit[0].replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).test(low)) issues.push(message);
  }
  return [...new Set(issues)];
}

function cvBodyHTML(model) {
  const parts = [];
  for (const section of model.sections) {
    parts.push(`<h2>${esc(section.title)}</h2>`);
    if (section.type === "summary") parts.push(`<p>${esc(section.text)}</p>`);
    else if (section.type === "experience") {
      for (const e of section.entries) {
        parts.push(`<h3>${esc(e.title)} — ${esc(e.employer)}</h3><p><em>${esc(e.note ? e.note + " · " : "")}${esc(e.place)} · ${esc(e.dates)}</em></p>`);
        parts.push(`<ul>${e.bullets.map(b => `<li><p>${esc(b.text)}</p></li>`).join("")}</ul>`);
      }
    } else if (section.type === "education") {
      for (const e of section.entries) {
        parts.push(`<h3>${esc(e.credential)}</h3><p><em>${esc(e.school)}${e.place ? " · " + esc(e.place) : ""}${e.dates ? " · " + esc(e.dates) : ""}</em></p>`);
        if (e.lines.length) parts.push(`<ul>${e.lines.map(l => `<li><p>${esc(l)}</p></li>`).join("")}</ul>`);
      }
    } else parts.push(`<p>${section.items.map(i => esc(i.label)).join(" · ")}</p>`);
  }
  return parts.join("");
}

function coverHTML(model, job) {
  return `<p>${esc(model.name)}<br>${esc(model.contact)}</p><p>Re: ${esc(job.title)}, ${esc(job.company)}</p><p>${esc(model.greeting)}</p>` +
    model.paragraphs.map(p => `<p>${esc(p.text)}</p>`).join("") + `<p>${esc(model.signoff)}<br>${esc(model.name)}</p>`;
}

function draftKey(id) { return `mj-draft-${id}`; }
function loadDraft(id) { try { return JSON.parse(localStorage.getItem(draftKey(id)) || "null"); } catch { return null; } }
function storeDraft(id, draft) { localStorage.setItem(draftKey(id), JSON.stringify({ ...draft, savedAt: new Date().toISOString() })); }

function makeEditor(element, html, onUpdate) {
  return new Editor({
    element,
    extensions: [StarterKit, Underline, TextStyle, Color, Link.configure({ openOnClick: false }), TextAlign.configure({ types: ["heading", "paragraph"] })],
    content: html,
    onUpdate: ({ editor }) => onUpdate(editor),
  });
}

function toolbar(getEditor, extra = "") {
  return `<div class="toolbar">
    <button data-cmd="undo" title="Undo">↶</button><button data-cmd="redo" title="Redo">↷</button>
    <button data-cmd="bold"><b>B</b></button><button data-cmd="italic"><i>I</i></button><button data-cmd="underline"><u>U</u></button>
    <select data-cmd="block"><option value="p">Text</option><option value="h2">Section</option><option value="h3">Entry</option></select>
    <button data-cmd="bullet">• List</button>
    <button data-cmd="left">⟸</button><button data-cmd="center">≡</button><button data-cmd="right">⟹</button>
    <input type="color" data-cmd="color" value="#1b1b1b" title="Text colour">
    <button data-cmd="link">Link</button>
    ${extra}
  </div>`;
}

function bindToolbar(root, getEditor) {
  root.querySelectorAll("[data-cmd]").forEach(el => {
    const run = () => {
      const editor = getEditor();
      if (!editor) return;
      const chain = editor.chain().focus();
      const cmd = el.dataset.cmd;
      if (cmd === "undo") chain.undo().run();
      else if (cmd === "redo") chain.redo().run();
      else if (cmd === "bold") chain.toggleBold().run();
      else if (cmd === "italic") chain.toggleItalic().run();
      else if (cmd === "underline") chain.toggleUnderline().run();
      else if (cmd === "bullet") chain.toggleBulletList().run();
      else if (["left", "center", "right"].includes(cmd)) chain.setTextAlign(cmd).run();
      else if (cmd === "color") chain.setColor(el.value).run();
      else if (cmd === "block") {
        if (el.value === "p") chain.setParagraph().run();
        else chain.setHeading({ level: el.value === "h2" ? 2 : 3 }).run();
      } else if (cmd === "link") {
        const url = prompt("Link address");
        if (url) chain.setLink({ href: url }).run(); else chain.unsetLink().run();
      }
    };
    if (el.tagName === "SELECT" || el.type === "color") el.onchange = run; else el.onclick = run;
  });
}

function moveSection(editor, direction) {
  const json = editor.getJSON();
  const nodes = json.content || [];
  const { from } = editor.state.selection;
  let pos = 0, current = -1;
  const starts = [];
  nodes.forEach((node, index) => { if (node.type === "heading" && node.attrs?.level === 2) starts.push(index); });
  editor.state.doc.forEach((node, offset, index) => { if (offset <= from) current = index; });
  const sectionIndex = starts.filter(s => s <= current).length - 1;
  if (sectionIndex < 0) return toast("Put the cursor inside a section first.");
  const ranges = starts.map((s, i) => [s, (starts[i + 1] ?? nodes.length)]);
  const target = sectionIndex + direction;
  if (target < 0 || target >= ranges.length) return;
  const blocks = ranges.map(([a, b]) => nodes.slice(a, b));
  [blocks[sectionIndex], blocks[target]] = [blocks[target], blocks[sectionIndex]];
  const head = nodes.slice(0, starts[0]);
  editor.commands.setContent({ type: "doc", content: [...head, ...blocks.flat()] }, true);
}

function runsFrom(node, base = {}) {
  const out = [];
  for (const child of node.content || []) {
    if (child.type === "text") {
      const marks = Object.fromEntries((child.marks || []).map(m => [m.type, m.attrs || true]));
      const link = marks.link?.href;
      const run = new docx.TextRun({ text: child.text, bold: !!marks.bold || base.bold, italics: !!marks.italic, underline: marks.underline ? {} : undefined, color: marks.textStyle?.color?.replace("#", "") || base.color, size: base.size });
      out.push(link ? new docx.ExternalHyperlink({ link, children: [new docx.TextRun({ text: child.text, style: "Hyperlink" })] }) : run);
    } else if (child.type === "hardBreak") out.push(new docx.TextRun({ break: 1 }));
  }
  return out;
}

const ALIGN = { left: docx.AlignmentType.LEFT, center: docx.AlignmentType.CENTER, right: docx.AlignmentType.RIGHT };

function docxBlocks(json, accent) {
  const blocks = [];
  for (const node of json.content || []) {
    const align = ALIGN[node.attrs?.textAlign];
    if (node.type === "heading") {
      const level2 = node.attrs.level === 2;
      blocks.push(new docx.Paragraph({ alignment: align, spacing: { before: level2 ? 200 : 100, after: 40 }, border: level2 ? { bottom: { color: "CCCCCC", style: docx.BorderStyle.SINGLE, size: 4, space: 1 } } : undefined,
        children: runsFrom(node, { bold: true, color: level2 ? accent : undefined, size: level2 ? 21 : 22 }) }));
    } else if (node.type === "paragraph") {
      blocks.push(new docx.Paragraph({ alignment: align, spacing: { after: 60 }, children: runsFrom(node, { size: 21 }) }));
    } else if (node.type === "bulletList" || node.type === "orderedList") {
      for (const item of node.content || []) for (const para of item.content || []) blocks.push(new docx.Paragraph({ bullet: { level: 0 }, spacing: { after: 20 }, children: runsFrom(para, { size: 21 }) }));
    }
  }
  return blocks;
}

async function exportDocx(kind, editor, job, settings) {
  const accent = (TEMPLATES[settings.template] || TEMPLATES["professional-operations"]).accent.replace("#", "");
  const header = appState.data.profile;
  const children = [];
  if (kind === "cv") {
    const top = [new docx.Paragraph({ children: [new docx.TextRun({ text: header.name, bold: true, size: 40, color: accent })] }),
      new docx.Paragraph({ children: [new docx.TextRun({ text: `Thessaloniki, Greece · ${header.phone} · ${header.email}`, size: 20 })] }),
      new docx.Paragraph({ children: [new docx.TextRun({ text: "Dutch and British national · EU right to work", size: 20 })] })];
    if (settings.photo !== "off") {
      try {
        const photo = new Uint8Array(await (await fetch(await photoUrl())).arrayBuffer());
        const image = new docx.Paragraph({ children: [new docx.ImageRun({ type: "png", data: photo, transformation: { width: 96, height: 118 } })] });
        const cells = settings.photo === "right" ? [top, [image]] : [[image], top];
        children.push(new docx.Table({ width: { size: 100, type: docx.WidthType.PERCENTAGE }, borders: docx.TableBorders.NONE,
          rows: [new docx.TableRow({ children: cells.map((c, i) => new docx.TableCell({ children: c, width: { size: (settings.photo === "right" ? i === 1 : i === 0) ? 18 : 82, type: docx.WidthType.PERCENTAGE }, borders: docx.TableBorders.NONE })) })] }));
      } catch { children.push(...top); }
    } else children.push(...top);
  }
  children.push(...docxBlocks(editor.getJSON(), accent));
  const doc = new docx.Document({ styles: { default: { document: { run: { font: "Calibri", size: 21 } } } },
    sections: [{ properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 794, bottom: 794, left: 850, right: 850 } } }, children }] });
  const blob = await docx.Packer.toBlob(doc);
  download(blob, `${fileStem()}_${kind === "cv" ? "CV" : "Cover_letter"}_${(job.company || "").replace(/[^A-Za-z0-9]+/g, "_")}.docx`);
}

const fileStem = () => (appState.data.profile.name || "CV").replace(/[^A-Za-z0-9]+/g, "_");

function download(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

function printPaper(selector) {
  const paper = document.querySelector(selector);
  paper.classList.add("print-target");
  window.print();
  setTimeout(() => paper.classList.remove("print-target"), 500);
}

function matrixTable(job) {
  const rows = job.matrix || [];
  if (!rows.length) return `<p class="muted">The ad has too little structured text to map requirement by requirement.</p>`;
  const evidenceById = Object.fromEntries((appState.data.profile.evidence || []).map(e => [e.id, e]));
  return `<table class="matrix"><tr><th>What they ask</th><th>Match</th><th>Evidence</th></tr>${rows.map(r => `<tr>
    <td><b>${esc(r.label)}</b><br><span class="muted small">${esc(r.requirement)}</span><br><span class="small">${esc(r.importance)}</span></td>
    <td class="m-${esc(r.match)}">${esc(r.match)}</td>
    <td class="small">${(r.evidence_ids || []).map(id => evidenceById[id] ? `<div>${esc(evidenceById[id].fact)} <span class="muted">(${esc(evidenceById[id].source)})</span></div>` : "").join("")}${r.note ? `<div class="gap">${esc(r.note)}</div>` : ""}</td></tr>`).join("")}</table>`;
}

function components(job) {
  const c = job.components || {};
  const names = { role_fit: "Role fit", evidence_coverage: "Evidence coverage", location_fit: "Location", language_fit: "Language", seniority_fit: "Seniority", education_fit: "Education", domain_interest: "Domain", freshness: "Freshness", source_confidence: "Source confidence", application_effort: "Application effort", compensation_quality: "Pay (if published)" };
  return `<div class="grid2">${Object.entries(names).map(([k, label]) => c[k] == null ? "" : `<div><div class="row" style="justify-content:space-between"><span class="small">${label}</span><span class="small">${Math.round(c[k] * 100)}</span></div><div class="bar"><span style="width:${Math.round(c[k] * 100)}%"></span></div></div>`).join("")}</div>`;
}

export async function jobView(job, tab, ctx) {
  const tabs = [["opportunity", "Opportunity"], ["match", "Match"], ["docs", "Documents"], ["apply", "Apply"]];
  const pay = money(job.salary);
  const header = `<p><a href="#">← Back</a></p>
    <span class="tier ${esc(job.tier)}">${esc(tierLabel(job.tier))} · ${esc(job.score)}</span>
    <h2 style="margin-top:4px">${esc(job.title)}</h2>
    <div class="meta">${esc(job.company)} · ${esc(job.location || "")} · ${esc(job.work_mode || "")}</div>
    <div class="tabs">${tabs.map(([id, label]) => `<button class="${id === tab ? "on" : ""}" data-tab="${id}">${label}</button>`).join("")}</div>`;
  const view = $("#view");
  if (tab === "opportunity") {
    view.innerHTML = header + `
      ${(job.blockers || []).length ? `<div class="banner red">${job.blockers.map(esc).join("<br>")}</div>` : ""}
      ${job.ai_policy === "prohibited" ? `<div class="banner">This employer does not accept AI-written application answers. Documents here are factual drafts; she writes the form answers herself. <span class="muted small">(${esc(job.ai_policy_evidence || "")})</span></div>` : ""}
      <div class="card"><div class="grid2 small">
        <div><b>Remote from Greece:</b> ${esc(job.greece_remote)}<br><span class="muted">${esc(job.remote_evidence || "")}</span></div>
        <div><b>Posted:</b> ${esc(job.posted || "unknown")} · <b>first seen</b> ${esc(ago(job.first_seen))}</div>
        <div><b>Deadline:</b> ${esc(job.deadline || "none stated")}</div>
        <div><b>Pay:</b> ${esc(pay || "not published")}</div>
        <div><b>Source:</b> ${esc(job.source)} (${esc(job.source_type)}) ${job.secondary_sources?.length ? `· also seen on ${job.secondary_sources.length} other page(s)` : ""}</div>
        <div><b>Status:</b> ${esc(job.open_status || "open")} · ${esc(job.status || "none")}</div>
      </div></div>
      <h2>Why it ranks here</h2><ul class="tight">${(job.reasons || []).map(r => `<li>${esc(r)}</li>`).join("")}${(job.gaps || []).map(g => `<li class="gap">${esc(g)}</li>`).join("")}${(job.unknowns || []).map(u => `<li class="gap">${esc(u)}</li>`).join("")}</ul>
      ${(job.greek_gist || []).length ? `<h2>In English, the key Greek phrases say</h2><ul class="tight">${job.greek_gist.map(g => `<li>${esc(g)}</li>`).join("")}</ul>` : ""}
      ${(job.scam_signals || []).length ? `<div class="banner red">Possible scam signals: ${job.scam_signals.map(esc).join(", ")}. Verify the employer before sharing documents.</div>` : ""}
      ${(job.versions || []).length ? `<p class="muted small">This ad changed ${job.versions.length} time(s) since first seen.</p>` : ""}
      <h2>Original posting ${job.language === "el" ? "(Greek)" : ""}</h2><div class="desc">${esc(job.description || "No text captured. Open the original.")}</div>
      <div class="actions"><a class="btn primary" href="${esc(job.url)}" target="_blank" rel="noopener">Open the original listing</a></div>`;
  } else if (tab === "match") {
    view.innerHTML = header + `<h2>Requirements against her evidence</h2><p class="muted small">Strong means a real job or CV line supports it. Transferable means it comes from her degrees or a nearby skill. Absent means do not claim it.</p>${matrixTable(job)}<h2>Score components</h2>${components(job)}`;
  } else if (tab === "docs") {
    await docsTab(job, header);
  } else {
    applyTab(job, header);
  }
  view.querySelectorAll("[data-tab]").forEach(b => b.onclick = () => { location.hash = `job=${job.id}&tab=${b.dataset.tab}`; });
}

async function docsTab(job, header) {
  const view = $("#view");
  if (!job.cv_model) {
    view.innerHTML = header + `<p class="muted">Documents are generated for the jobs on the short list. Save this job and the next run prepares them.</p><button id="save-for-docs">Save and generate</button>`;
    $("#save-for-docs").onclick = () => command(`status ${job.id} saved`, { id: job.id, patch: { status: "saved" } });
    return;
  }
  const saved = loadDraft(job.id) || {};
  const settings = { template: saved.template || job.cv_model.template, photo: saved.photo || "left", pages: saved.pages || 1 };
  const model = settings.pages === 2 && job.cv_model_2 ? job.cv_model_2 : job.cv_model;
  const photo = await photoUrl();
  const tpl = TEMPLATES[settings.template] || TEMPLATES["professional-operations"];
  const prof = appState.data.profile;
  const tplOptions = Object.entries(appState.data.templates).map(([k, v]) => `<option value="${k}" ${k === settings.template ? "selected" : ""}>${esc(v)}</option>`).join("");
  const files = job.has_files || [];
  view.innerHTML = header + `
    ${job.frozen ? `<div class="banner">This is the frozen version sent with the application. Edits here do not change it.</div>` : ""}
    ${job.ai_policy === "prohibited" ? `<div class="banner">The employer bans AI-written answers. Use the CV as a factual document. Rewrite the cover letter in her own words before using it, or leave it out.</div>` : ""}
    <div class="row">
      <label class="small">Template <select id="tpl">${tplOptions}</select></label>
      <label class="small">Photo <select id="photo-pos"><option value="left">Left</option><option value="right">Right</option><option value="off">Off</option></select></label>
      <label class="small">Length <select id="pages"><option value="1">One page</option><option value="2">Two pages</option></select></label>
      <button id="regen" title="Discard edits and rebuild from her evidence">Rebuild from evidence</button>
    </div>
    <h2>CV</h2>
    ${toolbar(null, `<button data-move="-1">Section ↑</button><button data-move="1">Section ↓</button>`)}
    <div class="paper-wrap"><div class="paper" id="cv-paper" style="--accent:${tpl.accent};font-family:${tpl.font}">
      <div class="cvhead ${settings.photo === "right" ? "right" : ""}">${settings.photo !== "off" && photo ? `<img src="${photo}" alt="">` : ""}<div><h1>${esc(prof.name)}</h1><div class="small">Thessaloniki, Greece · ${esc(prof.phone)} · ${esc(prof.email)}<br>Dutch and British national · EU right to work</div></div></div>
      <div id="cv-editor"></div></div></div>
    <div class="lint" id="cv-lint"></div>
    <div class="actions"><button class="primary" id="cv-docx">Download Word</button><button id="cv-print">Download PDF (print)</button>${files.includes("cv_pdf") ? `<button id="cv-cloud-pdf">Original PDF</button>` : ""}${files.includes("cv_docx") ? `<button id="cv-cloud-docx">Original Word</button>` : ""}<button id="save-draft">Save draft</button><button id="mark-ready">Mark ready</button></div>
    <details class="trace"><summary>Why is each line allowed?</summary>${traceList(model)}</details>
    <h2>Cover letter</h2>
    ${toolbar(null)}
    <div class="paper-wrap"><div class="paper letter" id="cover-paper"><div id="cover-editor"></div></div></div>
    <div class="lint" id="cover-lint"></div>
    <div class="actions"><button class="primary" id="cover-docx">Download Word</button><button id="cover-print">Download PDF (print)</button>${files.includes("cover_pdf") ? `<button id="cover-cloud-pdf">Original PDF</button>` : ""}</div>
    <p class="muted small">Drafts save on this device. ${saved.savedAt ? "Last saved " + esc(ago(saved.savedAt)) + "." : ""}</p>`;
  $("#photo-pos").value = settings.photo;
  $("#pages").value = String(settings.pages);
  let cvEditor, coverEditor;
  const check = () => {
    const all = lint(cvEditor.getText());
    $("#cv-lint").innerHTML = all.length ? all.map(i => `<div class="crit">✕ ${esc(i)}</div>`).join("") : `<div class="ok">✓ No factual problems found.</div>`;
    const coverIssues = lint(coverEditor.getText(), "cover");
    $("#cover-lint").innerHTML = coverIssues.length ? coverIssues.map(i => `<div class="crit">✕ ${esc(i)}</div>`).join("") : `<div class="ok">✓ No factual problems found.</div>`;
    $("#mark-ready").disabled = all.length > 0 || coverIssues.length > 0;
    return all.length + coverIssues.length;
  };
  cvEditor = makeEditor($("#cv-editor"), saved.cv && !job.frozen ? saved.cv : cvBodyHTML(model), check);
  coverEditor = makeEditor($("#cover-editor"), saved.cover && !job.frozen ? saved.cover : coverHTML(job.cover_model, job), check);
  const bars = view.querySelectorAll(".toolbar");
  bindToolbar(bars[0], () => cvEditor);
  bindToolbar(bars[1], () => coverEditor);
  bars[0].querySelectorAll("[data-move]").forEach(b => b.onclick = () => moveSection(cvEditor, Number(b.dataset.move)));
  check();
  const persist = extra => storeDraft(job.id, { ...loadDraft(job.id), cv: cvEditor.getHTML(), cover: coverEditor.getHTML(), template: $("#tpl").value, photo: $("#photo-pos").value, pages: Number($("#pages").value), ...extra });
  $("#save-draft").onclick = () => { persist(); toast("Draft saved on this device."); };
  $("#mark-ready").onclick = () => { if (check()) return; persist({ ready: true }); command(`status ${job.id} prepared`, { id: job.id, patch: { status: "prepared" } }); };
  for (const id of ["tpl", "photo-pos", "pages"]) $("#" + id).onchange = () => { persist(); docsTab(job, header); };
  $("#regen").onclick = () => { if (confirm("Discard edits and rebuild both documents from her evidence?")) { localStorage.removeItem(`mj-draft-${job.id}`); docsTab(job, header); } };
  const current = () => ({ template: $("#tpl").value, photo: $("#photo-pos").value });
  $("#cv-docx").onclick = () => { if (check()) return toast("Fix the factual problems first."); exportDocx("cv", cvEditor, job, current()); };
  $("#cover-docx").onclick = () => exportDocx("cover", coverEditor, job, current());
  $("#cv-print").onclick = () => printPaper("#cv-paper");
  $("#cover-print").onclick = () => printPaper("#cover-paper");
  const cloud = (name, type, filename) => async () => download(await fileBlob(`${job.id}-${name}`, type), filename);
  if ($("#cv-cloud-pdf")) $("#cv-cloud-pdf").onclick = cloud("cv_pdf", "application/pdf", `${fileStem()}_CV.pdf`);
  if ($("#cv-cloud-docx")) $("#cv-cloud-docx").onclick = cloud("cv_docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", `${fileStem()}_CV.docx`);
  if ($("#cover-cloud-pdf")) $("#cover-cloud-pdf").onclick = cloud("cover_pdf", "application/pdf", `${fileStem()}_Cover_letter.pdf`);
}

function traceList(model) {
  const evidenceById = Object.fromEntries((appState.data.profile.evidence || []).map(e => [e.id, e]));
  const lines = [];
  for (const s of model.sections) {
    for (const e of s.entries || []) for (const b of e.bullets || []) lines.push([b.text, b.evidence]);
    for (const i of s.items || []) lines.push([i.label, i.evidence]);
  }
  return `<ul class="tight">${lines.map(([text, ids]) => `<li>${esc(text)}<br><span class="muted">${(ids || []).map(id => esc(evidenceById[id]?.source || id)).join("; ")}</span></li>`).join("")}</ul>`;
}

function applyTab(job, header) {
  const view = $("#view");
  const prohibited = job.ai_policy === "prohibited";
  const evidence = (appState.data.profile.evidence || []).filter(e => e.confirmed);
  const memory = evidence.filter(e => (e.parent || "").startsWith("exp_")).slice(0, 8);
  const checklist = ["Correct employer and role", "Correct CV version", "Correct cover letter, or none", "Name, email and phone checked", "Work authorisation answered: Dutch citizen, EU right to work", "Salary question reviewed", "Travel and availability reviewed", "AI policy checked", "Required custom questions written", "Attachments visible on the form", "Consent and privacy boxes reviewed", "Submit pressed by her, not by software"];
  const draft = loadDraft(job.id) || {};
  view.innerHTML = header + `
    <div class="banner">Nothing here submits an application. The Apply Bridge on the Mac fills ordinary fields and uploads the CV, then stops on the employer's page for review.</div>
    ${prohibited ? `<div class="card"><b>Questions she writes herself</b><p class="small">The employer requires her own words. Here are true things she may want to draw on:</p><ul class="tight">${memory.map(e => `<li>${esc(e.fact)}</li>`).join("")}</ul></div>` : ""}
    <div class="actions">
      <a class="btn primary" href="${esc(job.apply_url || job.url)}" target="_blank" rel="noopener">Open the employer's form</a>
      <button id="bridge">${LOCAL ? "Prepare with Apply Bridge" : "Queue for the Mac Apply Bridge"}</button>
    </div>
    <p class="muted small" id="bridge-msg">${LOCAL ? "" : "Queued items wait until the Mac dashboard is open. The phone cannot run the bridge."}</p>
    <h2>Review checklist</h2>
    ${checklist.map((c, i) => `<label class="row small"><input type="checkbox" data-check="${i}" ${draft.checks?.[i] ? "checked" : ""}> ${esc(c)}</label>`).join("")}
    <h2>Status</h2>
    <div class="actions">${["prepared", "submitted", "interview", "offer", "rejected", "withdrawn", "skipped"].map(s => `<button data-status="${s}">${s}</button>`).join("")}</div>
    <p class="muted small">Marking it submitted freezes the CV and cover letter that went with it.</p>
    <h2>Tell the ranking something</h2>
    <div class="chips">${[["more", "More like this"], ["less", "Less like this"], ["too_customer", "Too customer-facing"], ["too_sales", "Too sales-oriented"], ["too_senior", "Too senior"], ["greek_too_strong", "Greek too strong"], ["remote_bad", "Remote restriction bad"], ["great_company", "Great company"], ["great_work", "Great type of work"], ["pay_low", "Pay too low"]].map(([k, l]) => `<button class="chip" data-fb="${k}">${l}</button>`).join("")}</div>`;
  view.querySelectorAll("[data-check]").forEach(box => box.onchange = () => { const d = loadDraft(job.id) || {}; d.checks = d.checks || {}; d.checks[box.dataset.check] = box.checked; storeDraft(job.id, d); });
  view.querySelectorAll("[data-status]").forEach(b => b.onclick = () => {
    if (b.dataset.status === "submitted") storeDraft(job.id, { ...(loadDraft(job.id) || {}), frozenAt: new Date().toISOString() });
    command(`status ${job.id} ${b.dataset.status}`, { id: job.id, patch: { status: b.dataset.status } });
  });
  view.querySelectorAll("[data-fb]").forEach(b => b.onclick = () => command(`feedback ${job.id} ${b.dataset.fb}`));
  $("#bridge").onclick = async () => {
    if (!LOCAL) return command(`prepare ${job.id}`);
    $("#bridge-msg").textContent = "Opening the employer's page on this Mac…";
    const draftNow = loadDraft(job.id) || {};
    const response = await fetch(`api/bridge/prepare/${job.id}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ edited: !!draftNow.cv }) });
    const result = await response.json();
    $("#bridge-msg").textContent = result.message || "Done.";
  };
}

export async function speculative(item, data, ctx) {
  const view = $("#view");
  const job = { id: "radar-" + item.company.replace(/\W+/g, "-"), title: "Speculative application", company: item.company, cv_model: item.cv_model, cover_model: item.cover_model, has_files: [], tier: "radar", score: "—", location: "Thessaloniki", ai_policy: "unknown" };
  const header = `<p><a href="#radar">← Radar</a></p><span class="tier verify">No confirmed opening</span><h2>${esc(item.company)}</h2><p>${esc(item.why)}</p><p class="muted small">${esc(item.angle)} Nothing is sent automatically. Review, then send from her own email.</p>`;
  await docsTab(job, header);
}
