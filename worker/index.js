/**
 * Cloudflare Worker — global leaderboard for steam-guesser
 *
 * Endpoints:
 *   GET  /top       → 200 JSON array (top 100 entries, sorted by score desc)
 *   POST /submit    → 200 { ok, rank, top, entry_ts } | 4xx { error }
 *
 * KV namespace binding name: LB
 * Storage layout (single key for simplicity, fine for low traffic):
 *   lb:top   → JSON array of entries, capped at 100
 *   rate:{ip} → '1' with 60s TTL, used as IP throttle
 *
 * Anti-cheat is best-effort:
 *   - score must equal perfects*100 + nears*50
 *   - perfects+nears+misses must equal picks
 *   - picks capped at 30 (3 minutes / ~6s per question is the realistic upper bound)
 *   - score capped at 2000
 *   - name length 1-16
 *   - 1 submit per IP per 60s
 *
 * Deploy:
 *   wrangler kv:namespace create LB
 *   (paste namespace id into wrangler.toml)
 *   wrangler deploy
 */

const TOP_CAP = 100;
const RATE_TTL_SEC = 60;
const MAX_NAME_LEN = 16;
const MAX_PICKS = 30;
const MAX_SCORE = 2000;

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Max-Age': '86400',
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS });
    }

    try {
      if (url.pathname === '/top' && request.method === 'GET') {
        return await getTop(env);
      }
      if (url.pathname === '/submit' && request.method === 'POST') {
        return await submit(request, env);
      }
      return jsonError('not_found', 404);
    } catch (e) {
      return jsonError(e.message || 'server_error', 500);
    }
  },
};

// ---------- handlers ----------
async function getTop(env) {
  const data = await env.LB.get('lb:top');
  return jsonOk(data ? JSON.parse(data) : []);
}

async function submit(request, env) {
  // 1. rate limit
  const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
  const rateKey = `rate:${ip}`;
  if (await env.LB.get(rateKey)) {
    return jsonError('rate_limited', 429);
  }

  // 2. parse + validate
  let body;
  try { body = await request.json(); }
  catch (_) { return jsonError('invalid_json', 400); }

  const name = sanitizeName(body.name);
  if (!name) return jsonError('name_required', 400);

  const score    = toInt(body.score);
  const picks    = toInt(body.picks);
  const perfects = toInt(body.perfects);
  const nears    = toInt(body.nears);
  const misses   = toInt(body.misses);

  if (score < 0 || score > MAX_SCORE)        return jsonError('invalid_score', 400);
  if (picks < 1 || picks > MAX_PICKS)         return jsonError('invalid_picks', 400);
  if (perfects < 0 || nears < 0 || misses < 0) return jsonError('invalid_counts', 400);
  if (perfects + nears + misses !== picks)    return jsonError('counts_mismatch', 400);
  if (score !== perfects * 100 + nears * 50)  return jsonError('score_mismatch', 400);

  // 3. assemble entry
  const entry = {
    name, score, picks, perfects, nears, misses,
    ts: Math.floor(Date.now() / 1000),
  };

  // 4. read-modify-write top list
  const raw = await env.LB.get('lb:top');
  const lb = raw ? JSON.parse(raw) : [];
  lb.push(entry);
  lb.sort((a, b) => (b.score - a.score) || (b.ts - a.ts));
  const capped = lb.slice(0, TOP_CAP);
  await env.LB.put('lb:top', JSON.stringify(capped));

  // 5. set rate cooldown
  await env.LB.put(rateKey, '1', { expirationTtl: RATE_TTL_SEC });

  // 6. find rank of this entry in the new top
  const rank = capped.findIndex(e => e.ts === entry.ts && e.name === entry.name) + 1;
  return jsonOk({ ok: true, rank: rank || null, top: capped, entry_ts: entry.ts });
}

// ---------- helpers ----------
function sanitizeName(raw) {
  if (typeof raw !== 'string') return '';
  // 移除控制字元、修剪首尾空白、截長
  const cleaned = raw.replace(/[\x00-\x1f\x7f]/g, '').trim().slice(0, MAX_NAME_LEN);
  return cleaned;
}

function toInt(v) {
  const n = Number(v);
  return Number.isFinite(n) ? (n | 0) : -1;
}

function jsonOk(data) {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { 'Content-Type': 'application/json; charset=utf-8', ...CORS },
  });
}

function jsonError(error, status) {
  return new Response(JSON.stringify({ error }), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', ...CORS },
  });
}
