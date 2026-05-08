"""Steam 評論猜猜看 — apartment-style terminal split layout."""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components

CACHE_DIR = Path.home() / ".config" / "steam-guesser"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = CACHE_DIR / "history.json"
POOL_FILE = CACHE_DIR / "pool.json"
BEST_FILE = CACHE_DIR / "best.json"

MIN_REVIEWS = 10
MAX_REVIEWS = 50_000  # 對齊 steamle.com 的 D 桶上限
TIME_LIMIT = 300  # 計時模式秒數(5 分鐘)

LANG_CODES = {"繁中": "tchinese", "EN": "english"}

BUCKETS = [
    (10,       100,             "10–100"),
    (100,      1_000,           "100–1K"),
    (1_000,    10_000,          "1K–10K"),
    (10_000,   50_000,          "10K–50K"),
]
LETTERS = ["A", "B", "C", "D"]

SCORE_TABLE = {0: 100, 1: 50}

T = {
    "繁中": {
        "mode_casual":    "悠閒模式",
        "mode_timed":     "計時挑戰",
        "time_attack":    "5 分鐘衝高分",
        "time_left":      "剩餘",
        "ended_title":    "TIME UP",
        "session_score":  "本場分數",
        "session_picks":  "答題數",
        "perfects":       "完美",
        "near_hits":      "相鄰",
        "misses":         "失準",
        "personal_best":  "個人最佳",
        "new_record":     "新紀錄!",
        "play_again":     "再玩一次",
        "view_results":   "結算",
        "title":          "STEAM 評論猜猜看",
        "tagline":        "看畫面，猜這款遊戲的評論落在哪個區間",
        "rules":          "完美 100　·　相鄰 50",
        "start":          "開始遊戲",
        "next":           "下一題",
        "query":          "評論區間 = ?",
        "select_prompt":  "選擇評論區間",
        "load1":          "連線 Steam 商店",
        "load2":          "載入遊戲資料",
        "comp1":          "比對你的選擇",
        "comp2":          "計算分數",
        "actual":         "實際評論",
        "correct":        "正解區間",
        "your_pick":      "你的選擇",
        "delta":          "差距",
        "rate_limit":     "Steam 暫時限流，請稍等幾秒",
        "genre":          "類型",
        "release":        "發售",
        "price":          "價格",
        "free":           "免費",
        "dev":            "開發",
        "streak":         "連勝",
        "best":           "最高",
        "runs":           "已玩",
        "avg":            "平均",
        "history":        "歷史紀錄",
        "lbl_perfect":    "完美命中",
        "lbl_adjacent":   "相鄰區間",
        "lbl_miss":       "錯過了",
        "scanning":       "掃描目標",
        "metadata":       "資料",
        "ready":          "系統就緒",
        "intro":          "看畫面 · 看影片 · 看評價區間\n選一個區間就送出",
        "analysis_done":  "分析完成",
        "lang_label":     "語言",
        "tbl_target":     "遊戲",
        "tbl_pick":       "你選",
        "tbl_actual":     "正解",
        "tbl_reviews":    "評論數",
        "tbl_score":      "分數",
    },
    "EN": {
        "mode_casual":    "CASUAL",
        "mode_timed":     "TIME ATTACK",
        "time_attack":    "5min — go for the high score",
        "time_left":      "TIME",
        "ended_title":    "TIME UP",
        "session_score":  "SESSION_SCORE",
        "session_picks":  "ANSWERED",
        "perfects":       "PERFECT",
        "near_hits":      "NEAR",
        "misses":         "MISS",
        "personal_best":  "PERSONAL_BEST",
        "new_record":     "NEW RECORD!",
        "play_again":     "PLAY AGAIN",
        "view_results":   "VIEW RESULTS",
        "title":          "STEAM REVIEW GUESSER",
        "tagline":        "Look at the visuals — guess the review bucket",
        "rules":          "PERFECT 100　·　ADJACENT 50",
        "start":          "Start",
        "next":           "Next",
        "query":          "review_count_bucket = ?",
        "select_prompt":  "SELECT REVIEW BUCKET",
        "load1":          "Connecting to Steam",
        "load2":          "Loading target data",
        "comp1":          "Comparing your pick",
        "comp2":          "Computing score",
        "actual":         "ACTUAL_REVIEWS",
        "correct":        "CORRECT_BUCKET",
        "your_pick":      "YOUR_PICK",
        "delta":          "DELTA",
        "rate_limit":     "Steam rate-limited — retry in a few seconds",
        "genre":          "GENRE",
        "release":        "RELEASE",
        "price":          "PRICE",
        "free":           "FREE",
        "dev":            "DEV",
        "streak":         "STREAK",
        "best":           "MAX",
        "runs":           "RUNS",
        "avg":            "AVG",
        "history":        "LOG_ARCHIVE",
        "lbl_perfect":    "PERFECT_MATCH",
        "lbl_adjacent":   "ADJACENT",
        "lbl_miss":       "MISS",
        "scanning":       "SCANNING_TARGET",
        "metadata":       "METADATA",
        "ready":          "SYSTEM READY",
        "intro":          "scan the trailer, screenshots, metadata\npick a bucket — that's your answer",
        "analysis_done":  "ANALYSIS_COMPLETE",
        "lang_label":     "LANG",
        "tbl_target":     "TARGET",
        "tbl_pick":       "PICK",
        "tbl_actual":     "ACTUAL",
        "tbl_reviews":    "REVIEWS",
        "tbl_score":      "+SCORE",
    },
}


# ---------- 資料 ----------

POOL_PAGES = 10  # 10 頁 ≈ 10000 款,確保 A 桶(10-100 評論)有足夠小品可選


def _load_cached_pool() -> list[dict] | None:
    """讀現有 pool.json,任何能用的都回傳,不行就 None"""
    if not POOL_FILE.exists():
        return None
    try:
        cached = json.loads(POOL_FILE.read_text(encoding="utf-8"))
        if cached and isinstance(cached, list):
            return cached
    except Exception:
        pass
    return None


def _log_pool_distribution(pool: list[dict]) -> None:
    """印出每桶有多少款遊戲 → Streamlit log,用來確認 A 桶不空"""
    counts = [0] * len(BUCKETS)
    in_range = 0
    for p in pool:
        n = p.get("reviews", 0)
        if MIN_REVIEWS <= n <= MAX_REVIEWS:
            in_range += 1
            counts[bucket_of(n)] += 1
    breakdown = " · ".join(
        f"{LETTERS[i]}({BUCKETS[i][2]}): {counts[i]}"
        for i in range(len(BUCKETS))
    )
    print(f"[pool] total={len(pool)} in_range={in_range} | {breakdown}", flush=True)


@st.cache_data(ttl=86400, show_spinner=False)
def load_pool() -> list[dict]:
    cached = _load_cached_pool()
    # 已有夠大的新格式 cache 就直接用
    if cached and "reviews" in cached[0] and len(cached) >= 8000:
        _log_pool_distribution(cached)
        return cached

    # 重抓多頁
    pool: list[dict] = []
    seen_ids: set[int] = set()
    for page in range(POOL_PAGES):
        try:
            r = requests.get(
                "https://steamspy.com/api.php",
                params={"request": "all", "page": page},
                timeout=20,
            )
            if r.status_code != 200:
                continue
            for k, v in r.json().items():
                if not v.get("name"):
                    continue
                appid = int(k)
                if appid in seen_ids:
                    continue
                seen_ids.add(appid)
                pool.append({
                    "appid": appid,
                    "name": v["name"],
                    "reviews": int(v.get("positive", 0)) + int(v.get("negative", 0)),
                })
            time.sleep(0.3)
        except Exception:
            continue

    if pool:
        POOL_FILE.write_text(json.dumps(pool, ensure_ascii=False), encoding="utf-8")
        _log_pool_distribution(pool)
        return pool

    # 重抓全失敗 → 用任何舊 cache 撐住,寧可玩到熱門也不要無法開始
    if cached:
        return cached
    return []


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_game(appid: int, lang: str) -> tuple[dict | None, int | None]:
    try:
        d = requests.get(
            "https://store.steampowered.com/api/appdetails",
            params={"appids": appid, "l": lang},
            timeout=20,
        ).json()
        node = d.get(str(appid), {})
        details = node["data"] if node.get("success") else None

        r = requests.get(
            f"https://store.steampowered.com/appreviews/{appid}",
            params={
                "json": 1,
                "num_per_page": 0,
                "purchase_type": "all",
                "language": "all",
            },
            headers={"User-Agent": "steam-guesser/0.6"},
            timeout=20,
        ).json()
        return details, r.get("query_summary", {}).get("total_reviews")
    except Exception:
        return None, None


def find_target(pool: list[dict], exclude: set[int], lang: str) -> dict | None:
    # 把 pool 按桶分群(用 steamspy 評論數預估),然後隨機選桶 → 桶內隨機抽,
    # 確保每桶機率相等,避免熱門池讓 C/D 桶遊戲淹沒 A/B
    by_bucket: list[list[dict]] = [[] for _ in BUCKETS]
    for p in pool:
        n = p.get("reviews", 0)
        if MIN_REVIEWS <= n <= MAX_REVIEWS and p["appid"] not in exclude:
            by_bucket[bucket_of(n)].append(p)

    # fallback:舊 cache 沒 reviews 欄位 → 退回平攤抽
    if all(not b for b in by_bucket):
        flat = [p for p in pool if p["appid"] not in exclude]
        random.shuffle(flat)
        for pick in flat[:25]:
            details, reviews = fetch_game(pick["appid"], lang)
            if details and reviews and MIN_REVIEWS <= reviews <= MAX_REVIEWS:
                return {"appid": pick["appid"], "reviews": reviews}
            time.sleep(0.2)
        return None

    # 隨機決定桶順序;每桶試最多 8 次再換下一桶
    bucket_order = random.sample(range(len(BUCKETS)), len(BUCKETS))
    for b in bucket_order:
        candidates = by_bucket[b]
        if not candidates:
            continue
        random.shuffle(candidates)
        for pick in candidates[:8]:
            details, reviews = fetch_game(pick["appid"], lang)
            if details and reviews and MIN_REVIEWS <= reviews <= MAX_REVIEWS:
                return {"appid": pick["appid"], "reviews": reviews}
            time.sleep(0.2)
    return None


def hero_video_url(d: dict) -> str | None:
    movies = d.get("movies") or []
    if not movies:
        return None
    hl = next((m for m in movies if m.get("highlight")), movies[0])
    legacy = (hl.get("mp4") or {}).get("480") or (hl.get("webm") or {}).get("480")
    if legacy:
        return ("https:" + legacy) if legacy.startswith("//") else legacy
    mid = hl.get("id")
    if not mid:
        return None
    return f"https://video.akamai.steamstatic.com/store_trailers/{mid}/movie480.mp4"


def bucket_of(n: int) -> int:
    for i, (lo, hi, _) in enumerate(BUCKETS):
        if lo <= n < hi:
            return i
    return len(BUCKETS) - 1


def score_for(picked: int, actual: int) -> int:
    return SCORE_TABLE.get(abs(picked - actual), 0)


def load_best() -> int:
    if not BEST_FILE.exists():
        return 0
    try:
        return int(json.loads(BEST_FILE.read_text(encoding="utf-8")).get("best", 0))
    except Exception:
        return 0


def save_best(score: int) -> None:
    try:
        BEST_FILE.write_text(json.dumps({"best": int(score)}), encoding="utf-8")
    except Exception:
        pass


def load_history() -> list[dict]:
    """讀歷史紀錄。新格式是 JSONL(每行一個 entry,append-only);
    舊格式是 JSON array,自動偵測並就地遷移成 JSONL。"""
    if not HISTORY_FILE.exists():
        return []
    text = HISTORY_FILE.read_text(encoding="utf-8")
    if not text.strip():
        return []
    if text.lstrip().startswith("["):
        # 舊格式 → 遷移成 JSONL
        try:
            data = json.loads(text)
        except Exception:
            return []
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                for item in data:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
        except Exception:
            pass  # 寫不進就算了,後續 load 還是能用
        return data
    # JSONL 格式
    out = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def save_history(entry: dict) -> None:
    """JSONL append-only,O(1) 寫入,不再讀整個歷史檔。"""
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass  # 寫不進就靜默,session_state 還是會反映進度


def trailing_streak(hist: list[dict]) -> int:
    s = 0
    for h in reversed(hist):
        if h.get("score", 0) >= 50:
            s += 1
        else:
            break
    return s


def best_streak(hist: list[dict]) -> int:
    best = cur = 0
    for h in hist:
        if h.get("score", 0) >= 50:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


# ---------- UI ----------

st.set_page_config(page_title="Steam 評論猜猜看", page_icon="◉", layout="wide")


# ---------- 狀態 ----------

if "init" not in st.session_state:
    h0 = load_history()
    st.session_state.init = True
    st.session_state.lang = "EN"
    st.session_state.phase = "idle"
    st.session_state.game = None
    st.session_state.picked = None
    st.session_state.celebrated = False
    st.session_state.seen = set()
    st.session_state.streak = trailing_streak(h0)
    st.session_state.best = best_streak(h0)
    # HUD 統計值快取(避免每次 rerun 都讀 history.json 計算)
    st.session_state.hist_total = len(h0)
    st.session_state.hist_score_sum = sum(int(h.get("score", 0)) for h in h0)
    # time-attack mode state(永遠開,強制計時)
    st.session_state.session_start_time = 0.0
    st.session_state.session_score = 0
    st.session_state.session_picks = 0
    st.session_state.session_perfects = 0
    st.session_state.session_nears = 0
    st.session_state.session_misses = 0
    st.session_state.session_best = load_best()
    # 進場黑幕 flag:開始遊戲 / 下一題按下時設為 True,進入 playing 渲染後消費
    st.session_state.show_curtain = False


# ---------- CSS（語系決定深淺;cache 過,不在每次 rerun 重新格式化 800 行 CSS）----------


@st.cache_data(show_spinner=False)
def render_css(lang: str) -> str:
    if lang == "繁中":
        return CSS_TEMPLATE.format(
            BG_1="#000000", BG_2="#050507",
            PANEL="rgba(8,8,10,0.85)", PANEL_2="rgba(12,12,14,0.7)",
            TEXT="#9aa0a6", TEXT_BRIGHT="#e0e0e0",
            DIM="#525860",
            ACCENT="#4caf50", ACCENT_GLOW="rgba(76,175,80,0.45)",
        )
    return CSS_TEMPLATE.format(
        BG_1="#020203", BG_2="#0a0a0e",
        PANEL="rgba(15,15,18,0.85)", PANEL_2="rgba(18,18,22,0.7)",
        TEXT="#b0b0b0", TEXT_BRIGHT="#ffffff",
        DIM="#666",
        ACCENT="#4caf50", ACCENT_GLOW="rgba(76,175,80,0.55)",
    )


CSS_TEMPLATE = r"""
<style>
  :root {{
    --bg-1: {BG_1};
    --bg-2: {BG_2};
    --panel: {PANEL};
    --panel-2: {PANEL_2};
    --border: #1c1c20;
    --border-2: #2a2a30;
    --text: {TEXT};
    --text-bright: {TEXT_BRIGHT};
    --dim: {DIM};
    --dimmer: #333;
    --accent: {ACCENT};
    --accent-dim: #2e7d32;
    --accent-glow: {ACCENT_GLOW};
    --gold: #ffc83d;
    --warn: #ff9800;
    --red: #d32f2f;
    --info: #29b6f6;
  }}

  /* hide streamlit chrome */
  #MainMenu, footer, header[data-testid="stHeader"] {{ visibility: hidden; height: 0; }}
  .block-container {{ padding-top: 0.6rem; padding-bottom: 4rem; max-width: 1320px; }}

  /* monospace ONLY on body text + buttons + our markdown — leave icon fonts alone */
  html, body, .stApp,
  div[data-testid="stMarkdownContainer"],
  div[data-testid="stMarkdownContainer"] *,
  div[data-testid="stButton"] > button,
  div[data-testid="stRadio"] label,
  input, textarea {{
    font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", "Courier New", monospace !important;
  }}
  /* but Streamlit material icons keep their font */
  span[data-testid*="StyledIcon"], .material-icons, .material-symbols-outlined,
  [class*="MuiIcon"], svg {{
    font-family: 'Material Symbols Rounded', 'Material Icons' !important;
  }}

  .stApp {{
    background: var(--bg-1);
    color: var(--text);
    min-height: 100vh;
  }}

  /* CRT scanlines (subtle, 1px) + chromatic */
  .crt {{
    position: fixed; inset: 0;
    background:
      linear-gradient(rgba(18,16,16,0) 50%, rgba(0,0,0,0.18) 50%),
      linear-gradient(90deg, rgba(255,0,0,0.04), rgba(0,255,0,0.02), rgba(0,0,255,0.04));
    background-size: 100% 2px, 3px 100%;
    pointer-events: none;
    z-index: 9999;
    animation: crt-flicker 0.18s infinite;
  }}
  @keyframes crt-flicker {{
    0%,100% {{ opacity: 0.92; }}
    50%     {{ opacity: 0.86; }}
  }}
  /* vignette (apartment-like) */
  .vignette {{
    position: fixed; inset: 0;
    background: radial-gradient(ellipse at center, rgba(0,0,0,0) 45%, rgba(0,0,0,0.85) 100%);
    pointer-events: none;
    z-index: 9998;
  }}

  /* 黑幕：開始遊戲 / 下一題切換時短暫蓋住整個畫面,
     讓底下的空殼面板先就定位,再淡出做戲劇性 reveal */
  .curtain {{
    position: fixed; inset: 0;
    background: #000;
    pointer-events: none;
    z-index: 10000;
    animation: curtainFade 0.6s cubic-bezier(0.22, 1, 0.36, 1) forwards;
  }}
  @keyframes curtainFade {{
    0%   {{ opacity: 1; }}
    50%  {{ opacity: 1; }}
    100% {{ opacity: 0; }}
  }}

  /* HUD */
  .hud {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
    padding: 10px 16px;
    background: var(--panel);
    border: 1px solid var(--border);
    box-shadow: 0 5px 15px rgba(0,0,0,0.6);
    margin-bottom: 14px;
  }}
  .hud .brand {{
    display: flex; align-items: center; gap: 10px;
    font-size: 13px; font-weight: 700;
    color: var(--accent);
    text-shadow: 0 0 6px var(--accent-glow);
    letter-spacing: 1px;
  }}
  .hud .blink {{
    width: 7px; height: 7px;
    background: var(--accent);
    box-shadow: 0 0 8px var(--accent-glow);
    animation: blink-soft 1.5s ease-in-out infinite;
  }}
  @keyframes blink-soft {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.3; }} }}

  .hud .stats {{ display: flex; gap: 18px; flex-wrap: wrap; align-items: baseline; }}
  .hud .stat {{ display: flex; gap: 6px; align-items: baseline; font-size: 11px; color: var(--dim); letter-spacing: 1px; }}
  .hud .stat b {{ font-size: 15px; font-weight: 700; font-feature-settings: "tnum"; }}
  .stat-streak b {{ color: var(--warn);  text-shadow: 0 0 8px rgba(255,152,0,0.4); }}
  .stat-best   b {{ color: var(--gold);  text-shadow: 0 0 8px rgba(255,200,61,0.4); }}
  .stat-runs   b {{ color: var(--text-bright); }}
  .stat-avg    b {{ color: var(--info);  text-shadow: 0 0 8px rgba(41,182,246,0.4); }}

  /* prompt */
  .prompt {{
    color: var(--accent);
    text-shadow: 0 0 6px var(--accent-glow);
    font-size: 13px;
    margin: 12px 0 8px;
    letter-spacing: 1px;
  }}
  .prompt .arrow {{ color: var(--dim); margin-right: 6px; }}
  .prompt .accent {{ color: var(--text-bright); }}
  .caret {{
    display: inline-block;
    width: 8px; height: 14px;
    background: var(--accent);
    margin-left: 4px;
    vertical-align: middle;
    animation: caret-blink 0.8s steps(2) infinite;
    box-shadow: 0 0 6px var(--accent-glow);
  }}
  @keyframes caret-blink {{ 50% {{ opacity: 0; }} }}

  /* fade-in */
  .fade-in {{ animation: fadeUp 0.55s cubic-bezier(0.22, 1, 0.36, 1) both; }}
  @keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(16px); filter: blur(4px); }}
    to   {{ opacity: 1; transform: translateY(0);    filter: blur(0); }}
  }}

  /* typewriter (inline span) */
  .tw {{
    display: inline-block;
    overflow: hidden;
    white-space: nowrap;
    width: 0;
    vertical-align: bottom;
    border-right: 2px solid currentColor;
    animation: tw-go 0.7s steps(24) forwards, tw-caret 0.7s step-end 5;
  }}
  @keyframes tw-go    {{ to {{ width: 100%; }} }}
  @keyframes tw-caret {{ 50% {{ border-color: transparent; }} }}

  /* full-screen impact flash on reveal */
  .impact-flash {{
    position: fixed; inset: 0;
    pointer-events: none;
    z-index: 9999;
    opacity: 0;
    animation: impact-pulse 0.65s ease-out forwards;
  }}
  @keyframes impact-pulse {{
    0%   {{ opacity: 0; }}
    18%  {{ opacity: 0.55; }}
    100% {{ opacity: 0; }}
  }}
  .impact-100 {{ background: radial-gradient(ellipse at center, rgba(76,175,80,0.75) 0%, rgba(76,175,80,0) 65%); }}
  .impact-50  {{ background: radial-gradient(ellipse at center, rgba(255,200,61,0.65) 0%, rgba(255,200,61,0) 65%); }}
  .impact-0   {{ background: radial-gradient(ellipse at center, rgba(211,47,47,0.65) 0%, rgba(211,47,47,0) 65%); }}

  /* entrance animations — 只在黑幕存在時觸發,避免答題後重渲染又跑一次 */
  body:has(.curtain) .prompt {{ animation: slideInLeft 0.45s cubic-bezier(0.22, 1, 0.36, 1) both; }}
  @keyframes slideInLeft {{
    from {{ opacity: 0; transform: translateX(-12px); }}
    to   {{ opacity: 1; transform: translateX(0); }}
  }}
  /* prompt accent 基礎樣式 — 永遠都在,沒有 clip-path 時就直接顯示完整字 */
  .prompt .accent {{
    display: inline-block;
    white-space: nowrap;
  }}
  /* clip-path typewriter — 只在黑幕存在時觸發 */
  body:has(.curtain) .prompt .accent {{
    clip-path: inset(0 100% 0 0);
    animation: tw-clip 0.55s steps(14) 0.1s forwards;
  }}
  @keyframes tw-clip {{
    from {{ clip-path: inset(0 100% 0 0); }}
    to   {{ clip-path: inset(0 0     0 0); }}
  }}

  /* panel entry — 同樣只在黑幕存在時觸發 */
  body:has(.curtain) .panel-glow {{ animation: panelIn 0.5s cubic-bezier(0.22, 1, 0.36, 1) both; }}
  @keyframes panelIn {{
    from {{ opacity: 0; transform: translateY(20px); filter: blur(6px); }}
    to   {{ opacity: 1; transform: translateY(0);    filter: blur(0); }}
  }}

  /* metadata 進場(只在黑幕存在時觸發,答題後 revealed 重渲染不會再跑)
     標題/描述採打字機效果,等黑幕散開、媒體進場後才開始打字 */
  body:has(.curtain) .target-title {{
    clip-path: inset(0 100% 0 0);
    animation: tw-clip 0.75s steps(28) 1.05s forwards;
  }}
  body:has(.curtain) .target-desc {{
    clip-path: inset(0 100% 0 0);
    animation: tw-clip 1.0s steps(48) 1.25s forwards;
  }}
  body:has(.curtain) .meta .row {{ animation: fadeUp 0.55s cubic-bezier(0.22, 1, 0.36, 1) both; }}
  body:has(.curtain) .meta .row:nth-child(1) {{ animation-delay: 1.45s; }}
  body:has(.curtain) .meta .row:nth-child(2) {{ animation-delay: 1.58s; }}
  body:has(.curtain) .meta .row:nth-child(3) {{ animation-delay: 1.71s; }}
  body:has(.curtain) .meta .row:nth-child(4) {{ animation-delay: 1.84s; }}

  /* horizontal-row buttons (bucket strip): staggered fade-up */
  [data-testid="stHorizontalBlock"] [data-testid="stButton"] > button {{
    animation: btnIn 0.45s cubic-bezier(0.22, 1, 0.36, 1) both;
  }}
  [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(1) [data-testid="stButton"] > button {{ animation-delay: 0.05s; }}
  [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(2) [data-testid="stButton"] > button {{ animation-delay: 0.12s; }}
  [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(3) [data-testid="stButton"] > button {{ animation-delay: 0.19s; }}
  [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(4) [data-testid="stButton"] > button {{ animation-delay: 0.26s; }}
  [data-testid="stHorizontalBlock"] > [data-testid="column"]:nth-child(5) [data-testid="stButton"] > button {{ animation-delay: 0.33s; }}
  @keyframes btnIn {{
    from {{ opacity: 0; transform: translateY(12px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}

  /* primary button (start / next) — entrance + strong idle CTA pulse to draw the eye */
  div[data-testid="stButton"] > button[kind="primary"] {{
    animation: btnIn 0.5s cubic-bezier(0.22, 1, 0.36, 1) both,
               ctaPulse 1.6s ease-in-out 0.5s infinite;
  }}
  @keyframes ctaPulse {{
    0%, 100% {{
      box-shadow: 0 0 18px rgba(76,175,80,0.35),
                  0 0 0   rgba(76,175,80,0),
                  inset 0 0 12px rgba(76,175,80,0.15);
      transform: scale(1);
      filter: brightness(1);
      border-color: var(--accent);
    }}
    50%      {{
      box-shadow: 0 0 50px rgba(76,175,80,0.95),
                  0 0 110px rgba(76,175,80,0.45),
                  inset 0 0 36px rgba(76,175,80,0.55);
      transform: scale(1.018);
      filter: brightness(1.2);
      border-color: #6fff6f;
    }}
  }}

  /* expanding ring around primary button */
  div[data-testid="stButton"] > button[kind="primary"]::after {{
    content: '';
    position: absolute;
    inset: 0;
    border: 2px solid var(--accent);
    pointer-events: none;
    animation: ctaRing 1.6s ease-out 0.5s infinite;
  }}
  @keyframes ctaRing {{
    0%   {{ opacity: 0.7;  transform: scale(1);    border-width: 2px; }}
    80%  {{ opacity: 0.05; transform: scale(1.04); border-width: 1px; }}
    100% {{ opacity: 0;    transform: scale(1.05); border-width: 1px; }}
  }}

  div[data-testid="stButton"] > button[kind="primary"]:hover:not(:disabled) {{
    animation: none;
    transform: scale(1.01);
    box-shadow: 0 0 60px var(--accent-glow), 0 0 120px rgba(76,175,80,0.5), inset 0 0 28px rgba(76,175,80,0.4);
    filter: brightness(1.1);
  }}
  div[data-testid="stButton"] > button[kind="primary"]:hover:not(:disabled)::after {{ animation: none; opacity: 0; }}

  div[data-testid="stButton"] > button[kind="primary"]:active:not(:disabled) {{
    animation: none;
    transform: scale(0.96);
    box-shadow: 0 0 80px var(--accent-glow), inset 0 0 40px rgba(76,175,80,0.7);
    background: linear-gradient(90deg, #4a9a4a, #1f6a1f) !important;
    filter: brightness(1.3);
  }}

  /* click feedback — flash → dim "processing" state until page reruns
     (NO pointer-events:none — that would swallow the mouseup/click events) */
  div[data-testid="stButton"] > button[kind="primary"].cta-clicked,
  div[data-testid="stButton"] > button.cta-clicked {{
    animation: clickFx 0.7s cubic-bezier(0.22, 1, 0.36, 1) forwards !important;
  }}
  @keyframes clickFx {{
    0%   {{ transform: scale(0.93); filter: brightness(1.8); box-shadow: 0 0 120px rgba(76,175,80,1), inset 0 0 60px rgba(120,255,120,0.9); border-color: #ffffff; color: #ffffff; }}
    25%  {{ transform: scale(1.025); filter: brightness(1.4); box-shadow: 0 0 80px var(--accent-glow), inset 0 0 40px rgba(76,175,80,0.6); }}
    100% {{ transform: scale(0.985); filter: brightness(0.5) saturate(0.6); box-shadow: 0 0 10px rgba(76,175,80,0.25), inset 0 0 18px rgba(0,0,0,0.55); border-color: rgba(76,175,80,0.3); color: rgba(76,175,80,0.55); opacity: 0.55; }}
  }}

  /* chip strip entry */
  @keyframes chipIn {{
    from {{ opacity: 0; transform: translateY(8px) scale(0.85); }}
    to   {{ opacity: 1; transform: translateY(0)  scale(1); }}
  }}

  /* panel */
  .panel {{
    background: var(--panel-2);
    border: 1px solid var(--border);
    padding: 14px 16px;
    box-shadow: inset 0 0 30px rgba(0,0,0,0.5);
  }}
  .panel-glow {{ border-left: 3px solid var(--accent); }}

  /* media base — 邊框與濾鏡永遠都在 */
  div[data-testid="stImage"] img,
  div[data-testid="stVideo"] video {{
    border: 1px solid var(--border-2);
    filter: brightness(0.9) contrast(1.05);
  }}
  /* media 進場 — 只在黑幕在 DOM 中時觸發,延後 0.7s 讓黑幕先散開,再位移 + 淡入 */
  body:has(.curtain) div[data-testid="stImage"] img,
  body:has(.curtain) div[data-testid="stVideo"] video {{
    animation: imgIn 0.85s cubic-bezier(0.22, 1, 0.36, 1) 0.7s both;
  }}
  @keyframes imgIn {{
    from {{ opacity: 0; filter: blur(14px) brightness(0.4); transform: translateY(36px) scale(1.04); }}
    to   {{ opacity: 1; filter: blur(0)    brightness(0.9); transform: translateY(0)    scale(1); }}
  }}

  /* metadata */
  .target-title {{
    font-size: 22px; font-weight: 800;
    color: var(--text-bright);
    text-shadow: 0 0 6px rgba(255,255,255,0.1);
    margin: 4px 0 6px;
    line-height: 1.2;
    word-break: break-word;
  }}
  .target-desc {{
    color: #888;
    font-size: 13px; line-height: 1.7;
    margin: 6px 0 14px;
  }}
  .meta {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px;
    font-size: 13px;
  }}
  .meta .row {{ display: flex; gap: 10px; align-items: baseline; }}
  .meta .k {{ color: var(--dim); font-weight: 700; min-width: 56px; letter-spacing: 1px; }}
  .meta .sep {{ color: var(--dimmer); }}
  .meta .v {{ color: var(--text-bright); font-weight: 500; }}

  /* buttons (apartment-style) */
  div[data-testid="stButton"] > button {{
    width: 100%;
    background: linear-gradient(90deg, #111, #0a0a0a);
    color: #ccc;
    border: 1px solid var(--border-2);
    border-radius: 0;
    padding: 14px 18px;
    text-align: left;
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.5px;
    cursor: pointer;
    position: relative;
    overflow: hidden;
    transition: all 0.15s ease;
  }}
  div[data-testid="stButton"] > button::before {{
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 4px; height: 100%;
    background: var(--border-2);
    transition: all 0.18s;
  }}
  div[data-testid="stButton"] > button:hover:not(:disabled) {{
    background: #1a1a1a;
    color: #fff;
    padding-left: 28px;
    border-color: #555;
    text-shadow: 0 0 6px rgba(255,255,255,0.4);
  }}
  div[data-testid="stButton"] > button:hover:not(:disabled)::before {{
    background: var(--accent);
    width: 6px;
    box-shadow: 0 0 12px var(--accent-glow);
  }}
  div[data-testid="stButton"] > button:active:not(:disabled) {{
    transform: scale(0.99);
    background: #222;
  }}

  /* primary (start / next) — center, bigger, glow */
  div[data-testid="stButton"] > button[kind="primary"] {{
    background: linear-gradient(90deg, #1a3a1a, #0a1a0a);
    color: var(--accent);
    border: 1px solid var(--accent);
    text-align: center;
    text-shadow: 0 0 8px var(--accent-glow);
    font-weight: 700;
    letter-spacing: 2px;
    padding: 14px 24px;
  }}
  div[data-testid="stButton"] > button[kind="primary"]::before {{ background: var(--accent); width: 4px; box-shadow: 0 0 10px var(--accent-glow); }}
  div[data-testid="stButton"] > button[kind="primary"]:hover:not(:disabled) {{
    background: linear-gradient(90deg, #265a26, #0e2a0e);
    color: #fff;
    padding-left: 24px;
    box-shadow: 0 0 22px var(--accent-glow), inset 0 0 14px rgba(76,175,80,0.2);
  }}

  /* radio (lang) */
  div[data-testid="stRadio"] > div {{ background: transparent; gap: 8px; }}
  div[data-testid="stRadio"] label {{
    background: #181818 !important;
    border: 1px solid #6a6a6a !important;
    border-radius: 0 !important;
    padding: 10px 22px !important;
    font-size: 14px !important;
    font-weight: 700 !important;
    color: #ffffff !important;
    cursor: pointer;
    transition: all 0.2s;
    letter-spacing: 2px;
  }}
  div[data-testid="stRadio"] label * {{
    color: #ffffff !important;
  }}
  div[data-testid="stRadio"] label:hover {{
    background: #2a2a2a !important;
    border-color: #999 !important;
  }}
  div[data-testid="stRadio"] label:has(input:checked) {{
    background: linear-gradient(90deg, #4caf50, #1f6a1f) !important;
    border-color: #6fff6f !important;
    border-width: 2px !important;
    color: #ffffff !important;
    box-shadow: 0 0 28px var(--accent-glow), inset 0 0 18px rgba(255,255,255,0.15);
    text-shadow: 0 0 10px rgba(255,255,255,0.7);
    opacity: 1;
    filter: none;
  }}

  /* typewriter */
  .loader {{ text-align: center; padding: 50px 14px; }}
  .loader-line {{
    display: inline-block;
    overflow: hidden;
    white-space: nowrap;
    font-size: 16px;
    color: var(--accent);
    border-right: 2px solid var(--accent);
    width: 0;
    margin: 0 auto;
    text-shadow: 0 0 6px var(--accent-glow);
    animation: typing 0.85s steps(22) forwards, caret 0.7s step-end infinite;
  }}
  .loader .l1 {{ animation-delay: 0.05s, 0s; }}
  .loader .l2 {{ animation-delay: 0.95s, 0.95s; }}
  .loader .row {{ display: block; height: 26px; }}
  @keyframes typing {{ to {{ width: 100%; }} }}
  @keyframes caret  {{ 50% {{ border-color: transparent; }} }}
  .dots {{ margin-top: 18px; display: inline-flex; gap: 8px; }}
  .dots span {{
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 8px var(--accent-glow);
    animation: bounce 1.2s ease-in-out infinite;
  }}
  .dots span:nth-child(2) {{ animation-delay: 0.15s; }}
  .dots span:nth-child(3) {{ animation-delay: 0.30s; }}
  @keyframes bounce {{
    0%, 80%, 100% {{ transform: translateY(0);    opacity: 0.45; }}
    40%           {{ transform: translateY(-9px); opacity: 1; }}
  }}

  /* indeterminate progress bar */
  .progress-bar {{
    position: relative;
    width: 100%;
    max-width: 320px;
    height: 3px;
    background: rgba(76,175,80,0.12);
    border: 1px solid rgba(76,175,80,0.25);
    overflow: hidden;
    margin: 18px auto 0;
  }}
  .progress-bar::after {{
    content: '';
    position: absolute;
    top: 0; bottom: 0;
    left: -40%; width: 40%;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
    box-shadow: 0 0 12px var(--accent-glow);
    animation: prog-slide 1.3s ease-in-out infinite;
  }}
  @keyframes prog-slide {{
    0%   {{ left: -40%; }}
    100% {{ left: 100%; }}
  }}

  /* score reveal */
  .score {{
    text-align: center;
    padding: 18px 14px;
    border: 1px solid var(--border-2);
    background: var(--panel-2);
    box-shadow: inset 0 0 30px rgba(0,0,0,0.5);
    margin-bottom: 12px;
    animation: pop 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) both;
  }}
  @keyframes pop {{
    0%   {{ opacity: 0; transform: translateY(-12px) scale(0.93); }}
    100% {{ opacity: 1; transform: translateY(0)      scale(1); }}
  }}
  .score .num {{ font-size: 70px; font-weight: 900; line-height: 1; letter-spacing: -1px; font-feature-settings: "tnum"; }}
  .score .lbl {{ font-size: 12px; letter-spacing: 3px; margin-top: 6px; font-weight: 700; }}
  .score-100 .num {{ color: var(--accent); text-shadow: 0 0 28px var(--accent-glow); }}
  .score-100 .lbl {{ color: var(--accent); }}
  .score-50  .num {{ color: var(--gold);  text-shadow: 0 0 28px rgba(255,200,61,0.7); }}
  .score-50  .lbl {{ color: var(--gold); }}
  .score-0   .num {{ color: var(--red);   text-shadow: 0 0 22px rgba(211,47,47,0.55); transform: skewX(-3deg); }}
  .score-0   .lbl {{ color: var(--red); }}

  /* 角落署名 */
  .signature {{
    position: fixed;
    bottom: 14px; left: 18px;
    z-index: 50;
    font-family: 'JetBrains Mono','Courier New',monospace;
    font-size: 11px;
    letter-spacing: 2px;
    color: var(--dim);
    background: rgba(8,8,10,0.8);
    border: 1px solid var(--border-2);
    border-left: 3px solid var(--accent);
    padding: 6px 14px;
    display: inline-flex;
    gap: 8px;
    align-items: center;
    backdrop-filter: blur(6px);
    -webkit-backdrop-filter: blur(6px);
    transition: all 0.28s cubic-bezier(0.22, 1, 0.36, 1);
    box-shadow: 0 0 14px rgba(0,0,0,0.5);
    user-select: none;
    pointer-events: auto;
  }}
  .signature:hover {{
    border-left-width: 5px;
    box-shadow: 0 0 28px var(--accent-glow), inset 0 0 16px rgba(76,175,80,0.15);
    background: rgba(8,30,8,0.88);
    color: #fff;
    transform: translateY(-1px);
  }}
  .signature .sig-prefix {{ color: var(--dim); opacity: 0.6; }}
  .signature .sig-by {{ color: var(--dim); }}
  .signature:hover .sig-by {{ color: #ddd; }}
  .signature .sig-name {{
    color: var(--accent);
    font-weight: 800;
    letter-spacing: 4px;
    text-shadow: 0 0 8px var(--accent-glow);
    animation: sigGlitch 5s infinite;
    display: inline-block;
  }}
  .signature:hover .sig-name {{
    color: #fff;
    text-shadow: 0 0 14px var(--accent-glow), 0 0 28px rgba(76,175,80,0.5);
    animation: sigGlitch 1.6s infinite;
  }}
  @keyframes sigGlitch {{
    0%, 88%, 100% {{ transform: translate(0); text-shadow: 0 0 8px var(--accent-glow); }}
    89% {{ transform: translate(-1px, 0); text-shadow: -2px 0 #ff3088, 2px 0 #30d6ff, 0 0 8px var(--accent-glow); }}
    91% {{ transform: translate(1px, 0); text-shadow:  2px 0 #ff3088, -2px 0 #30d6ff, 0 0 8px var(--accent-glow); }}
    93% {{ transform: translate(-2px, 1px); text-shadow: -1px 1px #ff3088, 1px -1px #30d6ff, 0 0 8px var(--accent-glow); }}
    95% {{ transform: translate(0, -1px); text-shadow: 0 0 12px var(--accent-glow); }}
    97% {{ transform: translate(1px, 0); }}
  }}
  .signature .sig-cursor {{
    display: inline-block;
    width: 7px; height: 13px;
    background: var(--accent);
    margin-left: -2px;
    box-shadow: 0 0 6px var(--accent-glow);
    animation: sigCursor 0.85s steps(2) infinite;
  }}
  @keyframes sigCursor {{ 50% {{ opacity: 0; }} }}

  /* ended phase (time-attack 結算) */
  .ended-wrap {{
    text-align: center;
    padding: 32px 18px 24px;
    border: 1px solid var(--accent);
    background: linear-gradient(180deg, rgba(0,40,0,0.3), rgba(0,15,0,0.3));
    box-shadow: 0 0 40px var(--accent-glow), inset 0 0 40px rgba(76,175,80,0.15);
    margin: 18px 0;
  }}
  .ended-tag {{
    font-size: 16px;
    letter-spacing: 8px;
    color: var(--red);
    text-shadow: 0 0 14px rgba(211,47,47,0.85);
    font-weight: 900;
    margin-bottom: 8px;
    animation: blink 0.5s steps(2) 4;
  }}
  @keyframes blink {{ 50% {{ opacity: 0.3; }} }}
  .ended-record {{
    color: var(--gold);
    letter-spacing: 6px;
    font-size: 14px;
    font-weight: 800;
    text-shadow: 0 0 14px rgba(255,200,61,0.9);
    margin: 6px 0;
    animation: recordPulse 1s ease-in-out infinite;
  }}
  @keyframes recordPulse {{
    0%, 100% {{ opacity: 0.85; transform: scale(1); }}
    50%      {{ opacity: 1;    transform: scale(1.05); }}
  }}
  .ended-score-num {{
    font-size: 96px; font-weight: 900;
    color: var(--accent);
    text-shadow: 0 0 36px var(--accent-glow);
    line-height: 1;
    margin: 12px 0 4px;
    font-feature-settings: "tnum";
  }}
  .ended-score-lbl {{
    color: var(--dim);
    letter-spacing: 4px;
    font-size: 12px;
    font-weight: 700;
  }}

  /* verdict banner */
  .verdict {{
    margin: 0 0 14px;
    padding: 14px 18px;
    border: 2px solid;
    position: relative;
    overflow: hidden;
    text-align: center;
    letter-spacing: 5px;
    font-weight: 900;
    font-size: 22px;
    font-family: 'JetBrains Mono','Courier New',monospace;
  }}
  .verdict::before {{
    content: '';
    position: absolute; left: -35%; top: 0; bottom: 0; width: 35%;
    background: linear-gradient(90deg, transparent, currentColor, transparent);
    opacity: 0.32;
    animation: v-scan 1.1s ease-out 0.25s both;
    pointer-events: none;
  }}
  @keyframes v-in {{
    0%   {{ opacity: 0; transform: translateY(-12px) scale(0.94); filter: blur(6px); }}
    100% {{ opacity: 1; transform: translateY(0)     scale(1);    filter: blur(0); }}
  }}
  @keyframes v-scan {{ to {{ left: 100%; }} }}
  .verdict-100 {{
    border-color: var(--accent);
    color: var(--accent);
    background: linear-gradient(90deg, rgba(0,60,0,0.55), rgba(0,30,0,0.5));
    text-shadow: 0 0 14px var(--accent-glow);
    animation: v-in 0.45s cubic-bezier(0.34, 1.56, 0.64, 1) both,
               v-pulse-g 1.4s ease-in-out 0.5s infinite;
  }}
  .verdict-50 {{
    border-color: var(--gold);
    color: var(--gold);
    background: linear-gradient(90deg, rgba(60,50,0,0.55), rgba(30,25,0,0.5));
    text-shadow: 0 0 14px rgba(255,200,61,0.85);
    box-shadow: 0 0 26px rgba(255,200,61,0.4), inset 0 0 20px rgba(255,200,61,0.18);
    animation: v-in 0.45s cubic-bezier(0.34, 1.56, 0.64, 1) both;
  }}
  .verdict-0 {{
    border-color: var(--red);
    color: var(--red);
    background: linear-gradient(90deg, rgba(60,0,0,0.55), rgba(30,0,0,0.5));
    text-shadow: 0 0 14px rgba(211,47,47,0.75);
    box-shadow: 0 0 26px rgba(211,47,47,0.5), inset 0 0 20px rgba(211,47,47,0.18);
    animation: v-in 0.45s cubic-bezier(0.34, 1.56, 0.64, 1) both,
               v-glitch 0.34s steps(2) 0.4s 3;
  }}
  @keyframes v-pulse-g {{
    0%, 100% {{ box-shadow: 0 0 22px rgba(76,175,80,0.4),  inset 0 0 18px rgba(76,175,80,0.15); }}
    50%      {{ box-shadow: 0 0 40px rgba(76,175,80,0.75), inset 0 0 32px rgba(76,175,80,0.3); }}
  }}
  @keyframes v-glitch {{
    0%   {{ transform: translate(0); }}
    25%  {{ transform: translate(-3px, 1px); }}
    50%  {{ transform: translate(2px, -1px); }}
    75%  {{ transform: translate(-1px, 2px); }}
    100% {{ transform: translate(0); }}
  }}

  /* log lines */
  .log {{
    border-left: 2px solid var(--border-2);
    padding: 4px 0 4px 12px;
    margin: 4px 0;
    color: var(--text);
    font-size: 13px;
    line-height: 1.6;
    animation: slideIn 0.35s ease-out both;
  }}
  .log:nth-of-type(1) {{ animation-delay: 0.05s; }}
  .log:nth-of-type(2) {{ animation-delay: 0.12s; }}
  .log:nth-of-type(3) {{ animation-delay: 0.19s; }}
  .log:nth-of-type(4) {{ animation-delay: 0.26s; }}
  @keyframes slideIn {{
    from {{ opacity: 0; transform: translateX(-6px); }}
    to   {{ opacity: 1; transform: translateX(0); }}
  }}
  .log .k {{ color: var(--dim); letter-spacing: 1px; }}
  .log .v {{ color: var(--text-bright); font-weight: 700; font-feature-settings: "tnum"; }}
  .log.steam .v {{ color: var(--accent); text-shadow: 0 0 10px var(--accent-glow); }}
  .log.success {{ border-color: var(--accent); color: #aef0ae; }}
  .log.gold    {{ border-color: var(--gold);   color: var(--gold); text-shadow: 0 0 10px rgba(255,200,61,0.4); }}
  .log.danger  {{ border-color: var(--red);    color: #ff8888; }}

  /* bucket strip (5 cells) */
  .bk-strip {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin: 12px 0; }}
  .chip {{
    text-align: center;
    padding: 10px 0;
    border: 1px solid var(--border-2);
    background: #0a0a0a;
    color: var(--dim);
    font-size: 12px; font-weight: 700;
    transition: all 0.3s ease;
    animation: chipIn 0.4s cubic-bezier(0.22, 1, 0.36, 1) both;
  }}
  .chip-correct {{
    background: linear-gradient(135deg, #1b3a1b, #0d2a0d);
    border-color: var(--accent);
    color: #aef0ae;
    box-shadow: 0 0 22px var(--accent-glow);
    animation: chipIn 0.4s cubic-bezier(0.22, 1, 0.36, 1) both,
               glow-g 1.6s ease-in-out 0.5s infinite;
  }}
  .chip-perfect {{
    background: linear-gradient(135deg, #1f4a1f, #102a10);
    border-color: var(--accent);
    color: #fff;
    box-shadow: 0 0 28px var(--accent-glow);
    animation: chipIn 0.4s cubic-bezier(0.22, 1, 0.36, 1) both,
               glow-y 1.4s ease-in-out 0.5s infinite;
  }}
  .chip-wrong {{
    background: linear-gradient(135deg, #3a1616, #2a0a0a);
    border-color: var(--red);
    color: #ffaaaa;
    animation: chipIn 0.4s cubic-bezier(0.22, 1, 0.36, 1) both,
               shake 0.5s 0.45s;
  }}
  @keyframes glow-g {{ 0%,100% {{ box-shadow: 0 0 16px var(--accent-glow); }} 50% {{ box-shadow: 0 0 28px var(--accent-glow); }} }}
  @keyframes glow-y {{ 0%,100% {{ box-shadow: 0 0 22px var(--accent-glow); transform: scale(1); }} 50% {{ box-shadow: 0 0 40px rgba(76,175,80,0.95); transform: scale(1.04); }} }}
  @keyframes shake  {{ 0%,100% {{ transform: translateX(0); }} 30% {{ transform: translateX(-3px); }} 70% {{ transform: translateX(3px); }} }}

  /* hero (idle) */
  .hero {{
    text-align: center;
    padding: 50px 20px 30px;
    margin: 30px auto;
    max-width: 600px;
    border: 1px solid var(--border-2);
    border-left: 3px solid var(--accent);
    background: var(--panel);
    box-shadow: inset 0 0 50px rgba(0,0,0,0.5), 0 6px 20px rgba(0,0,0,0.6);
  }}
  .hero .icon {{ font-size: 36px; color: var(--accent); text-shadow: 0 0 16px var(--accent-glow); margin-bottom: 12px; animation: heroIconPulse 2.4s ease-in-out infinite; }}
  @keyframes heroIconPulse {{
    0%, 100% {{ text-shadow: 0 0 14px var(--accent-glow); transform: scale(1); }}
    50%      {{ text-shadow: 0 0 28px var(--accent-glow), 0 0 60px rgba(76,175,80,0.5); transform: scale(1.08); }}
  }}
  .hero-title {{
    font-size: 42px;
    font-weight: 900;
    letter-spacing: 7px;
    color: var(--text-bright);
    margin: 8px 0 4px;
    text-shadow: 0 0 18px var(--accent-glow), 0 0 40px rgba(76,175,80,0.3);
    line-height: 1.1;
    animation: titleGlow 3s ease-in-out infinite;
  }}
  @keyframes titleGlow {{
    0%, 100% {{ text-shadow: 0 0 18px var(--accent-glow), 0 0 40px rgba(76,175,80,0.3); }}
    50%      {{ text-shadow: 0 0 28px var(--accent-glow), 0 0 70px rgba(76,175,80,0.55); }}
  }}
  .hero-tagline {{
    color: var(--dim);
    font-size: 13px;
    letter-spacing: 3px;
    margin: 6px 0 14px;
    font-weight: 500;
  }}
  .hero-divider {{
    width: 60%;
    height: 1px;
    margin: 14px auto 18px;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
    box-shadow: 0 0 8px var(--accent-glow);
  }}
  .hero-status, .hero h2 {{ font-size: 16px; font-weight: 700; color: var(--accent); margin: 4px 0 10px; letter-spacing: 2px; text-shadow: 0 0 8px var(--accent-glow); }}
  .hero p {{ color: var(--dim); font-size: 13px; line-height: 1.7; margin: 4px 0; white-space: pre-line; }}
  .hero .rules {{ color: var(--accent); text-shadow: 0 0 8px var(--accent-glow); font-size: 12px; letter-spacing: 1.5px; margin: 16px 0 8px; }}

  /* expander */
  div[data-testid="stExpander"] {{
    background: var(--panel-2);
    border: 1px solid var(--border-2);
    border-radius: 0;
    margin-top: 20px;
  }}
  div[data-testid="stExpander"] summary {{ color: var(--accent) !important; font-weight: 700; letter-spacing: 1.5px; }}
  div[data-testid="stDataFrame"] {{ background: rgba(10,10,12,0.6); }}
</style>
"""

st.markdown(render_css(st.session_state.lang), unsafe_allow_html=True)
st.markdown('<div class="vignette"></div><div class="crt"></div>', unsafe_allow_html=True)


# ---------- HUD ----------

# 直接用 session_state 累積值,不在每次 rerun 重讀 history.json
total = int(st.session_state.hist_total)
avg = (st.session_state.hist_score_sum / total) if total else 0
t = T[st.session_state.lang]

hud_l, hud_r = st.columns([3, 1])
with hud_l:
    st.markdown(
        f"""
<div class="hud fade-in">
  <div class="brand"><span class="blink"></span>◉ {t['title']} · v0.6</div>
  <div class="stats">
    <div class="stat stat-streak">{t['streak']} <b>{st.session_state.streak}</b></div>
    <div class="stat stat-best">{t['best']} <b>{st.session_state.best}</b></div>
    <div class="stat stat-runs">{t['runs']} <b>{total}</b></div>
    <div class="stat stat-avg">{t['avg']} <b>{avg:.0f}</b></div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
with hud_r:
    new_lang = st.radio(
        "lang",
        list(LANG_CODES.keys()),
        index=list(LANG_CODES.keys()).index(st.session_state.lang),
        horizontal=True,
        label_visibility="collapsed",
        key="lang_radio",
    )
    if new_lang != st.session_state.lang:
        st.session_state.lang = new_lang
        st.rerun()

lang_code = LANG_CODES[st.session_state.lang]
t = T[st.session_state.lang]


# ---------- 角落署名(固定右下,glitch + 閃爍游標)----------
st.markdown(
    """
<div class="signature">
  <span class="sig-prefix">//</span>
  <span class="sig-by">crafted by</span>
  <span class="sig-name">吉米</span>
  <span class="sig-cursor"></span>
</div>
""",
    unsafe_allow_html=True,
)


# ---------- BGM(全程存在,跨 phase 不重新 mount) ----------

components.html(
    r"""
<style>
  body { margin: 0; background: transparent; font-family: 'JetBrains Mono','Courier New',monospace; }
  #aw {
    display: flex; gap: 8px; align-items: center;
    padding: 6px 10px;
    background: rgba(8,8,10,0.9);
    border: 1px solid #2a2a30;
    border-left: 3px solid #4caf50;
    color: #4caf50;
    font-size: 11px;
    letter-spacing: 1px;
    width: max-content;
  }
  #aw button {
    background: #0a0a0a;
    border: 1px solid #4caf50;
    color: #4caf50;
    padding: 4px 10px;
    font-family: inherit;
    font-size: 11px;
    cursor: pointer;
    letter-spacing: 1px;
    text-shadow: 0 0 6px rgba(76,175,80,0.5);
  }
  #aw button:hover { background: #1a3a1a; color: #fff; }
  #vol { width: 80px; }
</style>
<div id="aw">
  <span>BGM</span>
  <button id="b">◉ ON</button>
  <input id="vol" type="range" min="0" max="100" value="100" />
</div>
<script>
let ctx=null, master=null, started=false, on=true;
const b = document.getElementById('b');
const vol = document.getElementById('vol');

function buildDrone() {
  ctx = new (window.AudioContext || window.webkitAudioContext)();
  master = ctx.createGain();
  master.gain.value = 0;
  master.connect(ctx.destination);

  const filter = ctx.createBiquadFilter();
  filter.type = 'lowpass';
  filter.frequency.value = 220;
  filter.Q.value = 0.6;
  filter.connect(master);

  function osc(type, freq, gain) {
    const o = ctx.createOscillator(); o.type=type; o.frequency.value=freq;
    const g = ctx.createGain(); g.gain.value=gain;
    o.connect(g); g.connect(filter);
    o.start();
    return o;
  }
  osc('sine', 55, 1.0);
  osc('sine', 73.4, 0.7);
  osc('sawtooth', 27.5, 0.25);
  osc('sine', 110, 0.35);
  osc('sine', 56.2, 0.4);

  const lfo = ctx.createOscillator();
  lfo.type='sine'; lfo.frequency.value=0.13;
  const lfoG = ctx.createGain(); lfoG.gain.value=0.025;
  lfo.connect(lfoG); lfoG.connect(master.gain);
  lfo.start();

  const sw = ctx.createOscillator();
  sw.type='sine'; sw.frequency.value=0.05;
  const swg = ctx.createGain(); swg.gain.value=60;
  sw.connect(swg); swg.connect(filter.frequency);
  sw.start();

  const buf = ctx.createBuffer(1, ctx.sampleRate*2, ctx.sampleRate);
  const data = buf.getChannelData(0);
  for (let i=0; i<data.length; i++) data[i] = (Math.random()*2-1)*0.05;
  const noise = ctx.createBufferSource();
  noise.buffer = buf; noise.loop = true;
  const noiseG = ctx.createGain(); noiseG.gain.value=0.06;
  const bp = ctx.createBiquadFilter(); bp.type='bandpass'; bp.frequency.value=800; bp.Q.value=1.5;
  noise.connect(bp); bp.connect(noiseG); noiseG.connect(master);
  noise.start();
}

function setOn(v) {
  if (!started) return;
  const tgt = v ? (parseInt(vol.value)/100)*0.12 : 0;
  master.gain.cancelScheduledValues(ctx.currentTime);
  master.gain.linearRampToValueAtTime(tgt, ctx.currentTime + (v ? 1.8 : 0.6));
  on = v;
  b.textContent = v ? '◉ ON' : '○ OFF';
  b.style.background = v ? '#1a3a1a' : '#0a0a0a';
  b.style.color = v ? '#fff' : '#4caf50';
}

let primeTargets = [];
function attachPrime(t) {
  try { t.addEventListener('pointerdown', autoPrime, true); t.addEventListener('keydown', autoPrime, true); primeTargets.push(t); } catch(e) {}
}
function detachPrime() {
  for (const t of primeTargets) {
    try { t.removeEventListener('pointerdown', autoPrime, true); t.removeEventListener('keydown', autoPrime, true); } catch(e) {}
  }
  primeTargets = [];
}
function autoPrime(e) {
  if (e.target && e.target.closest && e.target.closest('#b')) return;
  if (!started) { buildDrone(); started=true; setOn(true); }
  detachPrime();
}
attachPrime(document);
try { attachPrime(window.parent.document); } catch(e) {}

b.addEventListener('click', () => {
  detachPrime();
  if (!started) { buildDrone(); started=true; setOn(false); return; }
  setOn(!on);
});
vol.addEventListener('input', () => {
  if (started && on) {
    const tgt = (parseInt(vol.value)/100)*0.12;
    master.gain.cancelScheduledValues(ctx.currentTime);
    master.gain.linearRampToValueAtTime(tgt, ctx.currentTime + 0.2);
  }
});
</script>
""",
    height=42,
)


# ---------- 滑鼠粒子背景(canvas 注入到 parent.document)----------
components.html(
    """
<script>
(function(){
  try {
    const parent = window.parent;
    const doc = parent.document;
    if (doc.body.dataset.particlesArmed === "1") return;
    doc.body.dataset.particlesArmed = "1";

    const canvas = doc.createElement('canvas');
    canvas.id = 'bg-particles';
    // 放在內容上層、modal 下層,低透明度當輕量氛圍特效;clicks 透過 pointer-events:none
    canvas.style.cssText = 'position:fixed; inset:0; pointer-events:none; z-index:5; opacity:0.5; mix-blend-mode:screen;';
    doc.body.appendChild(canvas);

    const ctx = canvas.getContext('2d');
    let mouseX = -9999, mouseY = -9999;

    const SPACING = 22;          // 網格間距(px)
    const REPEL_RADIUS = 110;    // 滑鼠影響半徑
    const MAX_OFFSET = 5;        // 粒子最大位移
    const SPRING = 0.18;         // 朝目標位置插值速度
    const BASE_R = 0.55;
    const BASE_ALPHA = 0.09;     // 平時透明度
    const GLOW_ALPHA = 0.6;      // 滑鼠靠近時最大透明度

    let particles = [];

    function rebuildGrid() {
      particles = [];
      const cols = Math.ceil(canvas.width / SPACING) + 2;
      const rows = Math.ceil(canvas.height / SPACING) + 2;
      for (let i = 0; i < cols; i++) {
        for (let j = 0; j < rows; j++) {
          // 每隔一行錯位半格,做出更有結構感的網格(類似六邊形)
          const offsetX = (j % 2 === 0) ? 0 : SPACING / 2;
          const hx = i * SPACING - SPACING + offsetX;
          const hy = j * SPACING - SPACING;
          particles.push({
            homeX: hx, homeY: hy,
            x: hx, y: hy,
          });
        }
      }
    }

    function resize() {
      canvas.width = parent.innerWidth;
      canvas.height = parent.innerHeight;
      rebuildGrid();
    }
    resize();
    parent.addEventListener('resize', resize);

    doc.addEventListener('mousemove', (e) => {
      mouseX = e.clientX;
      mouseY = e.clientY;
    }, true);
    doc.addEventListener('mouseleave', () => { mouseX = -9999; mouseY = -9999; });

    function frame() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      for (const p of particles) {
        const dx = p.homeX - mouseX;
        const dy = p.homeY - mouseY;
        const dist = Math.sqrt(dx*dx + dy*dy);

        let targetX = p.homeX, targetY = p.homeY;
        let influence = 0;
        if (dist < REPEL_RADIUS && dist > 0) {
          influence = Math.pow(1 - dist / REPEL_RADIUS, 2);  // 0..1 越近越大
          const offset = influence * MAX_OFFSET;
          targetX = p.homeX + (dx / dist) * offset;
          targetY = p.homeY + (dy / dist) * offset;
        }

        // 平滑插值朝 target,沒有慣性
        p.x += (targetX - p.x) * SPRING;
        p.y += (targetY - p.y) * SPRING;

        const alpha = BASE_ALPHA + influence * (GLOW_ALPHA - BASE_ALPHA);
        const r = BASE_R + influence * 1.2;

        ctx.beginPath();
        ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(170, 230, 180,' + alpha + ')';
        if (influence > 0.05) {
          ctx.shadowColor = 'rgba(76,175,80,0.7)';
          ctx.shadowBlur = r * 3;
        } else {
          ctx.shadowBlur = 0;
        }
        ctx.fill();
      }
      ctx.shadowBlur = 0;
      parent.requestAnimationFrame(frame);
    }
    parent.requestAnimationFrame(frame);
  } catch(e) {}
})();
</script>
""",
    height=0,
)


# ---------- click feedback: when a button is pressed, mark it so CSS can flash → dim it ----------
components.html(
    """
<script>
(function(){
  try {
    const doc = window.parent.document;
    if (doc.body.dataset.clickFxArmed === "1") return;
    doc.body.dataset.clickFxArmed = "1";
    doc.addEventListener('mousedown', (e) => {
      const btn = e.target.closest('[data-testid="stButton"] button');
      if (btn && !btn.disabled) btn.classList.add('cta-clicked');
    }, true);
  } catch(e) {}
})();
</script>
""",
    height=0,
)


# ---------- 計時 HUD timer(JS 獨立 tick,不靠 Streamlit rerun)----------
if (
    st.session_state.phase in ("playing", "revealed")
    and st.session_state.session_start_time > 0
):
    _start_ms = int(st.session_state.session_start_time * 1000)
    _limit_ms = TIME_LIMIT * 1000
    components.html(
        f"""
<style>
  body {{ margin: 0; background: transparent; font-family: 'JetBrains Mono','Courier New',monospace; }}
  #tw {{
    display: inline-flex; gap: 14px; align-items: baseline;
    padding: 8px 18px;
    background: rgba(8,8,10,0.9);
    border: 1px solid #2a2a30;
    border-left: 3px solid var(--accent, #4caf50);
    color: #4caf50;
    font-size: 12px;
    letter-spacing: 2px;
  }}
  #tw .lbl   {{ color: #888; font-size: 11px; }}
  #tw .clock {{ font-size: 22px; font-weight: 800; letter-spacing: 3px; color: #4caf50; text-shadow: 0 0 10px rgba(76,175,80,0.6); font-feature-settings: "tnum"; }}
  #tw .score {{ color: #888; font-size: 11px; }}
  #tw .score b {{ color: #fff; font-size: 14px; font-weight: 800; margin-left: 4px; font-feature-settings: "tnum"; text-shadow: 0 0 8px rgba(255,255,255,0.3); }}
  .urgent .clock {{ color: #ff8a3c !important; text-shadow: 0 0 14px rgba(255,138,60,0.85) !important; animation: blink 0.45s steps(2) infinite; }}
  .urgent {{ border-left-color: #ff8a3c !important; }}
  .danger .clock {{ color: #ff4040 !important; text-shadow: 0 0 16px rgba(255,64,64,0.95) !important; animation: blink 0.28s steps(2) infinite; }}
  .danger {{ border-left-color: #ff4040 !important; }}
  @keyframes blink {{ 50% {{ opacity: 0.35; }} }}
</style>
<div id="tw">
  <span class="lbl">{t['time_left']}</span>
  <span class="clock" id="clk">--:--</span>
  <span class="score">{t['session_score']} <b id="scr">{st.session_state.session_score}</b></span>
</div>
<script>
(function(){{
  const start = {_start_ms};
  const limit = {_limit_ms};
  const tw = document.getElementById('tw');
  const clk = document.getElementById('clk');
  function tick() {{
    const remain = Math.max(0, limit - (Date.now() - start));
    const s = Math.ceil(remain / 1000);
    const mm = String(Math.floor(s / 60)).padStart(2, '0');
    const ss = String(s % 60).padStart(2, '0');
    clk.textContent = mm + ':' + ss;
    tw.classList.toggle('urgent', remain > 0 && remain <= 60000);
    tw.classList.toggle('danger', remain > 0 && remain <= 15000);
    if (remain > 0) setTimeout(tick, 250);
  }}
  tick();
}})();
</script>
""",
        height=50,
    )


def render_loader_html(line1: str, line2: str) -> str:
    return f"""
<div class="loader fade-in">
  <div class="row"><span class="loader-line l1">&gt; {line1}</span></div>
  <div class="row"><span class="loader-line l2">&gt; {line2}</span></div>
  <div class="dots"><span></span><span></span><span></span></div>
  <div class="progress-bar"></div>
</div>
"""


# ---------- pool ----------

# 先顯示載入提示——首次重建 pool 要打 5 頁 steamspy ≈ 3-5 秒,避免白屏
_pool_cached_now = _load_cached_pool()
_needs_rebuild = not (_pool_cached_now and "reviews" in (_pool_cached_now[0] if _pool_cached_now else {}) and len(_pool_cached_now) >= 4000)
if _needs_rebuild:
    _pool_loader = st.empty()
    _pool_loader.markdown(render_loader_html("Building game pool", "First-time setup, ~5s"), unsafe_allow_html=True)

try:
    pool = load_pool()
except Exception as e:
    st.error(f"題庫載入失敗：{e}")
    st.stop()

if _needs_rebuild:
    _pool_loader.empty()

if not pool:
    st.error("題庫是空的——steamspy 可能暫時無法連線,稍後重新整理試試,或刪除 ~/.config/steam-guesser/pool.json")
    st.stop()


# ---------- IDLE ----------

if st.session_state.phase == "idle":
    st.markdown(
        f"""
<div class="hero fade-in">
  <div class="icon">◉</div>
  <h1 class="hero-title">{t['title']}</h1>
  <div class="hero-tagline">// {t['tagline']}</div>
  <div class="hero-divider"></div>
  <h2 class="hero-status">&gt; {t['ready']}</h2>
  <p>{t['intro']}</p>
  <div class="rules">{t['rules']}</div>
</div>
""",
        unsafe_allow_html=True,
    )
    # 提示這是計時挑戰
    st.markdown(
        f"<div style='text-align:center; color:var(--accent); letter-spacing:4px; font-size:13px; margin: 6px 0 12px; text-shadow:0 0 8px var(--accent-glow);'>⏱ {t['mode_timed']} · {t['time_attack']}</div>",
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        if st.button(f"[ {t['start']} ]", use_container_width=True, type="primary", key="btn_start"):
            ph = st.empty()
            with ph.container():
                st.markdown(render_loader_html(t["load1"], t["load2"]), unsafe_allow_html=True)
                components.html(
                    """
<script>
(function(){
  try {
    const doc = window.parent.document;
    setTimeout(() => {
      const l = doc.querySelector('.loader');
      if (l) l.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 80);
  } catch(e) {}
})();
</script>
""",
                    height=0,
                )
            g = find_target(pool, st.session_state.seen, lang_code)
            ph.empty()
            if g:
                st.session_state.game = g
                st.session_state.seen.add(g["appid"])
                st.session_state.phase = "playing"
                st.session_state.picked = None
                st.session_state.celebrated = False
                # reset session counters when starting (timed or casual restart)
                st.session_state.session_score = 0
                st.session_state.session_picks = 0
                st.session_state.session_perfects = 0
                st.session_state.session_nears = 0
                st.session_state.session_misses = 0
                st.session_state.session_start_time = time.time()
                st.session_state.show_curtain = True
            else:
                st.error(t["rate_limit"])
            st.rerun()

    if st.session_state.hist_total:
        with st.expander(t["history"], expanded=False):
            # idle 階段才會讀完整檔案——遊戲中不會碰
            hist = load_history()
            valid = [h for h in hist if h.get("picked", -1) < len(BUCKETS) and h.get("actual_bucket", -1) < len(BUCKETS)]
            recent = list(reversed(valid[-10:]))
            st.dataframe(
                [
                    {
                        t["tbl_target"]:  h.get("name", ""),
                        t["tbl_pick"]:    f"[{LETTERS[h['picked']]}] {BUCKETS[h['picked']][2]}",
                        t["tbl_actual"]:  f"[{LETTERS[h['actual_bucket']]}] {BUCKETS[h['actual_bucket']][2]}",
                        t["tbl_reviews"]: f"{h.get('actual_reviews', 0):,}",
                        t["tbl_score"]:   h["score"],
                    }
                    for h in recent
                ],
                use_container_width=True,
                hide_index=True,
            )

    st.stop()


# ---------- 時間到 → 轉 ended phase(讓使用者在 revealed 看完最後一題才結算) ----------

if (
    st.session_state.phase == "playing"
    and st.session_state.session_start_time > 0
    and (time.time() - st.session_state.session_start_time) >= TIME_LIMIT
):
    st.session_state.phase = "ended"


# ---------- ENDED(計時模式結算)----------

if st.session_state.phase == "ended":
    final_score = int(st.session_state.session_score)
    is_record = final_score > st.session_state.session_best
    if is_record:
        st.session_state.session_best = final_score
        save_best(final_score)

    record_html = (
        f'<div class="ended-record">★ {t["new_record"]} ★</div>'
        if is_record else ""
    )
    st.markdown(
        f"""
<div class="impact-flash impact-100"></div>
<div class="ended-wrap fade-in">
  <div class="ended-tag">{t['ended_title']}</div>
  {record_html}
  <div class="ended-score-num">+{final_score}</div>
  <div class="ended-score-lbl">{t['session_score']}</div>
</div>
""",
        unsafe_allow_html=True,
    )

    s_l, s_r = st.columns([1, 1])
    with s_l:
        st.markdown(
            f"""
<div class="log"><span class="k">{t['session_picks']}</span> <span style="color:var(--dimmer)">::</span> <span class="v">{st.session_state.session_picks}</span></div>
<div class="log success"><span class="k">{t['perfects']}</span> <span style="color:var(--dimmer)">::</span> <span class="v">{st.session_state.session_perfects}</span></div>
<div class="log gold"><span class="k">{t['near_hits']}</span> <span style="color:var(--dimmer)">::</span> <span class="v">{st.session_state.session_nears}</span></div>
<div class="log danger"><span class="k">{t['misses']}</span> <span style="color:var(--dimmer)">::</span> <span class="v">{st.session_state.session_misses}</span></div>
""",
            unsafe_allow_html=True,
        )
    with s_r:
        st.markdown(
            f"""
<div class="log"><span class="k">{t['personal_best']}</span> <span style="color:var(--dimmer)">::</span> <span class="v">{st.session_state.session_best}</span></div>
""",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    pa_c1, pa_c2, pa_c3 = st.columns([1, 1, 1])
    with pa_c2:
        if st.button(f"[ {t['play_again']} ]", use_container_width=True, type="primary", key="btn_again"):
            st.session_state.phase = "idle"
            st.session_state.game = None
            st.session_state.picked = None
            st.session_state.celebrated = False
            st.session_state.session_start_time = 0.0
            st.session_state.session_score = 0
            st.session_state.session_picks = 0
            st.session_state.session_perfects = 0
            st.session_state.session_nears = 0
            st.session_state.session_misses = 0
            st.rerun()
    st.stop()


# ---------- 載入當前遊戲 ----------

g = st.session_state.game
details, _ = fetch_game(g["appid"], lang_code)
if details is None:
    st.error(t["rate_limit"])
    st.stop()
actual_idx = bucket_of(g["reviews"])

# 進入 playing 時的黑幕 reveal:覆蓋整個畫面,半秒後淡出,
# 期間下方面板/媒體/文字依各自延遲依序進場(空殼 → 媒體 → 文字打字)
if st.session_state.show_curtain and st.session_state.phase == "playing":
    st.markdown('<div class="curtain"></div>', unsafe_allow_html=True)
    st.session_state.show_curtain = False


# ---------- 上半:視覺(左) + 描述(右) ----------

L, R = st.columns([1.45, 1])

with L:
    st.markdown(
        f'<div class="prompt" data-nonce="{g["appid"]}"><span class="arrow">&gt;</span><span class="accent">{t["scanning"]}</span></div>',
        unsafe_allow_html=True,
    )

    video_url = hero_video_url(details)
    if video_url:
        st.video(video_url, autoplay=True, loop=True, muted=True)
    elif details.get("header_image"):
        st.image(details["header_image"], use_container_width=True)

    shots = details.get("screenshots") or []
    if shots:
        cols = st.columns(min(3, len(shots)))
        for i, s in enumerate(shots[:3]):
            cols[i].image(s["path_thumbnail"], use_container_width=True)

with R:
    title = details.get("name", "—")
    desc = details.get("short_description", "") or "—"
    genres = " · ".join(x["description"] for x in details.get("genres", [])[:4]) or "—"
    release = details.get("release_date", {}).get("date", "—")
    if details.get("price_overview"):
        price = details["price_overview"]["final_formatted"]
    elif details.get("is_free"):
        price = t["free"]
    else:
        price = "—"
    devs = ", ".join(details.get("developers", [])[:2]) or "—"

    panel_nonce = g["appid"]
    st.markdown(
        f"""
<div class="prompt" data-nonce="{panel_nonce}"><span class="arrow">&gt;</span><span class="accent">{t['metadata']}</span></div>
<div class="panel panel-glow" data-nonce="{panel_nonce}">
  <div class="target-title">{title}</div>
  <div class="target-desc">{desc}</div>
  <div class="meta">
    <div class="row"><span class="k">{t['genre']}</span><span class="sep">::</span><span class="v">{genres}</span></div>
    <div class="row"><span class="k">{t['release']}</span><span class="sep">::</span><span class="v">{release}</span></div>
    <div class="row"><span class="k">{t['price']}</span><span class="sep">::</span><span class="v">{price}</span></div>
    <div class="row"><span class="k">{t['dev']}</span><span class="sep">::</span><span class="v">{devs}</span></div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


# ---------- 下半:答題 / 結果(全寬) ----------

st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)

if st.session_state.phase == "playing":
    st.markdown(
        f"""
<div class="prompt" id="query-prompt" data-nonce="{g['appid']}">
  <span class="arrow">&gt;</span><span class="accent">QUERY</span>
  <span style="color:var(--dim); margin-left:6px;">{t['query']}</span><span class="caret"></span>
</div>
<div style="color: var(--dim); font-size:12px; letter-spacing:1px; margin: 6px 0 12px;">
  {t['select_prompt']}
</div>
""",
        unsafe_allow_html=True,
    )

    # auto-scroll to the answer area on new game. Try multiple times because Streamlit
    # may still be rendering and reset scroll right after the iframe mounts.
    components.html(
        f"""
<script>
(function(){{
  try {{
    const doc = window.parent.document;
    const win = window.parent;
    const key = 'play_{g['appid']}';
    if (doc.body.dataset.lastPlayScroll === key) return;
    doc.body.dataset.lastPlayScroll = key;
    function doScroll() {{
      const q = doc.getElementById('query-prompt');
      if (q) {{
        q.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      }} else {{
        win.scrollTo({{ top: doc.body.scrollHeight, behavior: 'smooth' }});
      }}
    }}
    // Streamlit re-renders settle over ~1s; fire repeatedly so the last call wins
    [250, 600, 1000, 1500].forEach(d => setTimeout(doScroll, d));
  }} catch(e) {{}}
}})();
</script>
""",
        height=0,
    )

    bcols = st.columns(len(BUCKETS))
    for i, (lo, hi, label) in enumerate(BUCKETS):
        with bcols[i]:
            if st.button(f"[ {LETTERS[i]} ]    {label}", key=f"bk_{i}", use_container_width=True):
                s = score_for(i, actual_idx)
                new_streak = st.session_state.streak + 1 if s >= 50 else 0
                st.session_state.streak = new_streak
                st.session_state.best = max(st.session_state.best, new_streak)
                st.session_state.picked = i
                st.session_state.phase = "revealed"
                st.session_state.celebrated = False
                # session counters (used by both modes; only 計時 mode shows結算)
                st.session_state.session_score += s
                st.session_state.session_picks += 1
                if s == 100:
                    st.session_state.session_perfects += 1
                elif s == 50:
                    st.session_state.session_nears += 1
                else:
                    st.session_state.session_misses += 1
                save_history(
                    {
                        "ts": int(time.time()),
                        "appid": g["appid"],
                        "name": details.get("name"),
                        "picked": i,
                        "actual_bucket": actual_idx,
                        "actual_reviews": g["reviews"],
                        "score": s,
                    }
                )
                # 同步 HUD 統計值,避免下次 rerun 又去讀檔
                st.session_state.hist_total += 1
                st.session_state.hist_score_sum += s
                st.rerun()

elif st.session_state.phase == "revealed":
    picked = st.session_state.picked
    s = score_for(picked, actual_idx)
    label_map = {
        100: t["lbl_perfect"],
        50:  t["lbl_adjacent"],
        0:   t["lbl_miss"],
    }

    verdict_map = {
        100: ("★", "MATCH"),
        50:  ("◉", "NEAR_HIT"),
        0:   ("✗", "DEVIATION"),
    }
    v_sym, v_code = verdict_map[s]
    st.markdown(
        f"""
<div class="impact-flash impact-{s}"></div>
<div class="verdict verdict-{s}"><span class="tw">{v_sym}&nbsp;&nbsp;{v_code}</span></div>
""",
        unsafe_allow_html=True,
    )

    rev_L, rev_R = st.columns([1, 1.4])
    with rev_L:
        st.markdown(
            f"""
<div class="prompt"><span class="arrow">&gt;</span><span class="accent">{t['analysis_done']}</span></div>
<div class="score score-{s}">
  <div class="num">+{s}</div>
  <div class="lbl">{label_map[s]}</div>
</div>
""",
            unsafe_allow_html=True,
        )
    with rev_R:
        log_class = {100: "success", 50: "gold", 0: "danger"}[s]
        delta = picked - actual_idx
        st.markdown(
            f"""
<div class="log steam"><span class="k">{t['actual']}</span> <span style="color:var(--dimmer)">::</span> <span class="v">{g['reviews']:,}</span></div>
<div class="log"><span class="k">{t['correct']}</span> <span style="color:var(--dimmer)">::</span> <span class="v">[{LETTERS[actual_idx]}] {BUCKETS[actual_idx][2]}</span></div>
<div class="log"><span class="k">{t['your_pick']}</span> <span style="color:var(--dimmer)">::</span> <span class="v">[{LETTERS[picked]}] {BUCKETS[picked][2]}</span></div>
<div class="log {log_class}"><span class="k">{t['delta']}</span> <span style="color:var(--dimmer)">::</span> <span class="v">{delta:+d}</span></div>
""",
            unsafe_allow_html=True,
        )

    chips = []
    for i in range(len(BUCKETS)):
        if i == actual_idx and i == picked:
            cls, mk = "chip chip-perfect", "★"
        elif i == actual_idx:
            cls, mk = "chip chip-correct", "✓"
        elif i == picked:
            cls, mk = "chip chip-wrong", "✗"
        else:
            cls, mk = "chip", LETTERS[i]
        chips.append(f"<div class='{cls}'>{mk}</div>")
    st.markdown(f"<div class='bk-strip'>{''.join(chips)}</div>", unsafe_allow_html=True)

    sfx_freq = {100: 880, 50: 523, 0: 196}[s]
    components.html(
        f"""
<script>
(function(){{
  try {{
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const now = ctx.currentTime;
    const o = ctx.createOscillator();
    o.type = {'\"square\"' if s == 0 else '\"sine\"'};
    o.frequency.setValueAtTime({sfx_freq}, now);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0, now);
    g.gain.linearRampToValueAtTime(0.25, now + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, now + 0.5);
    o.connect(g); g.connect(ctx.destination);
    o.start(now);
    o.stop(now + 0.55);
    {'// rising arpeggio for perfect' if s == 100 else ''}
    {'const o2 = ctx.createOscillator(); o2.type = "sine"; o2.frequency.setValueAtTime(1320, now+0.15); const g2 = ctx.createGain(); g2.gain.setValueAtTime(0, now+0.15); g2.gain.linearRampToValueAtTime(0.2, now+0.17); g2.gain.exponentialRampToValueAtTime(0.0001, now+0.7); o2.connect(g2); g2.connect(ctx.destination); o2.start(now+0.15); o2.stop(now+0.75);' if s == 100 else ''}
  }} catch(e) {{}}

  // auto-scroll to verdict so user sees the result + Next button without scrolling
  try {{
    const doc = window.parent.document;
    setTimeout(() => {{
      const v = doc.querySelector('.verdict');
      if (v) v.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
    }}, 60);
  }} catch(e) {{}}
}})();
</script>
""",
        height=0,
    )

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    # 時間到 → 改顯示「結算」按鈕,點下去看總成績
    time_up = (
        st.session_state.session_start_time > 0
        and (time.time() - st.session_state.session_start_time) >= TIME_LIMIT
    )
    next_label = t["view_results"] if time_up else t["next"]
    if st.button(f"[ {next_label} ]", use_container_width=True, type="primary", key="btn_next"):
        if time_up:
            st.session_state.phase = "ended"
            st.rerun()
        ph = st.empty()
        with ph.container():
            st.markdown(render_loader_html(t["load1"], t["load2"]), unsafe_allow_html=True)
            components.html(
                """
<script>
(function(){
  try {
    const doc = window.parent.document;
    setTimeout(() => {
      const l = doc.querySelector('.loader');
      if (l) l.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 80);
  } catch(e) {}
})();
</script>
""",
                height=0,
            )
        new_g = find_target(pool, st.session_state.seen, lang_code)
        ph.empty()
        if new_g:
            st.session_state.game = new_g
            st.session_state.seen.add(new_g["appid"])
            st.session_state.phase = "playing"
            st.session_state.show_curtain = True
        else:
            st.session_state.phase = "idle"
            st.session_state.game = None
        st.session_state.picked = None
        st.session_state.celebrated = False
        st.rerun()


