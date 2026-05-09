// Steam Review Guesser — static frontend
// Port of app.py (Streamlit) to vanilla JS for GitHub Pages deployment.
// 資料 (games.json) 由 GitHub Actions 預先烘焙;前端純靜態載入。

import { applyI18n, t, T, THEME_OF, LANGS } from './modules/i18n.js';
import { mountBGM }       from './modules/bgm.js';
import { mountParticles } from './modules/particles.js';
import { startTimer }     from './modules/timer.js';
import { playSFX, playHoverSFX, playPressSFX, playTickSFX, playClockSFX, mountSfxControls } from './modules/sfx.js';
import { triggerPerfectFx, triggerMissShake, boostCrt, showToast, triggerTimeUpFx } from './modules/fx.js';
import { extractAccentColor, applyAccent } from './modules/colorize.js';

// ---------- 設定(從 data/config.json 載入)----------
let LEADERBOARD_API = '';   // boot 時填入,空白 = 沒設定 → fallback 到本機排行榜

// ---------- 常數 ----------
const BUCKETS = [
  { lo: 10,    hi: 100,    label: '10–100' },
  { lo: 100,   hi: 1000,   label: '100–1K' },
  { lo: 1000,  hi: 10000,  label: '1K–10K' },
  { lo: 10000, hi: 50000,  label: '10K–50K' },
];
const LETTERS = ['A', 'B', 'C', 'D'];
const SCORE_TABLE = { 0: 100, 1: 50 };
// 兩個遊玩模式 — Timed 3 分鐘倒數,Endless 無時間限制
const MODES = {
  timed:   { label: 'TIME ATTACK', labelTc: '計時挑戰', time: 180, icon: '⏱' },
  endless: { label: 'ENDLESS',     labelTc: '無盡',     time: 0,   icon: '∞' },
};
const DEFAULT_MODE = 'timed';
const HISTORY_CAP = 1000;          // localStorage 歷史記錄上限
const LEADERBOARD_CAP = 10;        // 本機排行榜 top N

// ---------- state(取代 st.session_state)----------
const state = {
  lang: 'EN',
  mode: DEFAULT_MODE,              // sprint/standard/marathon/endless
  phase: 'boot',                   // boot → idle → playing → revealed → ended
  game: null,
  picked: null,
  seen: new Set(),                 // session-only,重整頁就清(同 app.py:416)
  streak: 0,
  best: 0,
  hist_total: 0,
  hist_score_sum: 0,
  session_score: 0,
  session_picks: 0,
  session_perfects: 0,
  session_nears: 0,
  session_misses: 0,
  session_start_time: 0,           // seconds (Date.now()/1000)
  session_best: 0,
  session_combo: 0,                // 連續 perfect 數,用來計倍率
  question_start_time: 0,          // 本題進入 playing 的時間 (ms),用來計時間獎金
  session_games: [],               // 本場每題:{appid, name_en, name_tc, reviews, bucket, picked, score, base, bonus, multiplier}
  ended_is_record: false,          // setPhase('ended') 進入時計算一次,避免重渲染又比一次
  ended_just_added_ts: 0,          // 剛剛這場進入【本機】排行榜的時間戳,用來高亮
  last_score_breakdown: null,      // 上題的 {base,bonus,multiplier,final,fast},revealed 顯示用
  // 全球排行榜
  lb_global: [],                   // top entries from Worker
  lb_global_status: 'idle',        // 'idle' | 'loading' | 'ok' | 'error'
  lb_my_global_ts: 0,              // 提交成功後 Worker 回傳的 entry_ts,用來高亮
  lb_my_global_rank: 0,
  lb_submitted: false,             // 本場是否已送出全球排行榜
  lb_submit_state: 'idle',         // 'idle' | 'submitting' | 'ok' | 'error'
  lb_submit_error: '',
  player_name: '',                 // 上次填過的名字,從 localStorage 讀
  pool: null,                      // games array from games.json
};

let stopTimerFn = null;

// ---------- localStorage(取代 ~/.config/steam-guesser/*)----------
const storage = {
  loadHistory: () => {
    try { return JSON.parse(localStorage.getItem('sg_history') || '[]'); }
    catch (_) { return []; }
  },
  appendHistory: (entry) => {
    const h = storage.loadHistory();
    h.push(entry);
    if (h.length > HISTORY_CAP) h.splice(0, h.length - HISTORY_CAP);
    try { localStorage.setItem('sg_history', JSON.stringify(h)); } catch (_) { /* quota=0 in private mode → silent */ }
  },
  loadBest: () => {
    const v = parseInt(localStorage.getItem('sg_best') || '0', 10);
    return Number.isFinite(v) ? v : 0;
  },
  saveBest: (n) => { try { localStorage.setItem('sg_best', String(n)); } catch (_) {} },
  loadLang: () => {
    const v = localStorage.getItem('sg_lang');
    return LANGS.includes(v) ? v : 'EN';
  },
  saveLang: (l) => { try { localStorage.setItem('sg_lang', l); } catch (_) {} },

  // 玩家暱稱(全球排行榜送出時記住,下次自動填)
  loadName: () => localStorage.getItem('sg_player_name') || '',
  saveName: (n) => { try { localStorage.setItem('sg_player_name', String(n).slice(0, 16)); } catch (_) {} },

  // 上次選擇的模式
  loadMode: () => {
    const v = localStorage.getItem('sg_mode');
    return MODES[v] ? v : DEFAULT_MODE;
  },
  saveMode: (m) => { try { if (MODES[m]) localStorage.setItem('sg_mode', m); } catch (_) {} },

  // 本機排行榜(top N session 分數,跨頁面持久化但限本瀏覽器)
  loadLeaderboard: () => {
    try { return JSON.parse(localStorage.getItem('sg_leaderboard') || '[]'); }
    catch (_) { return []; }
  },
  appendLeaderboard: (entry) => {
    const lb = storage.loadLeaderboard();
    lb.push(entry);
    // 高分在前;同分時新的在前
    lb.sort((a, b) => (b.score - a.score) || (b.ts - a.ts));
    const capped = lb.slice(0, LEADERBOARD_CAP);
    try { localStorage.setItem('sg_leaderboard', JSON.stringify(capped)); } catch (_) {}
    return capped;
  },
};

// ---------- 純函式(直譯自 app.py:309-398)----------
function bucketOf(n) {
  for (let i = 0; i < BUCKETS.length; i++) {
    const b = BUCKETS[i];
    if (n >= b.lo && n < b.hi) return i;
  }
  return BUCKETS.length - 1;
}

function scoreFor(picked, actual) {
  return SCORE_TABLE[Math.abs(picked - actual)] ?? 0;
}

// 取得當前模式的倒數秒數;endless 回 0
function currentTimeLimit() {
  return MODES[state.mode]?.time ?? 0;
}
function isEndless() { return state.mode === 'endless'; }

// 計分:base × 連擊倍率(時間獎金已移除,避免鼓勵背題庫的玩法)
// elapsedMs 仍記錄,給 SPEED_DEMON 成就用,不再加分
function computeScore(picked, actualIdx, elapsedMs, comboBefore) {
  const base = scoreFor(picked, actualIdx);
  if (base === 0) {
    return { base: 0, bonus: 0, multiplier: 1, final: 0, comboAfter: 0, fast: false };
  }
  // 連擊只在 perfect (base=100) 才累加;只要不是 perfect 就清零
  const comboAfter = base === 100 ? comboBefore + 1 : 0;
  // 倍率:只在 perfect 且 combo ≥ 2 啟動
  let multiplier = 1;
  if (base === 100) {
    if (comboAfter >= 5)      multiplier = 3;
    else if (comboAfter >= 3) multiplier = 2;
    else if (comboAfter >= 2) multiplier = 1.5;
  }
  const final = Math.round(base * multiplier);
  return { base, bonus: 0, multiplier, final, comboAfter, fast: elapsedMs < 2000 };
}

function trailingStreak(hist) {
  let s = 0;
  for (let i = hist.length - 1; i >= 0; i--) {
    if ((hist[i].score | 0) >= 50) s++;
    else break;
  }
  return s;
}

function bestStreak(hist) {
  let best = 0, cur = 0;
  for (const h of hist) {
    if ((h.score | 0) >= 50) { cur++; best = Math.max(best, cur); }
    else cur = 0;
  }
  return best;
}

function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function pickRandom(arr) { return arr[Math.floor(Math.random() * arr.length)]; }

function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// 計算本場解鎖的成就(只看 session 內統計)
function computeAchievements() {
  const games = state.session_games;
  const out = [];
  if (!games.length) return out;

  // FIRST_BLOOD:首次完美
  if (games.some(g => g.base === 100)) out.push({ key: 'ach_first_blood', icon: '🩸' });

  // TRIPLE / RAMPAGE:連續 perfect 達 3 / 5
  let cur = 0, maxStreak = 0;
  for (const g of games) { if (g.base === 100) { cur++; maxStreak = Math.max(maxStreak, cur); } else cur = 0; }
  if (maxStreak >= 5) out.push({ key: 'ach_rampage', icon: '🔥' });
  else if (maxStreak >= 3) out.push({ key: 'ach_triple', icon: '⚡' });

  // CLUTCH:時間到前 5 秒內答對(基於最後一題的提交時間)
  const lastG = games[games.length - 1];
  if (lastG && lastG.score > 0 && state.session_start_time > 0) {
    // 沒記每題提交時間,我們用「最後一題的 elapsed_ms」估—— 不夠精準,暫且改成 picks > 0 且 session 結束時還剩 < 5s
    // CLUTCH 只在計時模式有意義
    const tl = currentTimeLimit();
    if (tl > 0) {
      const elapsed = state.ended_just_added_ts - state.session_start_time;
      if (elapsed >= tl - 5 && elapsed <= tl + 1 && lastG.score > 0) {
        out.push({ key: 'ach_clutch', icon: '⏰' });
      }
    }
  }

  // SHARPSHOOTER:perfect ≥ 80%
  if (games.length >= 5 && state.session_perfects / games.length >= 0.8) {
    out.push({ key: 'ach_sharpshooter', icon: '🎯' });
  }

  // SPEED_DEMON:平均 elapsed < 3s
  if (games.length >= 5) {
    const avgMs = games.reduce((s, g) => s + (g.elapsed_ms || 0), 0) / games.length;
    if (avgMs < 3000) out.push({ key: 'ach_speed_demon', icon: '⚡' });
  }

  // FLAWLESS:沒任何 miss
  if (games.length >= 5 && state.session_misses === 0) {
    out.push({ key: 'ach_no_miss', icon: '✨' });
  }

  // MARATHON:答 ≥ 15 題
  if (games.length >= 15) out.push({ key: 'ach_marathon', icon: '🏃' });

  return out;
}

// 把這場成績格式化成可分享的 emoji 文字(像 wordle)
function buildShareText() {
  const lang = state.lang;
  const score = state.session_score | 0;
  const picks = state.session_picks;
  // 用本場 session_games 還原每題的命中等級
  const cells = state.session_games.map(g => {
    if (g.score === 0) return '✗';
    if (g.base === 100) return '⭐';
    return '◉';
  }).join('');
  const url = location.origin + location.pathname;
  return [
    `STEAM REVIEW GUESSER · ${score} pts (${picks} picks)`,
    `${cells}`,
    `${url}`,
  ].join('\n');
}

async function copyShareText() {
  const text = buildShareText();
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      // fallback:臨時 textarea + execCommand
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus(); ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    showToast({ icon: '📋', title: t(state.lang, 'share_copied'), tier: 'default', durationMs: 1800 });
    return true;
  } catch (e) {
    showToast({ icon: '⚠', title: t(state.lang, 'share_failed'), tier: 'silver', durationMs: 2000 });
    return false;
  }
}

// 從 game 拼一句冷知識(revealed 顯示用)
function genTrivia(g, lang) {
  const loc = gameLocalized(g, lang);
  const candidates = [];
  // 1. 售價 + 區間
  if (loc.price && loc.price !== '—') {
    candidates.push(lang === 'EN'
      ? `Listed at ${loc.price} on Steam.`
      : `Steam 售價 ${loc.price}。`);
  }
  // 2. 開發商
  if (loc.developers && loc.developers.length) {
    const dev = loc.developers[0];
    candidates.push(lang === 'EN'
      ? `Developed by ${dev}.`
      : `由 ${dev} 開發。`);
  }
  // 3. 發售日期 + 推算年代
  if (loc.release_date && loc.release_date !== '—') {
    const yMatch = loc.release_date.match(/(\d{4})/);
    if (yMatch) {
      const yr = parseInt(yMatch[1], 10);
      const age = new Date().getFullYear() - yr;
      candidates.push(lang === 'EN'
        ? `Released in ${yr} — ${age} years on Steam.`
        : `${yr} 年發售,在 Steam 上耕耘 ${age} 年。`);
    } else {
      candidates.push(lang === 'EN'
        ? `Released ${loc.release_date}.`
        : `發售於 ${loc.release_date}。`);
    }
  }
  // 4. 評論數 + 桶位置
  const b = bucketOf(g.reviews);
  const bandLabel = BUCKETS[b].label;
  candidates.push(lang === 'EN'
    ? `${(g.reviews | 0).toLocaleString()} reviews — sits firmly in the ${bandLabel} band.`
    : `${(g.reviews | 0).toLocaleString()} 則評論,落在 ${bandLabel} 區間。`);
  // 5. 類型相關(若有)
  if (loc.genres && loc.genres.length) {
    const tag = loc.genres[0];
    candidates.push(lang === 'EN'
      ? `Tagged primarily as ${tag}.`
      : `主要分類:${tag}。`);
  }
  return candidates.length ? candidates[Math.floor(Math.random() * candidates.length)] : '';
}

// 數字計數動畫(ease-out cubic,默認 600ms)
function animateNumber(el, from, to, durationMs = 600, prefix = '+') {
  const start = performance.now();
  function tick(now) {
    const t = Math.min(1, (now - start) / durationMs);
    const eased = 1 - Math.pow(1 - t, 3);
    const value = Math.round(from + (to - from) * eased);
    el.textContent = prefix + value;
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

// ---------- 設定 + 全球排行榜 API ----------
async function loadConfig() {
  try {
    const cfg = await fetch('data/config.json', { cache: 'no-store' }).then(r => r.json());
    if (cfg && typeof cfg.leaderboard_api === 'string') {
      LEADERBOARD_API = cfg.leaderboard_api.replace(/\/$/, '');
    }
  } catch (_) { /* 沒 config 也 OK,降級成本機排行榜 */ }
}

async function fetchGlobalLb() {
  if (!LEADERBOARD_API) {
    state.lb_global_status = 'idle';
    return;
  }
  state.lb_global_status = 'loading';
  try {
    const r = await fetch(`${LEADERBOARD_API}/top`);
    if (!r.ok) throw new Error('http ' + r.status);
    const data = await r.json();
    state.lb_global = Array.isArray(data) ? data : [];
    state.lb_global_status = 'ok';
  } catch (e) {
    console.warn('global lb fetch failed:', e);
    state.lb_global_status = 'error';
  }
  // 重新 render(可能在 ended phase 等顯示資料)
  if (state.phase === 'ended') render();
}

async function submitGlobalLb(name) {
  if (!LEADERBOARD_API) return false;
  state.lb_submit_state = 'submitting';
  state.lb_submit_error = '';
  render();
  try {
    const r = await fetch(`${LEADERBOARD_API}/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        score: state.session_score | 0,
        picks: state.session_picks,
        perfects: state.session_perfects,
        nears: state.session_nears,
        misses: state.session_misses,
      }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const code = data.error || 'unknown';
      state.lb_submit_state = 'error';
      state.lb_submit_error =
        code === 'rate_limited' ? t(state.lang, 'submit_error_rate') :
        (code.startsWith('invalid') || code.endsWith('_mismatch') || code === 'name_required') ? t(state.lang, 'submit_error_invalid') :
        t(state.lang, 'submit_error_network');
      render();
      return false;
    }
    state.lb_global = Array.isArray(data.top) ? data.top : state.lb_global;
    state.lb_my_global_ts = data.entry_ts || 0;
    state.lb_my_global_rank = data.rank || 0;
    state.lb_submitted = true;
    state.lb_submit_state = 'ok';
    storage.saveName(name);
    state.player_name = name;
    render();
    // 進前 10 名 → 跳 rank-up toast,前 3 名加金/銀/銅 tier
    const rank = state.lb_my_global_rank;
    if (rank >= 1 && rank <= 10) {
      const tier = rank === 1 ? 'gold' : rank === 2 ? 'silver' : rank === 3 ? 'bronze' : 'top10';
      const icon = rank === 1 ? '🏆' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : '↑';
      showToast({
        icon,
        title: `${t(state.lang, 'your_rank')}: #${rank}`,
        subtitle: rank <= 3 ? '🌟 TOP ' + rank : '',
        tier,
        durationMs: 3500,
      });
    }
    return true;
  } catch (e) {
    state.lb_submit_state = 'error';
    state.lb_submit_error = t(state.lang, 'submit_error_network');
    render();
    return false;
  }
}

// ---------- pool 載入 + cachebust ----------
async function loadPool() {
  // version.txt 先抓(no-store),再用其 hash 帶 query string 抓 games.json
  let v = '';
  try {
    v = (await fetch('data/version.txt', { cache: 'no-store' }).then(r => r.text())).trim();
  } catch (_) { /* 沒 version.txt 就吃預設 cache 行為 */ }
  const url = v ? `data/games.json?v=${encodeURIComponent(v)}` : 'data/games.json';
  const data = await fetch(url).then(r => {
    if (!r.ok) throw new Error('games.json fetch ' + r.status);
    return r.json();
  });
  if (!Array.isArray(data.games)) throw new Error('games.json schema mismatch');
  state.pool = data.games;
}

// findTarget — 已在 build 端預分桶(g.bucket),JS 端只要過濾 seen + 桶公平抽
function findTarget() {
  if (!state.pool) return null;
  const byBucket = BUCKETS.map(() => []);
  for (const g of state.pool) {
    if (g.bucket >= 0 && g.bucket < BUCKETS.length && !state.seen.has(g.appid)) {
      byBucket[g.bucket].push(g);
    }
  }
  // 隨機桶順序,每桶找到第一個就回傳
  for (const b of shuffle([0, 1, 2, 3])) {
    if (byBucket[b].length) return pickRandom(byBucket[b]);
  }
  // 全看過了 → 重置 seen 再試一次(避免完全卡死)
  if (state.seen.size > 0) {
    state.seen.clear();
    return findTarget();
  }
  return null;
}

// ---------- 從 history 重算 HUD 統計值 ----------
function rebuildHistStats() {
  const h = storage.loadHistory();
  state.hist_total = h.length;
  state.hist_score_sum = h.reduce((s, e) => s + (e.score | 0), 0);
  state.streak = trailingStreak(h);
  state.best = bestStreak(h);
}

// ---------- HUD ----------
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}
function updateHUD() {
  const total = state.hist_total;
  const avg = total ? state.hist_score_sum / total : 0;
  setText('hud-streak', state.streak);
  setText('hud-best', state.best);
  setText('hud-runs', total);
  setText('hud-avg', avg.toFixed(0));
  // combo 達 2 才顯示;>=5 加 RAMPAGE 樣式
  const comboRow = document.getElementById('hud-combo-row');
  if (!comboRow) return;
  if (state.session_combo >= 2) {
    comboRow.hidden = false;
    setText('hud-combo', state.session_combo);
    comboRow.classList.toggle('combo-rampage', state.session_combo >= 5);
  } else {
    comboRow.hidden = true;
    comboRow.classList.remove('combo-rampage');
  }
}

// ---------- 語言 ----------
function applyLang() {
  document.body.dataset.theme = THEME_OF[state.lang];
  applyI18n(state.lang);
  // lang switch 按鈕的 active class
  for (const btn of document.querySelectorAll('#lang-switch button')) {
    btn.classList.toggle('active', btn.dataset.lang === state.lang);
  }
}

// ---------- 渲染 ----------
const view = () => document.getElementById('view');

function tplLoader(line1, line2) {
  return `
    <div class="loader fade-in">
      <div class="row"><span class="loader-line l1">&gt; ${escapeHtml(line1)}</span></div>
      <div class="row"><span class="loader-line l2">&gt; ${escapeHtml(line2)}</span></div>
      <div class="dots"><span></span><span></span><span></span></div>
      <div class="progress-bar"></div>
    </div>
  `;
}

function tplIdle() {
  const lang = state.lang;
  // 兩個 CTA 卡:模式 + 開始合併。Timed = 綠(主推),Endless = 金(略低調)
  const cta = (key, variant) => {
    const m = MODES[key];
    const bigLabel = lang === 'EN' ? m.label : m.labelTc;
    const sub = key === 'timed'
      ? (lang === 'EN' ? '03:00 · race the clock' : '03:00 · 衝高分')
      : (lang === 'EN' ? 'no clock · play freely' : '無時間限制 · 玩到爽');
    const tag = key === 'timed' ? '[T]' : '[∞]';
    const action = key === 'timed'
      ? (lang === 'EN' ? '▶ START TIMED' : '▶ 開始計時')
      : (lang === 'EN' ? '▶ START ENDLESS' : '▶ 開始無盡');
    return `
      <button class="cta-card cta-${variant}" data-mode="${key}">
        <div class="cta-head">
          <span class="cta-tag">${tag}</span>
          <span class="cta-name">${escapeHtml(bigLabel)}</span>
        </div>
        <div class="cta-sub">${escapeHtml(sub)}</div>
        <div class="cta-action">${action}</div>
      </button>
    `;
  };
  return `
    <div class="hero fade-in">
      <div class="hero-icon">◉</div>
      <h1 class="hero-title">${escapeHtml(t(lang, 'title'))}</h1>
      <div class="hero-tagline">// ${escapeHtml(t(lang, 'tagline'))}</div>
      <div class="hero-divider"></div>
      <h2 class="hero-status">&gt; ${escapeHtml(t(lang, 'ready'))}</h2>
      <p>${escapeHtml(t(lang, 'intro'))}</p>
      <div class="rules">${escapeHtml(t(lang, 'rules'))}</div>
    </div>
    <div class="cta-grid">
      ${cta('timed', 'timed')}
      ${cta('endless', 'endless')}
    </div>
    ${tplHistoryExpander()}
  `;
}

function tplHistoryExpander() {
  if (!state.hist_total) return '';
  const lang = state.lang;
  const hist = storage.loadHistory();
  const valid = hist.filter(h => h.picked >= 0 && h.picked < BUCKETS.length && h.actual_bucket >= 0 && h.actual_bucket < BUCKETS.length);
  const recent = valid.slice(-10).reverse();
  const rows = recent.map(h => `
    <tr>
      <td>${escapeHtml(h.name || '')}</td>
      <td>[${LETTERS[h.picked]}] ${BUCKETS[h.picked].label}</td>
      <td>[${LETTERS[h.actual_bucket]}] ${BUCKETS[h.actual_bucket].label}</td>
      <td>${(h.actual_reviews | 0).toLocaleString()}</td>
      <td>${h.score | 0}</td>
    </tr>
  `).join('');
  return `
    <details class="expander">
      <summary>${escapeHtml(t(lang, 'history'))}</summary>
      <div class="body">
        <table>
          <thead>
            <tr>
              <th>${escapeHtml(t(lang, 'tbl_target'))}</th>
              <th>${escapeHtml(t(lang, 'tbl_pick'))}</th>
              <th>${escapeHtml(t(lang, 'tbl_actual'))}</th>
              <th>${escapeHtml(t(lang, 'tbl_reviews'))}</th>
              <th>${escapeHtml(t(lang, 'tbl_score'))}</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </details>
  `;
}

function gameLocalized(g, lang) {
  return g[THEME_OF[lang]] || g.en || g.tc || {};
}

// 上半段 (影片/圖片 + metadata) — playing/revealed 共用,只渲染一次,
// phase 切換時不會重建 → 影片不會重播、標題不會重打字
function tplGameUpper() {
  const g = state.game;
  const lang = state.lang;
  const loc = gameLocalized(g, lang);
  const title = loc.name || '—';
  const desc = loc.short_description || '—';
  const genres = (loc.genres || []).slice(0, 4).join(' · ') || '—';
  const release = loc.release_date || '—';
  const price = loc.price || '—';
  const devs = (loc.developers || []).slice(0, 2).join(', ') || '—';

  let mediaHtml = '';
  if (g.trailer_url) {
    mediaHtml = `<video class="hero-media" src="${escapeHtml(g.trailer_url)}" autoplay loop muted playsinline></video>`;
  } else if (g.header_image) {
    mediaHtml = `<img class="hero-media" src="${escapeHtml(g.header_image)}" alt="">`;
  }
  const shotsHtml = (g.screenshots || []).slice(0, 3).map(s => `<img src="${escapeHtml(s)}" alt="">`).join('');

  return `
    <div class="split">
      <div class="col">
        <div class="prompt"><span class="arrow">&gt;</span><span class="accent">${escapeHtml(t(lang, 'scanning'))}</span></div>
        <div class="media">${mediaHtml}</div>
        ${shotsHtml ? `<div class="shots">${shotsHtml}</div>` : ''}
      </div>
      <div class="col">
        <div class="prompt"><span class="arrow">&gt;</span><span class="accent">${escapeHtml(t(lang, 'metadata'))}</span></div>
        <div class="panel panel-glow">
          <div class="target-title">${escapeHtml(title)}</div>
          <div class="target-desc">${escapeHtml(desc)}</div>
          <div class="meta">
            <div class="row"><span class="k">${escapeHtml(t(lang, 'genre'))}</span><span class="sep">::</span><span class="v">${escapeHtml(genres)}</span></div>
            <div class="row"><span class="k">${escapeHtml(t(lang, 'release'))}</span><span class="sep">::</span><span class="v">${escapeHtml(release)}</span></div>
            <div class="row"><span class="k">${escapeHtml(t(lang, 'price'))}</span><span class="sep">::</span><span class="v">${escapeHtml(price)}</span></div>
            <div class="row"><span class="k">${escapeHtml(t(lang, 'dev'))}</span><span class="sep">::</span><span class="v">${escapeHtml(devs)}</span></div>
          </div>
        </div>
      </div>
    </div>
  `;
}

// playing 下半段:QUERY + 4 個 bucket 按鈕(endless 多一個 END RUN)
function tplPlayingLower() {
  const lang = state.lang;
  const bucketBtns = BUCKETS.map((b, i) => `
    <button class="btn bk-btn" data-bucket="${i}">
      [ ${LETTERS[i]} ]    ${b.label}
      <span class="kbd-hint">${LETTERS[i]}</span>
    </button>
  `).join('');
  const endlessBtn = isEndless() ? `
    <div class="endless-actions">
      <button class="btn end-run-btn" id="btn-end-run">[ ${escapeHtml(t(lang, 'end_run'))} ]</button>
    </div>
  ` : '';
  return `
    <div class="spacer-md"></div>
    <div class="prompt" id="query-prompt">
      <span class="arrow">&gt;</span><span class="accent">QUERY</span>
      <span style="color: var(--dim); margin-left:6px;">${escapeHtml(t(lang, 'query'))}</span><span class="caret"></span>
    </div>
    <div class="dim-sub">${escapeHtml(t(lang, 'select_prompt'))}</div>
    <div class="bk-buttons">${bucketBtns}</div>
    ${endlessBtn}
  `;
}

// revealed 下半段:閃光 + verdict + 分數 + log + chips + Next 按鈕
function tplRevealedLower() {
  const g = state.game;
  const lang = state.lang;
  const picked = state.picked;
  const actualIdx = bucketOf(g.reviews);
  const sc = state.last_score_breakdown || { base: 0, bonus: 0, multiplier: 1, final: 0, fast: false, comboAfter: 0 };
  const labelMap = { 100: t(lang, 'lbl_perfect'), 50: t(lang, 'lbl_adjacent'), 0: t(lang, 'lbl_miss') };
  const verdictMap = { 100: ['★', 'MATCH'], 50: ['◉', 'NEAR_HIT'], 0: ['✗', 'DEVIATION'] };
  const [vSym, vCode] = verdictMap[sc.base];
  const logClass = { 100: 'success', 50: 'gold', 0: 'danger' }[sc.base];
  const delta = picked - actualIdx;

  // verdict 文字 — 連擊倍率時加附註,大連擊時 RAMPAGE
  let vText = vCode;
  let verdictExtraClass = '';
  if (sc.multiplier >= 3) { vText = `RAMPAGE × ${sc.multiplier}`; verdictExtraClass = 'verdict-rampage'; }
  else if (sc.multiplier > 1) { vText = `${vCode} × ${sc.multiplier}`; verdictExtraClass = 'verdict-combo'; }

  // breakdown:base + bonus + multiplier 三個小格子
  let breakdownHtml = '';
  if (sc.base > 0) {
    const parts = [`<span class="bd-base">+${sc.base}</span>`];
    if (sc.bonus > 0) {
      parts.push(`<span class="bd-bonus">⚡ +${sc.bonus}${sc.fast ? ' FAST' : ''}</span>`);
    }
    if (sc.multiplier > 1) {
      parts.push(`<span class="bd-combo">× ${sc.multiplier}</span>`);
    }
    breakdownHtml = `<div class="breakdown">${parts.join('')}</div>`;
  }

  // chip 序列化揭曉:錯的先暗化,正解最後高亮
  // - data-reveal-order 控制動畫延遲(透過 CSS variable --rd)
  // - 錯的 chip(非 actual、非 picked)排在前 3 位,延遲 0.05/0.15/0.25
  // - picked-but-wrong 第 4 位,延遲 0.45 (短暫停頓後出現紅光)
  // - actualIdx (正解) 最後出,延遲 0.7 (高潮)
  const order = (() => {
    const others = [];
    let pickedWrongIdx = -1;
    let actualOrderIdx = -1;
    for (let i = 0; i < BUCKETS.length; i++) {
      if (i === actualIdx) continue;          // 正解最後處理
      if (i === picked) { pickedWrongIdx = i; continue; }
      others.push(i);
    }
    // 中性 chip 先排, picked-but-wrong 中段, 正解最後
    const seq = [];
    for (const i of others) seq.push({ idx: i, delay: 0.05 + seq.length * 0.1 });
    if (pickedWrongIdx >= 0) seq.push({ idx: pickedWrongIdx, delay: 0.45 });
    seq.push({ idx: actualIdx, delay: 0.75 });
    return seq;
  })();

  const chipsByIdx = new Map();
  for (const { idx, delay } of order) {
    let cls, mk;
    if (idx === actualIdx && idx === picked) { cls = 'chip chip-perfect'; mk = '★'; }
    else if (idx === actualIdx)              { cls = 'chip chip-correct'; mk = '✓'; }
    else if (idx === picked)                 { cls = 'chip chip-wrong';   mk = '✗'; }
    else                                      { cls = 'chip chip-neutral'; mk = LETTERS[idx]; }
    chipsByIdx.set(idx, `<div class="${cls}" style="--rd:${delay}s">${mk}</div>`);
  }
  const chips = BUCKETS.map((_, i) => chipsByIdx.get(i)).join('');

  const tl = currentTimeLimit();
  const timeUp = !isEndless() && tl > 0 && state.session_start_time > 0 && (Date.now() / 1000 - state.session_start_time) >= tl;
  const nextLabel = timeUp ? t(lang, 'view_results') : t(lang, 'next');

  return `
    <div class="spacer-md"></div>
    <div class="impact-flash impact-${sc.base}"></div>
    <div class="verdict verdict-${sc.base} ${verdictExtraClass}"><span class="tw">${vSym}&nbsp;&nbsp;${vText}</span></div>

    <div class="rev-split">
      <div>
        <div class="prompt"><span class="arrow">&gt;</span><span class="accent">${escapeHtml(t(lang, 'analysis_done'))}</span></div>
        <div class="score score-${sc.base}">
          <div class="num" data-score="${sc.final}">+0</div>
          <div class="lbl">${escapeHtml(labelMap[sc.base])}</div>
          ${breakdownHtml}
        </div>
      </div>
      <div>
        <div class="log steam"><span class="k">${escapeHtml(t(lang, 'actual'))}</span> <span style="color:var(--dimmer)">::</span> <span class="v">${(g.reviews | 0).toLocaleString()}</span></div>
        <div class="log"><span class="k">${escapeHtml(t(lang, 'correct'))}</span> <span style="color:var(--dimmer)">::</span> <span class="v">[${LETTERS[actualIdx]}] ${BUCKETS[actualIdx].label}</span></div>
        <div class="log"><span class="k">${escapeHtml(t(lang, 'your_pick'))}</span> <span style="color:var(--dimmer)">::</span> <span class="v">[${LETTERS[picked]}] ${BUCKETS[picked].label}</span></div>
        <div class="log ${logClass}"><span class="k">${escapeHtml(t(lang, 'delta'))}</span> <span style="color:var(--dimmer)">::</span> <span class="v">${delta >= 0 ? '+' : ''}${delta}</span></div>
      </div>
    </div>

    <div class="bk-strip">${chips}</div>

    <div class="trivia">// ${escapeHtml(genTrivia(g, lang))}</div>

    <div class="spacer-sm"></div>
    <div class="primary-row">
      <button class="btn primary" id="btn-next">[ ${escapeHtml(nextLabel)} ]</button>
    </div>
  `;
}

function tplAchievements() {
  const lang = state.lang;
  const list = computeAchievements();
  if (!list.length) return '';
  const cards = list.map((a, i) => {
    const trans = T[lang][a.key] || T['EN'][a.key] || ['', ''];
    const [title, desc] = trans;
    return `
      <div class="ach-card" style="--ach-i:${i}">
        <div class="ach-icon">${a.icon}</div>
        <div class="ach-body">
          <div class="ach-title">${escapeHtml(title)}</div>
          <div class="ach-desc">${escapeHtml(desc)}</div>
        </div>
      </div>
    `;
  }).join('');
  return `
    <div class="achievements">
      <div class="achievements-title">&gt; ${escapeHtml(t(lang, 'achievements'))} <span style="color:var(--dim);font-weight:500;">(${list.length})</span></div>
      <div class="ach-grid">${cards}</div>
    </div>
  `;
}

function tplEnded() {
  const lang = state.lang;
  const finalScore = state.session_score | 0;
  const recordHtml = state.ended_is_record
    ? `<div class="ended-record">★ ${escapeHtml(t(lang, 'new_record'))} ★</div>`
    : '';

  // 本場每一題,連到 Steam 商店頁
  const sessionRows = state.session_games.map(sg => {
    const name = (lang === 'EN' ? sg.name_en : sg.name_tc) || sg.name_en || `App ${sg.appid}`;
    const scoreClass = sg.score === 100 ? 'score-100' : sg.score === 50 ? 'score-50' : 'score-0';
    const url = `https://store.steampowered.com/app/${sg.appid}/`;
    return `
      <li>
        <a class="sg-link" href="${url}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(t(lang, 'open_steam'))}">
          <span class="sg-bucket">[${LETTERS[sg.bucket]}]</span>
          <span class="sg-name">${escapeHtml(name)}</span>
          <span class="sg-reviews">${sg.reviews.toLocaleString()}</span>
          <span class="sg-score ${scoreClass}">+${sg.score}</span>
          <span class="sg-arrow">↗</span>
        </a>
      </li>
    `;
  }).join('');
  const sessionListHtml = state.session_games.length ? `
    <div class="session-games">
      <div class="session-games-title">&gt; ${escapeHtml(t(lang, 'session_games'))} <span style="color:var(--dim);font-weight:500;">(${state.session_games.length})</span></div>
      <ul>${sessionRows}</ul>
    </div>
  ` : '';

  // ---------- 全球排行榜(只在 LEADERBOARD_API 設定時顯示) ----------
  let globalLbHtml = '';
  if (LEADERBOARD_API) {
    const gs = state.lb_global_status;
    let inner = '';
    if (gs === 'loading' || gs === 'idle') {
      inner = `<div class="lb-loading">${escapeHtml(t(lang, 'leaderboard_loading'))}</div>`;
    } else if (gs === 'error') {
      inner = `<div class="lb-loading lb-offline">${escapeHtml(t(lang, 'leaderboard_offline'))}</div>`;
    } else if (gs === 'ok') {
      const rows = state.lb_global.map((e, i) => {
        const isMine = e.ts === state.lb_my_global_ts;
        const date = new Date(e.ts * 1000);
        const dateStr = `${date.getMonth() + 1}/${date.getDate()}`;
        return `
          <li class="${isMine ? 'lb-current' : ''}">
            <span class="lb-rank">#${i + 1}</span>
            <span class="lb-name">${escapeHtml(e.name)}</span>
            <span class="lb-score">+${e.score}</span>
            <span class="lb-stats">
              <span class="lb-stat lb-perfect">★${e.perfects}</span>
              <span class="lb-stat lb-near">◉${e.nears}</span>
              <span class="lb-stat lb-miss">✗${e.misses}</span>
            </span>
            <span class="lb-date">${dateStr}</span>
          </li>
        `;
      }).join('');
      inner = state.lb_global.length
        ? `<ul class="lb-global-list">${rows}</ul>`
        : `<div class="lb-loading">—</div>`;
    }

    // submit 表單 / 已送出狀態 — endless 模式不上全球榜(避免不公平)
    let submitHtml = '';
    if (isEndless()) {
      submitHtml = `<div class="endless-lb-note">${escapeHtml(t(lang, 'endless_no_lb'))}</div>`;
    } else if (state.session_picks > 0) {
      if (state.lb_submitted) {
        submitHtml = `
          <div class="submit-done">
            <span class="submit-check">✓</span>
            <span>${escapeHtml(t(lang, 'submitted'))}</span>
            ${state.lb_my_global_rank ? `<span class="submit-rank">${escapeHtml(t(lang, 'your_rank'))}: <b>#${state.lb_my_global_rank}</b></span>` : ''}
          </div>
        `;
      } else {
        const submitBusy = state.lb_submit_state === 'submitting';
        const submitLabel = submitBusy ? t(lang, 'submitting') : t(lang, 'submit');
        const errMsg = state.lb_submit_state === 'error'
          ? `<div class="submit-error">${escapeHtml(state.lb_submit_error)}</div>`
          : '';
        submitHtml = `
          <div class="submit-row">
            <div class="submit-label">${escapeHtml(t(lang, 'submit_prompt'))}</div>
            <form id="lb-submit" class="submit-form">
              <input id="lb-name" type="text" maxlength="16" minlength="1"
                     placeholder="${escapeHtml(t(lang, 'name_placeholder'))}"
                     value="${escapeHtml(state.player_name || '')}"
                     ${submitBusy ? 'disabled' : ''} required>
              <button type="submit" class="btn submit-btn" ${submitBusy ? 'disabled' : ''}>
                [ ${escapeHtml(submitLabel)} ]
              </button>
            </form>
            ${errMsg}
          </div>
        `;
      }
    }

    globalLbHtml = `
      <div class="leaderboard leaderboard-global">
        <div class="leaderboard-title">&gt; ${escapeHtml(t(lang, 'leaderboard_global'))} ${gs === 'ok' ? `<span style="color:var(--dim);font-weight:500;">(${state.lb_global.length})</span>` : ''}</div>
        ${submitHtml}
        ${inner}
      </div>
    `;
  }

  // ---------- 本機排行榜 — 列出 top N,本場剛進來的這筆高亮 ----------
  const lb = storage.loadLeaderboard();
  const lbRows = lb.map((e, i) => {
    const isCurrent = e.ts === state.ended_just_added_ts;
    const date = new Date(e.ts * 1000);
    const dateStr = `${date.getMonth() + 1}/${date.getDate()}`;
    const timeStr = `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
    return `
      <li class="${isCurrent ? 'lb-current' : ''}">
        <span class="lb-rank">#${i + 1}</span>
        <span class="lb-score">+${e.score}</span>
        <span class="lb-stats">
          <span class="lb-stat">${e.picks}</span>
          <span class="lb-stat lb-perfect">★${e.perfects}</span>
          <span class="lb-stat lb-near">◉${e.nears}</span>
          <span class="lb-stat lb-miss">✗${e.misses}</span>
        </span>
        <span class="lb-date">${dateStr} ${timeStr}</span>
      </li>
    `;
  }).join('');
  // 有全球排行榜時,本機改成「個人最佳」,放在 details 收起來
  const localLbTitle = LEADERBOARD_API ? t(lang, 'leaderboard_local') : t(lang, 'leaderboard');
  const localLbInner = lb.length ? `
    <div class="leaderboard">
      <div class="leaderboard-title">&gt; ${escapeHtml(localLbTitle)} <span style="color:var(--dim);font-weight:500;">(${lb.length}/${LEADERBOARD_CAP})</span></div>
      <ul>${lbRows}</ul>
    </div>
  ` : '';
  // 有全球排行榜時,本機放進 expander(避免畫面太長);沒全球時直接顯示
  const leaderboardHtml = LEADERBOARD_API && lb.length ? `
    <details class="expander expander-local-lb">
      <summary>${escapeHtml(localLbTitle)} (${lb.length})</summary>
      <div class="body">${localLbInner}</div>
    </details>
  ` : localLbInner;

  return `
    <div class="impact-flash impact-100"></div>
    <div class="ended-wrap fade-in">
      <div class="ended-tag">${escapeHtml(t(lang, 'ended_title'))}</div>
      ${recordHtml}
      <div class="ended-score-num">+${finalScore}</div>
      <div class="ended-score-lbl">${escapeHtml(t(lang, 'session_score'))}</div>
    </div>

    <div class="rev-split">
      <div>
        <div class="log"><span class="k">${escapeHtml(t(lang, 'session_picks'))}</span> <span style="color:var(--dimmer)">::</span> <span class="v">${state.session_picks}</span></div>
        <div class="log success"><span class="k">${escapeHtml(t(lang, 'perfects'))}</span> <span style="color:var(--dimmer)">::</span> <span class="v">${state.session_perfects}</span></div>
        <div class="log gold"><span class="k">${escapeHtml(t(lang, 'near_hits'))}</span> <span style="color:var(--dimmer)">::</span> <span class="v">${state.session_nears}</span></div>
        <div class="log danger"><span class="k">${escapeHtml(t(lang, 'misses'))}</span> <span style="color:var(--dimmer)">::</span> <span class="v">${state.session_misses}</span></div>
      </div>
      <div>
        <div class="log"><span class="k">${escapeHtml(t(lang, 'personal_best'))}</span> <span style="color:var(--dimmer)">::</span> <span class="v">${state.session_best}</span></div>
      </div>
    </div>

    ${tplAchievements()}
    ${globalLbHtml}
    ${leaderboardHtml}
    ${sessionListHtml}

    <div class="spacer-sm"></div>
    <div class="primary-row primary-row-multi">
      <button class="btn share-btn" id="btn-share">[ 📋 ${escapeHtml(t(lang, 'share_run'))} ]</button>
      <button class="btn primary" id="btn-again">[ ${escapeHtml(t(lang, 'play_again'))} ]</button>
    </div>
  `;
}

function tplBoot() {
  const lang = state.lang;
  return `
    <div class="loader fade-in">
      <div class="row"><span class="loader-line l1">&gt; ${escapeHtml(t(lang, 'loading_data'))}</span></div>
      <div class="row"><span class="loader-line l2">&gt; ${escapeHtml(t(lang, 'data_first'))}</span></div>
      <div class="dots"><span></span><span></span><span></span></div>
      <div class="progress-bar"></div>
    </div>
  `;
}

function tplError(msg) {
  return `
    <div class="hero fade-in">
      <div class="icon">⚠</div>
      <h2 class="hero-status">&gt; ERROR</h2>
      <p>${escapeHtml(msg)}</p>
    </div>
  `;
}

// ---------- 渲染主入口 ----------
// 上半段(影片+資訊)只在「換新題目」時重建,phase 切換 (playing↔revealed) 只重 render 下半段;
// 這樣影片不會重播、標題不會重打字。view.dataset.upperKey 紀錄目前 upper 對應哪一場。
function render() {
  try { return renderInner(); }
  catch (e) {
    console.error('render() failed', e);
    const v = document.getElementById('view');
    if (v) {
      v.innerHTML = `
        <div class="hero fade-in">
          <div class="icon" style="color:var(--red)">⚠</div>
          <h2 class="hero-status" style="color:var(--red)">&gt; RENDER ERROR</h2>
          <p style="color:#ccc">phase = <b>${escapeHtml(String(state.phase))}</b></p>
          <p style="color:#888;font-size:11px;">${escapeHtml(String(e.message || e))}</p>
          <p style="color:#666;font-size:10px;">F12 看 console 拿完整 stack trace</p>
        </div>
      `;
    }
  }
}
function renderInner() {
  const v = view();
  const isGameView = ['playing', 'revealed'].includes(state.phase);
  const upperKey = isGameView && state.game ? `g${state.game.appid}` : '';
  const currentUpperKey = v.dataset.upperKey || '';

  if (isGameView && upperKey === currentUpperKey && v.querySelector('#lower')) {
    // 同一場遊戲、只是 phase 換 → 只重 render 下半段
    const lower = v.querySelector('#lower');
    lower.innerHTML = state.phase === 'playing' ? tplPlayingLower() : tplRevealedLower();
  } else {
    // 全部重 render(換新題、進非遊戲 phase、或第一次)
    let html = '';
    if (state.phase === 'boot')      html = tplBoot();
    else if (state.phase === 'idle')     html = tplIdle();
    else if (state.phase === 'ended')    html = tplEnded();
    else if (isGameView) {
      const lowerHtml = state.phase === 'playing' ? tplPlayingLower() : tplRevealedLower();
      html = `<div id="upper">${tplGameUpper()}</div><div id="lower">${lowerHtml}</div>`;
    }
    v.innerHTML = html;
    if (isGameView) v.dataset.upperKey = upperKey;
    else delete v.dataset.upperKey;
  }

  bindPhaseEvents();
  applyI18n(state.lang, v);
  updateHUD();

  // timer widget 顯隱
  const timerEl = document.getElementById('timer-widget');
  const showTimer = ['playing', 'revealed'].includes(state.phase);
  timerEl.hidden = !showTimer;
  if (!showTimer) timerEl.innerHTML = '';

  // 進到 playing/revealed 時 scroll 到結果區 + 觸發數字計數動畫
  if (state.phase === 'playing') {
    requestAnimationFrame(() => {
      const q = document.getElementById('query-prompt');
      if (q) q.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  } else if (state.phase === 'revealed') {
    requestAnimationFrame(() => {
      const verdict = v.querySelector('.verdict');
      if (verdict) verdict.scrollIntoView({ behavior: 'smooth', block: 'start' });
      // 分數計數動畫:0 → final
      const numEl = v.querySelector('.score .num[data-score]');
      if (numEl) {
        const target = parseInt(numEl.dataset.score, 10);
        animateNumber(numEl, 0, target, 700);
      }
      // 揭曉特效:perfect 全螢幕快閃 + 粒子爆炸;miss 整頁震;CRT 短暫加強
      const sc = state.last_score_breakdown;
      if (sc) {
        boostCrt();
        if (sc.base === 100) {
          const rect = verdict ? verdict.getBoundingClientRect() : null;
          const cx = rect ? rect.left + rect.width / 2 : window.innerWidth / 2;
          const cy = rect ? rect.top + rect.height / 2 : window.innerHeight / 2;
          triggerPerfectFx(cx, cy);
        } else if (sc.base === 0) {
          triggerMissShake();
        }
      }
    });
  }
}

// ---------- 轉場流程 ----------
// idle→playing / revealed→playing 用這條:內容淡出 → loader → 淡入新題 + staggered 進場
async function runStagedTransition({ findGame, freshSession }) {
  const v = view();

  // Step 1:現有內容淡出(0.6s)
  v.classList.add('fading');
  await sleep(620);

  // Step 2:loader 顯示(換內容後淡入,跑 typewriter ~1.4s)
  v.innerHTML = tplLoader(t(state.lang, 'load1'), t(state.lang, 'load2'));
  v.classList.remove('fading');
  await sleep(1400);

  // Step 3:loader 淡出(0.4s)
  v.classList.add('fading');
  await sleep(420);

  // Step 4:抽題 + 設好 state
  const g = findGame();
  if (!g) {
    v.classList.remove('fading');
    setPhase('idle');
    return;
  }
  state.game = g;
  state.seen.add(g.appid);
  state.picked = null;
  if (freshSession) {
    state.session_score = 0;
    state.session_picks = 0;
    state.session_perfects = 0;
    state.session_nears = 0;
    state.session_misses = 0;
    state.session_combo = 0;
    state.session_start_time = Date.now() / 1000;
    state.session_games = [];
    if (stopTimerFn) { stopTimerFn(); stopTimerFn = null; }
  }
  state.question_start_time = Date.now();
  // 從 header 圖抽主色當這題的 accent(背景跑,不阻塞 transition)
  applyAccent(null);
  if (g.header_image) {
    extractAccentColor(g.header_image).then(applyAccent);
  }

  // Step 5:body.staging 開,渲染 playing 內容,淡入
  document.body.classList.add('staging');
  state.phase = 'playing';
  render();
  // requestAnimationFrame 確保 fading→fade-in 之間瀏覽器有 layout flush,動畫不會被合併
  requestAnimationFrame(() => {
    requestAnimationFrame(() => v.classList.remove('fading'));
  });
  ensureTimerRunning();

  // Step 6:進場動畫(meta 列最後一個 1.84s+0.55s≈2.4s 結束)後關 staging
  setTimeout(() => document.body.classList.remove('staging'), 2700);
}

// ---------- 階段事件綁定 ----------
function bindPhaseEvents() {
  // idle 上的兩張 CTA 卡:點下去直接以該模式開始
  for (const c of document.querySelectorAll('.cta-card[data-mode]')) {
    c.addEventListener('click', () => onClickStartMode(c.dataset.mode));
  }

  const btnNext = document.getElementById('btn-next');
  if (btnNext) btnNext.addEventListener('click', onClickNext);

  const btnAgain = document.getElementById('btn-again');
  if (btnAgain) btnAgain.addEventListener('click', onClickAgain);

  const btnShare = document.getElementById('btn-share');
  if (btnShare) btnShare.addEventListener('click', copyShareText);

  for (const btn of document.querySelectorAll('.bk-btn')) {
    btn.addEventListener('click', () => onClickBucket(parseInt(btn.dataset.bucket, 10)));
  }

  // 結束本場(endless 模式 playing 時)
  const btnEndRun = document.getElementById('btn-end-run');
  if (btnEndRun) btnEndRun.addEventListener('click', onClickEndRun);

  const submitForm = document.getElementById('lb-submit');
  if (submitForm) {
    submitForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const input = document.getElementById('lb-name');
      const name = (input && input.value || '').trim().slice(0, 16);
      if (!name) { input && input.focus(); return; }
      submitGlobalLb(name);
    });
  }
}

// ---------- 事件 handlers ----------
let inTransition = false;

async function onClickStartMode(mode) {
  if (inTransition) return;
  if (mode && MODES[mode]) {
    state.mode = mode;
    storage.saveMode(mode);
  }
  inTransition = true;
  for (const c of document.querySelectorAll('.cta-card')) c.disabled = true;
  await runStagedTransition({ findGame: findTarget, freshSession: true });
  inTransition = false;
}

async function onClickNext() {
  if (inTransition) return;
  const tl = currentTimeLimit();
  const timeUp = !isEndless() && tl > 0 && state.session_start_time > 0 && (Date.now() / 1000 - state.session_start_time) >= tl;
  if (timeUp) {
    setPhase('ended');
    return;
  }
  inTransition = true;
  const btn = document.getElementById('btn-next');
  if (btn) btn.disabled = true;
  await runStagedTransition({ findGame: findTarget, freshSession: false });
  inTransition = false;
}

function onClickBucket(idx) {
  if (state.phase !== 'playing') return;
  // 答題後不該再跑進場動畫,即使 staging 的 setTimeout 還沒到也立刻關
  document.body.classList.remove('staging');
  const g = state.game;
  const actualIdx = bucketOf(g.reviews);
  const elapsedMs = Date.now() - (state.question_start_time || Date.now());
  const sc = computeScore(idx, actualIdx, elapsedMs, state.session_combo);
  state.picked = idx;
  state.last_score_breakdown = sc;     // tplRevealedLower 用到
  state.session_combo = sc.comboAfter;

  // 全場 streak 紀錄(穩定保留,跨多場累積)
  state.streak = sc.base >= 50 ? state.streak + 1 : 0;
  state.best = Math.max(state.best, state.streak);

  state.session_score += sc.final;
  state.session_picks += 1;
  if (sc.base === 100) state.session_perfects += 1;
  else if (sc.base === 50) state.session_nears += 1;
  else state.session_misses += 1;

  storage.appendHistory({
    ts: Math.floor(Date.now() / 1000),
    appid: g.appid,
    name: gameLocalized(g, state.lang).name || '',
    picked: idx,
    actual_bucket: actualIdx,
    actual_reviews: g.reviews | 0,
    score: sc.final,
  });
  state.hist_total += 1;
  state.hist_score_sum += sc.final;

  // 本場紀錄,結算頁要列出來連到 Steam 商店頁
  state.session_games.push({
    appid: g.appid,
    name_en: (g.en && g.en.name) || '',
    name_tc: (g.tc && g.tc.name) || '',
    reviews: g.reviews | 0,
    bucket: actualIdx,
    picked: idx,
    score: sc.final,
    base: sc.base,
    bonus: sc.bonus,
    multiplier: sc.multiplier,
    elapsed_ms: elapsedMs,
  });

  setPhase('revealed');

  // 揭曉音效(用 base 不是 final,音效仍依命中等級判定)
  requestAnimationFrame(() => playSFX(sc.base));
}

function onClickEndRun() {
  if (state.phase !== 'playing' || !isEndless()) return;
  // 玩家主動結束 endless,直接觸發 ended(同 timer onExpire 的視覺特效)
  document.body.classList.remove('staging');
  triggerTimeUpFx(state.lang === 'EN' ? 'RUN ENDED' : '結束本場', () => setPhase('ended'));
}

function onClickAgain() {
  state.session_start_time = 0;
  state.session_score = 0;
  state.session_picks = 0;
  state.session_perfects = 0;
  state.session_nears = 0;
  state.session_misses = 0;
  state.session_combo = 0;
  state.session_games = [];
  state.game = null;
  state.picked = null;
  applyAccent(null);    // 重置 game accent
  if (stopTimerFn) { stopTimerFn(); stopTimerFn = null; }
  setPhase('idle');
}

// ---------- timer 啟動/管理 ----------
function ensureTimerRunning() {
  // endless 模式不啟動 timer
  if (isEndless()) return;
  if (stopTimerFn) return;
  const container = document.getElementById('timer-widget');
  stopTimerFn = startTimer({
    container,
    getStartTime: () => state.session_start_time,
    getScore:     () => state.session_score,
    getPhase:     () => state.phase,
    getTimeLimit: () => currentTimeLimit(),
    getLabel:      () => t(state.lang, 'time_left'),
    getScoreLabel: () => t(state.lang, 'session_score'),
    onExpire: () => {
      // 不論 playing 或 revealed,時間到立刻播全螢幕「TIME UP」紅幕 + 警報音,
      // 1.5 秒後自動切到結算 phase
      if (state.phase === 'ended') return;
      triggerTimeUpFx('TIME UP', () => setPhase('ended'));
    },
    // 倒數音效分三階段:
    //   30s..16s:時鐘秒針(高頻 click)
    //   15s..6s :心跳低頻 thump
    //    5s..1s :加重雙聲咚-咚(intensity 1.5 觸發 sub-bass 後音)
    onTick: (sec) => {
      if (sec >= 16) playClockSFX();
      else if (sec >= 6) playTickSFX(1.0);
      else playTickSFX(1.5);
    },
  });
}

// ---------- phase 切換 ----------
function setPhase(p) {
  state.phase = p;
  if (p === 'ended') {
    // 第一次進 ended 時計算 record + 寫【本機】排行榜,後續重渲染(如語言切換)不會再寫
    state.ended_is_record = state.session_score > state.session_best;
    if (state.ended_is_record) {
      state.session_best = state.session_score;
      storage.saveBest(state.session_best);
    }
    if (state.session_picks > 0) {
      state.ended_just_added_ts = Math.floor(Date.now() / 1000);
      storage.appendLeaderboard({
        score: state.session_score | 0,
        ts: state.ended_just_added_ts,
        picks: state.session_picks,
        perfects: state.session_perfects,
        nears: state.session_nears,
        misses: state.session_misses,
      });
    }
    // 全球排行榜也撈一次(non-blocking;UI 先顯示 loading)
    if (LEADERBOARD_API) fetchGlobalLb();
    if (stopTimerFn) { stopTimerFn(); stopTimerFn = null; }
  }
  if (p === 'idle') {
    state.ended_is_record = false;
    state.ended_just_added_ts = 0;
    state.lb_my_global_ts = 0;
    state.lb_my_global_rank = 0;
    state.lb_submitted = false;
    state.lb_submit_state = 'idle';
    state.lb_submit_error = '';
    if (stopTimerFn) { stopTimerFn(); stopTimerFn = null; }
  }
  render();
}

// ---------- 全域:鍵盤快捷鍵 ----------
function setupKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    // 不要攔截輸入框中的鍵入
    const tag = (e.target && e.target.tagName) || '';
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    if (inTransition) return;

    if (state.phase === 'playing') {
      const idx = ['a', 'b', 'c', 'd'].indexOf(e.key.toLowerCase());
      if (idx >= 0 && idx < BUCKETS.length) {
        e.preventDefault();
        // 視覺上 ping 一下對應 bucket 按鈕
        const btn = document.querySelector(`.bk-btn[data-bucket="${idx}"]`);
        if (btn) btn.classList.add('cta-clicked');
        playPressSFX();
        onClickBucket(idx);
      }
    } else if (state.phase === 'revealed') {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        const btn = document.getElementById('btn-next');
        if (btn) { btn.classList.add('cta-clicked'); playPressSFX(); btn.click(); }
      }
    } else if (state.phase === 'idle') {
      // T = timed, E = endless, Enter/Space = 上次選的模式(預設 timed)
      const k = e.key.toLowerCase();
      let mode = null;
      if (k === 't') mode = 'timed';
      else if (k === 'e') mode = 'endless';
      else if (e.key === 'Enter' || e.key === ' ') mode = MODES[state.mode] ? state.mode : 'timed';
      if (mode) {
        e.preventDefault();
        const card = document.querySelector(`.cta-card[data-mode="${mode}"]`);
        if (card) { card.classList.add('cta-clicked'); playPressSFX(); card.click(); }
      }
    } else if (state.phase === 'ended') {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        const btn = document.getElementById('btn-again');
        if (btn) { btn.classList.add('cta-clicked'); playPressSFX(); btn.click(); }
      }
    }
  });
}

// ---------- 全域:click flash + hover SFX + press SFX ----------
function setupButtonFx() {
  // hover SFX(用 mouseover + dataset 旗標去重,避免在按鈕內部移動連發)
  document.addEventListener('mouseover', (e) => {
    const btn = e.target.closest && e.target.closest('button');
    if (!btn || btn.disabled) return;
    if (btn.dataset.hovered === '1') return;
    btn.dataset.hovered = '1';
    playHoverSFX();
  });
  document.addEventListener('mouseout', (e) => {
    const btn = e.target.closest && e.target.closest('button');
    if (!btn) return;
    // relatedTarget 還在 btn 內 = 沒真離開
    if (btn.contains(e.relatedTarget)) return;
    delete btn.dataset.hovered;
  });

  // mousedown:press SFX + click flash
  document.addEventListener('mousedown', (e) => {
    const btn = e.target.closest && e.target.closest('button');
    if (!btn || btn.disabled) return;
    playPressSFX();
    if (btn.classList.contains('btn')) btn.classList.add('cta-clicked');
  }, true);
}

// ---------- 語言切換 ----------
function setupLangSwitch() {
  const sw = document.getElementById('lang-switch');
  sw.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-lang]');
    if (!btn) return;
    const newLang = btn.dataset.lang;
    if (newLang === state.lang) return;
    state.lang = newLang;
    storage.saveLang(newLang);
    applyLang();
    // 轉場中不要插 render(會打斷淡入淡出);其他狀態下重 render 動態字串
    if (state.phase !== 'boot' && !inTransition) render();
  });
}

// ---------- boot ----------
async function boot() {
  try {
    state.lang = storage.loadLang();
    state.mode = storage.loadMode();
    state.session_best = storage.loadBest();
    state.player_name = storage.loadName();
    rebuildHistStats();
    applyLang();
    updateHUD();

    // 顯示 boot loader 並開始抓資料
    setPhase('boot');
    setupButtonFx();
    setupLangSwitch();
    setupKeyboardShortcuts();

    // 背景特效 + BGM / SFX widgets
    mountParticles();
    const audioContainer = document.getElementById('bgm-widget');
    mountBGM(audioContainer);
    mountSfxControls(audioContainer);

    // config 跟 pool 平行載(loadConfig 內部 try/catch,不會 throw;loadPool 失敗直接退出)
    try {
      await Promise.all([loadConfig(), loadPool()]);
    } catch (e) {
      console.error('boot: load failed', e);
      view().innerHTML = tplError('Failed to load game data: ' + (e.message || e));
      return;
    }

    // 進入 idle
    setPhase('idle');
  } catch (e) {
    // 同步 boot 階段任何錯誤(state 初始化 / setPhase / module mount)→ 顯示在 view
    console.error('boot: fatal', e);
    const v = document.getElementById('view');
    if (v) {
      v.innerHTML = `
        <div class="hero fade-in">
          <div class="icon" style="color:var(--red)">⚠</div>
          <h2 class="hero-status" style="color:var(--red)">&gt; BOOT ERROR</h2>
          <p style="color:#ccc">${escapeHtml(String(e.message || e))}</p>
          <p style="color:#888;font-size:11px;">F12 看 console 拿完整 stack trace</p>
        </div>
      `;
    }
  }
}

// :has() 不支援的瀏覽器 → 加 .no-has,讓 CSS fallback 跳過進場動畫
if (!CSS.supports || !CSS.supports('selector(:has(*))')) {
  document.body.classList.add('no-has');
}

// 全域錯誤 → 直接寫到 view,任何被吞的 error 都會浮出來
function dumpErr(label, err) {
  console.error(label, err);
  const v = document.getElementById('view');
  if (!v) return;
  const msg = err && (err.stack || err.message) || String(err);
  v.innerHTML = `
    <div class="hero fade-in" style="border-left-color:#d32f2f">
      <div class="icon" style="color:#d32f2f">⚠</div>
      <h2 class="hero-status" style="color:#d32f2f">&gt; ${label}</h2>
      <pre style="color:#ccc;font-size:11px;white-space:pre-wrap;text-align:left;max-width:600px;margin:10px auto;background:rgba(0,0,0,0.5);padding:12px;border:1px solid #333">${msg.replace(/[<>&]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))}</pre>
    </div>
  `;
}
window.addEventListener('error', (e) => dumpErr('UNCAUGHT ERROR', e.error || e.message));
window.addEventListener('unhandledrejection', (e) => dumpErr('UNHANDLED REJECTION', e.reason));

// 進到 boot 之前就先在 view 留個記號,如果這個記號永遠看得到,代表 JS 載入了但 boot() 沒被呼叫
(() => {
  const v = document.getElementById('view');
  if (v) v.innerHTML = '<div style="color:#4caf50;padding:30px;font-family:monospace;font-size:13px;letter-spacing:1px;">[JS] loaded, calling boot()...</div>';
})();

boot();
