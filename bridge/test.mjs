// Regression test: the bridge fills and uploads but never submits, even when a submit button is labelled "Apply".
import { execFileSync } from "node:child_process";
import { writeFileSync, readFileSync, mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

const here = fileURLToPath(new URL(".", import.meta.url));
const dir = mkdtempSync(join(tmpdir(), "bridge-test-"));
writeFileSync(join(dir, "cv.pdf"), "%PDF-1.4 test");
const pack = {
  apply_url: "file://" + join(here, "fixture.html"), ai_policy: "prohibited", allow_cover_text: false, cover_text: "",
  files: { cv: join(dir, "cv.pdf"), cover: join(dir, "cv.pdf") },
  fields: { first_name: "Test", last_name: "Person", full_name: "Test Person", email: "test@example.com", phone: "+30 000", city: "Thessaloniki", linkedin: "" },
};
writeFileSync(join(dir, "package.json"), JSON.stringify(pack));
execFileSync("node", [join(here, "bridge.mjs"), join(dir, "package.json")], { env: { ...process.env, BRIDGE_HEADLESS: "1" }, stdio: "inherit" });
const report = JSON.parse(readFileSync(join(dir, "report.json"), "utf8"));
const fail = message => { console.error("FAIL:", message); process.exit(1); };
if (report.page_submitted) fail("the fixture form was submitted");
if (!report.filled.some(f => f.includes("first_name"))) fail("first name not filled");
if (!report.uploaded.some(u => u.startsWith("CV"))) fail("CV not uploaded");
if (report.uploaded.some(u => u.startsWith("Cover"))) fail("cover letter uploaded despite AI ban");
if (!report.skipped_sensitive.some(s => /gender/i.test(s))) fail("gender field was not left alone");
console.log("PASS: filled", report.filled.length, "fields, uploaded CV only, did not submit");
