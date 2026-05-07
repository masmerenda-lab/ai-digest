/**
 * Cloudflare Worker – AI Digest Web Push
 *
 * Endpoint:
 *   POST /subscribe  – salva una PushSubscription nel KV
 *   POST /notify     – invia Web Push a tutti gli iscritti (auth richiesta)
 *
 * Secrets da settare con `wrangler secret put`:
 *   VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_SUBJECT, NOTIFY_SECRET
 */

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
};

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS });
    }

    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/subscribe') {
      return handleSubscribe(request, env);
    }
    if (request.method === 'POST' && url.pathname === '/unsubscribe') {
      return handleUnsubscribe(request, env);
    }
    if (request.method === 'GET' && url.pathname === '/subscribers/count') {
      return handleCount(env);
    }
    if (request.method === 'POST' && url.pathname === '/notify') {
      return handleNotify(request, env);
    }

    return new Response('Not found', { status: 404 });
  },
};

// ---------------------------------------------------------------------------
// POST /subscribe
// ---------------------------------------------------------------------------
async function handleSubscribe(request, env) {
  let sub;
  try {
    sub = await request.json();
  } catch {
    return json({ error: 'Invalid JSON' }, 400);
  }

  if (!sub?.endpoint) {
    return json({ error: 'Missing endpoint' }, 400);
  }

  const key = crypto.randomUUID();
  await env.SUBSCRIPTIONS.put(key, JSON.stringify(sub));
  return json({ ok: true, id: key }, 201);
}

// ---------------------------------------------------------------------------
// POST /unsubscribe
// ---------------------------------------------------------------------------
async function handleUnsubscribe(request, env) {
  let body;
  try { body = await request.json(); } catch { return json({ error: 'Invalid JSON' }, 400); }
  if (!body?.id) return json({ error: 'Missing id' }, 400);
  await env.SUBSCRIPTIONS.delete(body.id);
  return json({ ok: true });
}

// ---------------------------------------------------------------------------
// GET /subscribers/count
// ---------------------------------------------------------------------------
async function handleCount(env) {
  const keys = await listAllKeys(env.SUBSCRIPTIONS);
  return json({ count: keys.length });
}

// ---------------------------------------------------------------------------
// POST /notify
// ---------------------------------------------------------------------------
async function handleNotify(request, env) {
  const auth = request.headers.get('Authorization') ?? '';
  if (auth !== `Bearer ${env.NOTIFY_SECRET}`) {
    return json({ error: 'Unauthorized' }, 401);
  }

  let payload;
  try {
    payload = await request.json();
  } catch {
    return json({ error: 'Invalid JSON' }, 400);
  }

  const { title = 'Digest AI', body = 'Nuovo digest disponibile!', url = '/' } = payload;
  const message = JSON.stringify({ title, body, url });

  const keys = await listAllKeys(env.SUBSCRIPTIONS);

  let sent = 0, failed = 0, removed = 0;

  await Promise.all(keys.map(async (kvKey) => {
    const raw = await env.SUBSCRIPTIONS.get(kvKey);
    if (!raw) return;

    let sub;
    try { sub = JSON.parse(raw); } catch { return; }

    const result = await sendWebPush(sub, message, env);

    if (result === 'ok') {
      sent++;
    } else if (result === 'gone') {
      await env.SUBSCRIPTIONS.delete(kvKey);
      removed++;
    } else {
      failed++;
    }
  }));

  return json({ sent, failed, removed });
}

// ---------------------------------------------------------------------------
// Web Push (VAPID)
// ---------------------------------------------------------------------------
async function sendWebPush(subscription, message, env) {
  try {
    const endpoint = subscription.endpoint;
    const audience = new URL(endpoint).origin;
    const vapidJwt = await buildVapidJwt(audience, env);

    // Cifratura payload: usiamo il Content-Encoding: aes128gcm
    const { ciphertext, salt, serverPublicKey } = await encryptPayload(
      message,
      subscription.keys.p256dh,
      subscription.keys.auth
    );

    const headers = {
      'Authorization': `vapid t=${vapidJwt.token},k=${env.VAPID_PUBLIC_KEY}`,
      'Content-Type': 'application/octet-stream',
      'Content-Encoding': 'aes128gcm',
      'TTL': '86400',
    };

    const body = buildBody(salt, serverPublicKey, ciphertext);

    const resp = await fetch(endpoint, { method: 'POST', headers, body });

    if (resp.status === 201 || resp.status === 200) return 'ok';
    if (resp.status === 410 || resp.status === 404) return 'gone';
    console.error(`Push failed ${resp.status} for ${endpoint}`);
    return 'error';
  } catch (err) {
    console.error('sendWebPush error:', err);
    return 'error';
  }
}

// ---------------------------------------------------------------------------
// VAPID JWT
// ---------------------------------------------------------------------------
async function buildVapidJwt(audience, env) {
  const now = Math.floor(Date.now() / 1000);
  const header = b64url(JSON.stringify({ typ: 'JWT', alg: 'ES256' }));
  const claims = b64url(JSON.stringify({ aud: audience, exp: now + 43200, sub: env.VAPID_SUBJECT }));
  const unsigned = `${header}.${claims}`;

  const privateKey = await importVapidPrivateKey(env.VAPID_PRIVATE_KEY, env.VAPID_PUBLIC_KEY);
  const sig = await crypto.subtle.sign(
    { name: 'ECDSA', hash: 'SHA-256' },
    privateKey,
    new TextEncoder().encode(unsigned)
  );
  const token = `${unsigned}.${b64urlBytes(new Uint8Array(sig))}`;
  return { token };
}

async function importVapidPrivateKey(privateKeyB64, publicKeyB64) {
  // Web Crypto non supporta 'raw' per ECDSA — serve JWK con x, y dalla chiave pubblica
  const pubBytes = base64urlDecode(publicKeyB64);
  // P-256 uncompressed: 0x04 | x (32 byte) | y (32 byte)
  const jwk = {
    kty: 'EC',
    crv: 'P-256',
    d: privateKeyB64,
    x: b64urlBytes(pubBytes.slice(1, 33)),
    y: b64urlBytes(pubBytes.slice(33, 65)),
  };
  return crypto.subtle.importKey('jwk', jwk, { name: 'ECDSA', namedCurve: 'P-256' }, false, ['sign']);
}

// ---------------------------------------------------------------------------
// AES128GCM payload encryption (RFC 8291)
// ---------------------------------------------------------------------------
async function encryptPayload(plaintext, p256dhB64, authB64) {
  const receiverPublicKey = base64urlDecode(p256dhB64);
  const authSecret = base64urlDecode(authB64);

  // Genera coppia di chiavi effimere
  const serverKeyPair = await crypto.subtle.generateKey(
    { name: 'ECDH', namedCurve: 'P-256' },
    true,
    ['deriveBits']
  );

  const serverPublicKeyRaw = new Uint8Array(
    await crypto.subtle.exportKey('raw', serverKeyPair.publicKey)
  );

  // Importa chiave pubblica del client
  const clientPublicKey = await crypto.subtle.importKey(
    'raw',
    receiverPublicKey,
    { name: 'ECDH', namedCurve: 'P-256' },
    false,
    []
  );

  // ECDH shared secret
  const sharedBits = await crypto.subtle.deriveBits(
    { name: 'ECDH', public: clientPublicKey },
    serverKeyPair.privateKey,
    256
  );

  const salt = crypto.getRandomValues(new Uint8Array(16));

  // RFC 8291 §3.4: IKM = HKDF(salt=auth_secret, IKM=ecdh_secret, info="WebPush: info\0"||ua_pub||as_pub)
  const prk = await hkdf(
    new Uint8Array(sharedBits),
    concat(new TextEncoder().encode('WebPush: info\0'), receiverPublicKey, serverPublicKeyRaw),
    authSecret,
    32
  );

  const cek = await hkdf(prk, new TextEncoder().encode('Content-Encoding: aes128gcm\0'), salt, 16);
  const nonce = await hkdf(prk, new TextEncoder().encode('Content-Encoding: nonce\0'), salt, 12);

  const key = await crypto.subtle.importKey('raw', cek, 'AES-GCM', false, ['encrypt']);
  const data = new TextEncoder().encode(plaintext);
  // Aggiungi byte di padding: 0x02 (record delimiter) + 1 byte padding length 0
  const padded = concat(data, new Uint8Array([2]));

  const encrypted = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: nonce },
    key,
    padded
  );

  return {
    ciphertext: new Uint8Array(encrypted),
    salt,
    serverPublicKey: serverPublicKeyRaw,
  };
}

function buildBody(salt, serverPublicKey, ciphertext) {
  // RFC 8291 §4: salt (16) + rs (4, big-endian) + idlen (1) + keyid (65) + ciphertext
  const rs = new Uint8Array(4);
  new DataView(rs.buffer).setUint32(0, 4096, false);
  const idlen = new Uint8Array([serverPublicKey.length]);
  return concat(salt, rs, idlen, serverPublicKey, ciphertext);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
async function hkdf(ikm, info, salt, length) {
  const key = await crypto.subtle.importKey('raw', ikm, 'HKDF', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits(
    { name: 'HKDF', hash: 'SHA-256', salt, info },
    key,
    length * 8
  );
  return new Uint8Array(bits);
}

async function listAllKeys(kv) {
  const keys = [];
  let cursor;
  do {
    const result = await kv.list({ cursor });
    keys.push(...result.keys.map(k => k.name));
    cursor = result.list_complete ? null : result.cursor;
  } while (cursor);
  return keys;
}

function b64url(str) {
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

function b64urlBytes(bytes) {
  let bin = '';
  bytes.forEach(b => { bin += String.fromCharCode(b); });
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

function base64urlDecode(str) {
  const s = str.replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(s.padEnd(s.length + (4 - s.length % 4) % 4, '='));
  return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
}

function concat(...arrays) {
  const total = arrays.reduce((n, a) => n + a.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const a of arrays) { out.set(a, offset); offset += a.length; }
  return out;
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...CORS, 'Content-Type': 'application/json' },
  });
}
