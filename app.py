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

MIN_REVIEWS = 20

LANG_CODES = {"繁中": "tchinese", "EN": "english"}

BUCKETS = [
    (0,        100,            "< 100"),
    (100,      1_000,          "100–1K"),
    (1_000,    10_000,         "1K–10K"),
    (10_000,   100_000,        "10K–100K"),
    (100_000,  float("inf"),   "100K+"),
]
LETTERS = ["A", "B", "C", "D", "E"]

SCORE_TABLE = {0: 100, 1: 50}

T = {
    "繁中": {
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

@st.cache_data(ttl=86400, show_spinner=False)
def load_pool() -> list[dict]:
    if POOL_FILE.exists():
        return json.loads(POOL_FILE.read_text(encoding="utf-8"))
    r = requests.get(
        "https://steamspy.com/api.php",
        params={"request": "all", "page": 0},
        timeout=30,
    )
    r.raise_for_status()
    pool = [
        {"appid": int(k), "name": v.get("name", "")}
        for k, v in r.json().items()
        if v.get("name")
    ]
    POOL_FILE.write_text(json.dumps(pool, ensure_ascii=False), encoding="utf-8")
    return pool


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
    for _ in range(12):
        pick = random.choice(pool)
        if pick["appid"] in exclude:
            continue
        details, reviews = fetch_game(pick["appid"], lang)
        if details and reviews and reviews >= MIN_REVIEWS:
            return {"appid": pick["appid"], "reviews": reviews}
        time.sleep(0.3)
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


def load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    n = len(BUCKETS)
    return [
        h for h in data
        if isinstance(h.get("picked"), int)
        and 0 <= h["picked"] < n
        and 0 <= h.get("actual_bucket", -1) < n
    ]


def save_history(entry: dict) -> None:
    h = load_history()
    h.append(entry)
    HISTORY_FILE.write_text(
        json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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
    st.session_state.lang = "繁中"
    st.session_state.phase = "idle"
    st.session_state.game = None
    st.session_state.picked = None
    st.session_state.celebrated = False
    st.session_state.seen = set()
    st.session_state.streak = trailing_streak(h0)
    st.session_state.best = best_streak(h0)


# ---------- CSS（語系決定深淺） ----------

DARKER = st.session_state.lang == "繁中"

# 顏色變數
if DARKER:
    BG_1 = "#000000"
    BG_2 = "#050507"
    PANEL = "rgba(8,8,10,0.85)"
    PANEL_2 = "rgba(12,12,14,0.7)"
    TEXT = "#9aa0a6"
    TEXT_BRIGHT = "#e0e0e0"
    DIM = "#525860"
    ACCENT = "#4caf50"
    ACCENT_GLOW = "rgba(76,175,80,0.45)"
else:
    BG_1 = "#020203"
    BG_2 = "#0a0a0e"
    PANEL = "rgba(15,15,18,0.85)"
    PANEL_2 = "rgba(18,18,22,0.7)"
    TEXT = "#b0b0b0"
    TEXT_BRIGHT = "#ffffff"
    DIM = "#666"
    ACCENT = "#4caf50"
    ACCENT_GLOW = "rgba(76,175,80,0.55)"

CSS = f"""
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
  .fade-in {{ animation: fadeUp 0.45s cubic-bezier(0.22, 1, 0.36, 1) both; }}
  @keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(8px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}

  /* panel */
  .panel {{
    background: var(--panel-2);
    border: 1px solid var(--border);
    padding: 14px 16px;
    box-shadow: inset 0 0 30px rgba(0,0,0,0.5);
  }}
  .panel-glow {{ border-left: 3px solid var(--accent); }}

  /* media */
  div[data-testid="stImage"] img,
  div[data-testid="stVideo"] video {{
    border: 1px solid var(--border-2);
    animation: imgIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) both;
    filter: brightness(0.9) contrast(1.05);
  }}
  @keyframes imgIn {{
    from {{ opacity: 0; filter: blur(10px) brightness(0.5); transform: scale(1.02); }}
    to   {{ opacity: 1; filter: blur(0)   brightness(0.9);  transform: scale(1); }}
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
  div[data-testid="stRadio"] > div {{ background: transparent; gap: 4px; }}
  div[data-testid="stRadio"] label {{
    background: #0a0a0a !important;
    border: 1px solid var(--border-2) !important;
    border-radius: 0 !important;
    padding: 4px 12px !important;
    font-size: 12px !important;
    cursor: pointer;
    transition: all 0.18s;
    letter-spacing: 1px;
  }}
  div[data-testid="stRadio"] label:hover {{ background: #1a1a1a !important; }}
  div[data-testid="stRadio"] label:has(input:checked) {{
    background: linear-gradient(90deg, #265a26, #0e2a0e) !important;
    border-color: var(--accent) !important;
    color: #fff !important;
    box-shadow: 0 0 12px var(--accent-glow);
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
  .score-100 .num {{ color: var(--gold);  text-shadow: 0 0 28px rgba(255,200,61,0.7); }}
  .score-100 .lbl {{ color: var(--gold); }}
  .score-50  .num {{ color: var(--accent); text-shadow: 0 0 22px var(--accent-glow); }}
  .score-50  .lbl {{ color: var(--accent); }}
  .score-0   .num {{ color: var(--red);   text-shadow: 0 0 22px rgba(211,47,47,0.55); transform: skewX(-3deg); }}
  .score-0   .lbl {{ color: var(--red); }}

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
  .bk-strip {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; margin: 12px 0; }}
  .chip {{
    text-align: center;
    padding: 10px 0;
    border: 1px solid var(--border-2);
    background: #0a0a0a;
    color: var(--dim);
    font-size: 12px; font-weight: 700;
    transition: all 0.3s ease;
  }}
  .chip-correct {{
    background: linear-gradient(135deg, #1b3a1b, #0d2a0d);
    border-color: var(--accent);
    color: #aef0ae;
    box-shadow: 0 0 22px var(--accent-glow);
    animation: glow-g 1.6s ease-in-out infinite;
  }}
  .chip-perfect {{
    background: linear-gradient(135deg, #3a3216, #2a240a);
    border-color: var(--gold);
    color: #fff;
    box-shadow: 0 0 26px rgba(255,200,61,0.6);
    animation: glow-y 1.4s ease-in-out infinite;
  }}
  .chip-wrong {{
    background: linear-gradient(135deg, #3a1616, #2a0a0a);
    border-color: var(--red);
    color: #ffaaaa;
    animation: shake 0.5s;
  }}
  @keyframes glow-g {{ 0%,100% {{ box-shadow: 0 0 16px var(--accent-glow); }} 50% {{ box-shadow: 0 0 28px var(--accent-glow); }} }}
  @keyframes glow-y {{ 0%,100% {{ box-shadow: 0 0 22px rgba(255,200,61,0.5); transform: scale(1); }} 50% {{ box-shadow: 0 0 36px rgba(255,200,61,0.95); transform: scale(1.03); }} }}
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
  .hero .icon {{ font-size: 36px; color: var(--accent); text-shadow: 0 0 16px var(--accent-glow); margin-bottom: 12px; }}
  .hero h2 {{ font-size: 18px; font-weight: 800; color: var(--text-bright); margin: 8px 0 6px; letter-spacing: 1px; }}
  .hero p {{ color: var(--dim); font-size: 13px; line-height: 1.7; margin: 4px 0; white-space: pre-line; }}
  .hero .rules {{ color: var(--accent); text-shadow: 0 0 8px var(--accent-glow); font-size: 12px; letter-spacing: 1.5px; margin: 16px 0 24px; }}

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

st.markdown(CSS, unsafe_allow_html=True)
st.markdown('<div class="vignette"></div><div class="crt"></div>', unsafe_allow_html=True)


# ---------- HUD ----------

hist = load_history()
total = len(hist)
avg = (sum(h["score"] for h in hist) / total) if total else 0
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


def render_loader_html(line1: str, line2: str) -> str:
    return f"""
<div class="loader fade-in">
  <div class="row"><span class="loader-line l1">&gt; {line1}</span></div>
  <div class="row"><span class="loader-line l2">&gt; {line2}</span></div>
  <div class="dots"><span></span><span></span><span></span></div>
</div>
"""


# ---------- pool ----------

try:
    pool = load_pool()
except Exception as e:
    st.error(f"題庫載入失敗：{e}")
    st.stop()


# ---------- IDLE ----------

if st.session_state.phase == "idle":
    st.markdown(
        f"""
<div class="hero fade-in">
  <div class="icon">◉</div>
  <h2>&gt; {t['ready']}</h2>
  <p>{t['intro']}</p>
  <div class="rules">{t['rules']}</div>
</div>
""",
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        if st.button(f"[ {t['start']} ]", use_container_width=True, type="primary", key="btn_start"):
            ph = st.empty()
            ph.markdown(render_loader_html(t["load1"], t["load2"]), unsafe_allow_html=True)
            g = find_target(pool, st.session_state.seen, lang_code)
            ph.empty()
            if g:
                st.session_state.game = g
                st.session_state.seen.add(g["appid"])
                st.session_state.phase = "playing"
                st.session_state.picked = None
                st.session_state.celebrated = False
            else:
                st.error(t["rate_limit"])
            st.rerun()

    if hist:
        with st.expander(t["history"], expanded=False):
            recent = list(reversed(hist[-10:]))
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

    # idle 也要有音訊控制（用戶可在這裡先開好音效）
    components.html(
        AUDIO_HTML := r"""
<style>
  body { margin: 0; background: transparent; font-family: 'JetBrains Mono','Courier New',monospace; }
  #aw {
    display: flex; gap: 6px; align-items: center;
    padding: 6px 10px;
    background: rgba(8,8,10,0.85);
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
  #aw button:disabled { opacity: 0.4; cursor: not-allowed; }
  #vol { width: 70px; }
</style>
<div id="aw">
  <span>BGM</span>
  <button id="b">○ OFF</button>
  <input id="vol" type="range" min="0" max="100" value="40" />
</div>
<script>
let ctx=null, master=null, started=false, on=false;
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

  // multiple low oscillators for a thick drone
  function osc(type, freq, gain) {
    const o = ctx.createOscillator(); o.type = type; o.frequency.value = freq;
    const g = ctx.createGain(); g.gain.value = gain;
    o.connect(g); g.connect(filter);
    o.start();
    return o;
  }
  osc('sine', 55, 1.0);
  osc('sine', 73.4, 0.7);  // perfect fifth-ish
  osc('sawtooth', 27.5, 0.25);
  osc('sine', 110, 0.35);
  // slight detune wobble
  const det = osc('sine', 56.2, 0.4);

  // breathing LFO
  const lfo = ctx.createOscillator();
  lfo.type = 'sine';
  lfo.frequency.value = 0.13;
  const lfoG = ctx.createGain();
  lfoG.gain.value = 0.025;
  lfo.connect(lfoG); lfoG.connect(master.gain);
  lfo.start();

  // very slow filter sweep
  const sw = ctx.createOscillator();
  sw.type = 'sine'; sw.frequency.value = 0.05;
  const swg = ctx.createGain(); swg.gain.value = 60;
  sw.connect(swg); swg.connect(filter.frequency);
  sw.start();

  // occasional crackles via noise + bandpass for that horror tape feel
  const buf = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
  const data = buf.getChannelData(0);
  for (let i=0; i<data.length; i++) data[i] = (Math.random()*2-1) * 0.05;
  const noise = ctx.createBufferSource();
  noise.buffer = buf; noise.loop = true;
  const noiseG = ctx.createGain(); noiseG.gain.value = 0.06;
  const bp = ctx.createBiquadFilter(); bp.type='bandpass'; bp.frequency.value = 800; bp.Q.value = 1.5;
  noise.connect(bp); bp.connect(noiseG); noiseG.connect(master);
  noise.start();
}

function setOn(v) {
  if (!started) return;
  const tgt = v ? (parseInt(vol.value)/100) * 0.12 : 0;
  master.gain.cancelScheduledValues(ctx.currentTime);
  master.gain.linearRampToValueAtTime(tgt, ctx.currentTime + (v ? 1.8 : 0.6));
  on = v;
  b.textContent = v ? '◉ ON' : '○ OFF';
  b.style.background = v ? '#1a3a1a' : '#0a0a0a';
  b.style.color = v ? '#fff' : '#4caf50';
}

b.addEventListener('click', () => {
  if (!started) { buildDrone(); started = true; setOn(true); return; }
  setOn(!on);
});
vol.addEventListener('input', () => {
  if (started && on) {
    const tgt = (parseInt(vol.value)/100) * 0.12;
    master.gain.cancelScheduledValues(ctx.currentTime);
    master.gain.linearRampToValueAtTime(tgt, ctx.currentTime + 0.2);
  }
});
</script>
""",
        height=42,
    )
    st.stop()


# ---------- 載入當前遊戲 ----------

g = st.session_state.game
details, _ = fetch_game(g["appid"], lang_code)
if details is None:
    st.error(t["rate_limit"])
    st.stop()
actual_idx = bucket_of(g["reviews"])


# ---------- 兩欄 ----------

L, R = st.columns([1.45, 1])

with L:
    st.markdown(
        f'<div class="prompt"><span class="arrow">&gt;</span><span class="accent">{t["scanning"]}</span></div>',
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

    st.markdown(
        f"""
<div class="panel panel-glow fade-in" style="margin-top:14px;">
  <div class="prompt" style="margin-top:0; margin-bottom:10px;">
    <span class="arrow">&gt;</span><span class="accent">{t['metadata']}</span>
  </div>
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


with R:
    if st.session_state.phase == "playing":
        st.markdown(
            f"""
<div class="prompt">
  <span class="arrow">&gt;</span><span class="accent">QUERY</span>
  <span style="color:var(--dim); margin-left:6px;">{t['query']}</span><span class="caret"></span>
</div>
<div style="color: var(--dim); font-size:12px; letter-spacing:1px; margin: 14px 0 10px;">
  {t['select_prompt']}
</div>
""",
            unsafe_allow_html=True,
        )
        for i, (lo, hi, label) in enumerate(BUCKETS):
            if st.button(f"[ {LETTERS[i]} ]    {label}", key=f"bk_{i}", use_container_width=True):
                s = score_for(i, actual_idx)
                new_streak = st.session_state.streak + 1 if s >= 50 else 0
                st.session_state.streak = new_streak
                st.session_state.best = max(st.session_state.best, new_streak)
                st.session_state.picked = i
                st.session_state.phase = "computing"
                st.session_state.celebrated = False
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
                st.rerun()

    elif st.session_state.phase == "computing":
        st.markdown(render_loader_html(t["comp1"], t["comp2"]), unsafe_allow_html=True)
        time.sleep(1.4)
        st.session_state.phase = "revealed"
        st.rerun()

    elif st.session_state.phase == "revealed":
        picked = st.session_state.picked
        s = score_for(picked, actual_idx)
        label_map = {
            100: t["lbl_perfect"],
            50:  t["lbl_adjacent"],
            0:   t["lbl_miss"],
        }

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

        log_class = {100: "gold", 50: "success", 0: "danger"}[s]
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

        # 揭曉音效（key 包含 score 與 appid，phase 切到 revealed 才會 mount）
        sfx_freq = {100: 880, 50: 523, 0: 196}[s]  # A5 / C5 / G3
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
}})();
</script>
""",
            height=0,
        )

        if s == 100 and not st.session_state.celebrated:
            st.balloons()
            st.session_state.celebrated = True

        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
        if st.button(f"[ {t['next']} ]", use_container_width=True, type="primary", key="btn_next"):
            ph = st.empty()
            ph.markdown(render_loader_html(t["load1"], t["load2"]), unsafe_allow_html=True)
            new_g = find_target(pool, st.session_state.seen, lang_code)
            ph.empty()
            if new_g:
                st.session_state.game = new_g
                st.session_state.seen.add(new_g["appid"])
                st.session_state.phase = "playing"
            else:
                st.session_state.phase = "idle"
                st.session_state.game = None
            st.session_state.picked = None
            st.session_state.celebrated = False
            st.rerun()


# ---------- 歷史 ----------

if hist:
    with st.expander(t["history"], expanded=False):
        recent = list(reversed(hist[-10:]))
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


# ---------- BGM 控制（持續顯示，內容固定，跨 rerun 不重新 mount） ----------

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
  <button id="b">○ OFF</button>
  <input id="vol" type="range" min="0" max="100" value="40" />
</div>
<script>
let ctx=null, master=null, started=false, on=false;
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

b.addEventListener('click', () => {
  if (!started) { buildDrone(); started=true; setOn(true); return; }
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
