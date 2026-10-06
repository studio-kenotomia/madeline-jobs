// Opens an employer application form on this Mac, fills safe factual fields and uploads files.
// It never submits. There is no code path that presses a final submit button.
import { chromium } from "playwright";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

const packagePath = process.argv[2];
if (!packagePath) { console.error("usage: node bridge.mjs <package.json>"); process.exit(2); }
const pack = JSON.parse(readFileSync(packagePath, "utf8"));
const reportPath = packagePath.replace(/package\.json$/, "report.json");
const profileDir = join(homedir(), "madeline-jobs", "playwright-profile");

const SENSITIVE = /gender|\bsex\b|pronoun|\brace\b|ethnic|veteran|disabilit|criminal|convict|religion|sexual|orientation|salary|compensation|expected pay|visa sponsor|sponsorship|relocat|notice period|start date|willing to travel|\btravel\b|date of birth|\bage\b|marital|health|medical|hispanic|latino/i;
const OPEN_APPLY = /^(apply|apply now|apply for this job|apply to this job|apply for this position|i'?m interested|start (your )?application|υποβολή βιογραφικού)$/i;
const NEVER_CLICK = /submit|send|finish|complete|confirm|review and|υποβολ|αποστολ|ολοκλήρωσ|επιβεβαίωσ/i;
const FIELDS = [
  [/first\s*name|given name|όνομα(?!τεπώνυμο)/i, "first_name"],
  [/last\s*name|surname|family name|επώνυμο/i, "last_name"],
  [/^\s*(full\s*)?name\s*\*?$|full name|ονοματεπώνυμο/i, "full_name"],
  [/e-?mail/i, "email"],
  [/phone|mobile|τηλέφωνο|κινητό/i, "phone"],
  [/^(city|location|current location|where are you based|πόλη)/i, "city"],
  [/linkedin/i, "linkedin"],
];

const report = { url: pack.apply_url, started: new Date().toISOString(), filled: [], uploaded: [], skipped_sensitive: [], left_for_review: [], notes: [], submitted: false };
const save = () => writeFileSync(reportPath, JSON.stringify(report, null, 2));

async function labelFor(input) {
  return input.evaluate(el => {
    const byFor = el.id ? document.querySelector(`label[for="${CSS.escape(el.id)}"]`) : null;
    const wrap = el.closest("label");
    const aria = el.getAttribute("aria-label") || "";
    const described = el.getAttribute("aria-labelledby") ? (document.getElementById(el.getAttribute("aria-labelledby"))?.textContent || "") : "";
    const near = el.closest("div,fieldset,li")?.querySelector("label,legend,.label,.field-label")?.textContent || "";
    return [byFor?.textContent, wrap?.textContent, aria, described, el.placeholder, el.name, near].filter(Boolean).join(" | ").replace(/\s+/g, " ").trim().slice(0, 200);
  });
}

async function safeToClick(el) {
  return el.evaluate((node, never) => {
    const text = [node.textContent, node.getAttribute("aria-label"), node.getAttribute("value"), node.getAttribute("title")].filter(Boolean).join(" ");
    if (new RegExp(never, "i").test(text)) return false;
    if ((node.getAttribute("type") || "").toLowerCase() === "submit") return false;
    const form = node.closest("form");
    if (form && form.querySelector("input[type=file], input[type=email], textarea")) return false;
    return true;
  }, NEVER_CLICK.source);
}

async function openForm(page) {
  const formAlreadyHere = await page.locator("input[type=file], input[type=email]").count();
  if (formAlreadyHere) { report.notes.push("The application form is already on the page."); return; }
  for (const role of ["link", "button"]) {
    const candidates = page.getByRole(role, { name: OPEN_APPLY });
    const count = await candidates.count();
    for (let i = 0; i < count; i++) {
      const el = candidates.nth(i);
      if (!(await el.isVisible().catch(() => false))) continue;
      if (!(await safeToClick(el))) { report.notes.push("Skipped a button that could submit."); continue; }
      const label = (await el.textContent() || "").trim();
      await el.click();
      report.notes.push(`Opened the form with "${label}".`);
      await page.waitForTimeout(2500);
      return;
    }
  }
}

async function fillFields(page) {
  const inputs = page.locator("input:not([type=hidden]):not([type=file]):not([type=submit]):not([type=button]):not([type=checkbox]):not([type=radio]), textarea, select");
  const count = await inputs.count();
  for (let i = 0; i < count; i++) {
    const input = inputs.nth(i);
    if (!(await input.isVisible().catch(() => false))) continue;
    const label = await labelFor(input);
    const tag = await input.evaluate(el => el.tagName.toLowerCase());
    const required = await input.evaluate(el => el.required || el.getAttribute("aria-required") === "true");
    if (SENSITIVE.test(label)) { report.skipped_sensitive.push(label); continue; }
    if (tag === "textarea") {
      if (/cover letter/i.test(label) && pack.allow_cover_text && pack.cover_text) {
        await input.fill(pack.cover_text);
        report.filled.push(`${label} (cover letter text)`);
      } else if (required) report.left_for_review.push(label);
      continue;
    }
    if (tag === "select") { if (required) report.left_for_review.push(label); continue; }
    const match = FIELDS.find(([pattern]) => pattern.test(label));
    const current = await input.inputValue().catch(() => "");
    if (match && pack.fields[match[1]] && !current) {
      await input.fill(pack.fields[match[1]]);
      report.filled.push(`${label} → ${match[1]}`);
    } else if (required && !current) {
      report.left_for_review.push(label);
    }
  }
}

async function uploadFiles(page) {
  const files = page.locator("input[type=file]");
  const count = await files.count();
  let usedCv = false;
  for (let i = 0; i < count; i++) {
    const input = files.nth(i);
    const label = (await labelFor(input)).toLowerCase();
    const isCover = /cover/.test(label);
    if (isCover) {
      if (pack.ai_policy === "prohibited" || !pack.files.cover) { report.notes.push("Cover letter upload left empty on purpose."); continue; }
      await input.setInputFiles(pack.files.cover);
      report.uploaded.push(`Cover letter → ${label || "file field"}`);
    } else if (!usedCv && pack.files.cv) {
      await input.setInputFiles(pack.files.cv);
      report.uploaded.push(`CV → ${label || "file field"}`);
      usedCv = true;
    }
  }
  if (!count) report.notes.push("No file upload field found yet. The form may need an account or a different step.");
}

async function banner(page) {
  await page.evaluate(() => {
    const el = document.createElement("div");
    el.textContent = "APPLICATION PREPARED — NOT SUBMITTED. Check every field, then press the employer's own submit button yourself.";
    el.style.cssText = "position:fixed;top:0;left:0;right:0;z-index:2147483647;background:#1c1915;color:#fff;font:600 15px -apple-system,sans-serif;padding:10px 14px;text-align:center";
    document.body.prepend(el);
  });
}

const context = await chromium.launchPersistentContext(profileDir, { headless: !!process.env.BRIDGE_HEADLESS, viewport: { width: 1280, height: 900 } });
const page = context.pages()[0] || await context.newPage();
await page.addInitScript(() => {
  const block = event => {
    if (window.__bridgeFilling) { event.preventDefault(); event.stopImmediatePropagation(); }
  };
  window.addEventListener("submit", block, true);
});
try {
  await page.goto(pack.apply_url, { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.waitForTimeout(2500);
  const html = (await page.content()).toLowerCase();
  if (/captcha|recaptcha|hcaptcha|cf-challenge|verify you are human/.test(html)) report.notes.push("A CAPTCHA or bot check is on the page. Solve it yourself; the bridge does not.");
  if (/sign in|log in|create (an )?account|σύνδεση/.test(html) && !/input[^>]+type="file"/.test(html)) report.notes.push("This employer may need an account. Log in in this window once; the session is kept on this Mac only.");
  await page.evaluate(() => { window.__bridgeFilling = true; });
  await openForm(page);
  await page.evaluate(() => { window.__bridgeFilling = true; }).catch(() => {});
  await fillFields(page);
  await uploadFiles(page);
  await page.evaluate(() => { window.__bridgeFilling = false; }).catch(() => {});
  await banner(page);
  if (process.env.BRIDGE_SCREENSHOT) await page.screenshot({ path: process.env.BRIDGE_SCREENSHOT, fullPage: false });
} catch (error) {
  report.notes.push(`Stopped: ${error.message.split("\n")[0]}`);
}
report.finished = new Date().toISOString();
save();
console.log(JSON.stringify(report));
if (process.env.BRIDGE_HEADLESS) await context.close();
