// Job radar sync. Separate from the app: touches only the job_radar schema.
// Auth: x-radar-token header, compared by SHA-256 against job_radar.config.
import postgres from "https://deno.land/x/postgresjs@v3.4.5/mod.js";

const sql = postgres(Deno.env.get("SUPABASE_DB_URL")!, { prepare: false, max: 2, idle_timeout: 20 });
const ORIGINS = ["https://studio-kenotomia.com", "http://127.0.0.1:8787", "http://localhost:8787"];
const DECISIONS = new Set(["like", "pass", "applied", "interview", "offer", "rejected", "withdrawn", "superlike"]);

function headers(origin: string) {
  return {
    "Access-Control-Allow-Origin": ORIGINS.includes(origin) ? origin : ORIGINS[0],
    "Access-Control-Allow-Headers": "content-type, x-radar-token",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
    "Content-Type": "application/json",
  };
}

async function sha256(text: string) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, "0")).join("");
}

Deno.serve(async (req: Request) => {
  const origin = req.headers.get("origin") ?? "";
  const h = headers(origin);
  if (req.method === "OPTIONS") return new Response(null, { headers: h });
  const reply = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: h });
  const token = req.headers.get("x-radar-token") ?? "";
  if (token.length < 20) return reply(401, { error: "missing token" });
  const [config] = await sql`select token_hash from job_radar.config where id = 1`;
  if (!config || config.token_hash !== await sha256(token)) return reply(401, { error: "bad token" });

  if (req.method === "GET") {
    const swipes = await sql`select job_id, decision, at, device from job_radar.swipes order by at desc`;
    const facts = await sql`select key, value, at from job_radar.facts`;
    const events = await sql`select kind, job_id, payload, at from job_radar.events where kind in ('feedback', 'import', 'prepare') and at > now() - interval '30 days' order by at desc limit 500`;
    return reply(200, { swipes, facts, events, now: new Date().toISOString() });
  }

  let body: Record<string, unknown> = {};
  try { body = await req.json(); } catch { return reply(400, { error: "bad json" }); }
  const action = String(body.action ?? "");
  const jobId = String(body.job_id ?? "").slice(0, 64);
  const device = String(body.device ?? "").slice(0, 40);

  if (action === "swipe") {
    const decision = String(body.decision ?? "");
    if (!jobId || !DECISIONS.has(decision)) return reply(400, { error: "bad swipe" });
    const at = body.at ? new Date(String(body.at)) : new Date();
    const snapshot = body.snapshot && typeof body.snapshot === "object" ? body.snapshot : null;
    await sql`insert into job_radar.swipes (job_id, decision, at, device, snapshot) values (${jobId}, ${decision}, ${at}, ${device}, ${snapshot ? sql.json(snapshot) : null})
      on conflict (job_id) do update set decision = excluded.decision, at = excluded.at, device = excluded.device, snapshot = coalesce(excluded.snapshot, job_radar.swipes.snapshot)
      where job_radar.swipes.at <= excluded.at`;
    await sql`insert into job_radar.events (kind, job_id, payload) values ('swipe', ${jobId}, ${sql.json({ decision, device })})`;
    return reply(200, { ok: true });
  }
  if (action === "undo") {
    if (!jobId) return reply(400, { error: "bad undo" });
    await sql`delete from job_radar.swipes where job_id = ${jobId}`;
    await sql`insert into job_radar.events (kind, job_id, payload) values ('undo', ${jobId}, ${sql.json({ device })})`;
    return reply(200, { ok: true });
  }
  if (action === "facts") {
    const key = String(body.key ?? "").slice(0, 40), value = String(body.value ?? "").slice(0, 80);
    if (!/^[a-z0-9_]+$/.test(key)) return reply(400, { error: "bad key" });
    await sql`insert into job_radar.facts (key, value) values (${key}, ${value}) on conflict (key) do update set value = excluded.value, at = now()`;
    return reply(200, { ok: true });
  }
  if (["feedback", "import", "prepare"].includes(action)) {
    const payload = { reason: String(body.reason ?? "").slice(0, 40), url: String(body.url ?? "").slice(0, 500), device };
    await sql`insert into job_radar.events (kind, job_id, payload) values (${action}, ${jobId || null}, ${sql.json(payload)})`;
    return reply(200, { ok: true });
  }
  return reply(400, { error: "unknown action" });
});
