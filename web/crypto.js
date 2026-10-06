const enc = new TextEncoder();

async function keyFor(pass, salt) {
  const material = await crypto.subtle.importKey("raw", enc.encode(pass), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey({ name: "PBKDF2", salt, iterations: 120000, hash: "SHA-256" }, material, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
}

export async function decryptBytes(pass, b64) {
  const raw = Uint8Array.from(atob(b64.trim()), c => c.charCodeAt(0));
  const key = await keyFor(pass, raw.slice(0, 16));
  return new Uint8Array(await crypto.subtle.decrypt({ name: "AES-GCM", iv: raw.slice(16, 28) }, key, raw.slice(28)));
}

export async function decryptJson(pass, b64) {
  return JSON.parse(new TextDecoder().decode(await decryptBytes(pass, b64)));
}
