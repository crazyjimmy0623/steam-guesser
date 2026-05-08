"""Steam 銷量/評論預測練習。

每回合隨機抽一款 Steam 遊戲，顯示截圖、描述、tags、發售日、價格，
讓使用者猜評論數（或推算銷量），用 log10 誤差打分。
"""

from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path

import requests
import streamlit as st

CACHE_DIR = Path.home() / ".config" / "steam-guesser"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = CACHE_DIR / "history.json"
POOL_FILE = CACHE_DIR / "pool.json"

BOXLEITER_MULTIPLIER = 40  # 評論數 → 估算銷量的概略倍數

# 使用者選擇用哪種語系載入商店資料；預設繁中、退回英文。
LANG_CODES = {"繁體中文": "tchinese", "English": "english"}


# ---------- 資料抓取 ----------

@st.cache_data(ttl=86400, show_spinner=False)
def load_pool() -> list[dict]:
    """從 SteamSpy 抓 top 1000 遊戲當題庫；只抓一次後存檔。"""
    if POOL_FILE.exists():
        return json.loads(POOL_FILE.read_text(encoding="utf-8"))
    r = requests.get(
        "https://steamspy.com/api.php",
        params={"request": "all", "page": 0},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    pool = [
        {"appid": int(k), "name": v.get("name", "")}
        for k, v in data.items()
        if v.get("name")
    ]
    POOL_FILE.write_text(json.dumps(pool, ensure_ascii=False), encoding="utf-8")
    return pool


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_game(appid: int, lang: str) -> tuple[dict | None, int | None]:
    """回傳 (商店詳情, 評論總數)。失敗時回 (None, None)。"""
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
            headers={"User-Agent": "steam-guesser/0.1"},
            timeout=20,
        ).json()
        review_count = r.get("query_summary", {}).get("total_reviews")
        return details, review_count
    except Exception as e:
        st.error(f"抓取失敗：{e}")
        return None, None


def pick_new_game(lang: str, pool: list[dict], max_tries: int = 8) -> dict | None:
    """隨機抽，跳過抓不到資料或評論數過少的遊戲。"""
    for _ in range(max_tries):
        pick = random.choice(pool)
        details, reviews = fetch_game(pick["appid"], lang)
        if details and reviews and reviews >= 50:
            return {"appid": pick["appid"], "details": details, "reviews": reviews}
        time.sleep(0.4)  # 避免 Steam 限流
    return None


# ---------- 評分 / 紀錄 ----------

def score(guess: int, actual: int) -> int:
    """log10 誤差打分：完全猜中 100，每差一個數量級扣 50。"""
    if guess <= 0 or actual <= 0:
        return 0
    err = abs(math.log10(guess) - math.log10(actual))
    return max(0, round(100 - 50 * err))


def load_history() -> list[dict]:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    return []


def save_history(entry: dict) -> None:
    history = load_history()
    history.append(entry)
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------- UI ----------

st.set_page_config(page_title="Steam 銷量猜猜看", page_icon="🎮", layout="centered")
st.title("Steam 銷量 / 評論預測練習")
st.caption("看畫面與描述，猜評論數或銷量，比比看誰準")

with st.sidebar:
    st.header("設定")
    lang_label = st.selectbox("商店語系", list(LANG_CODES.keys()), index=0)
    lang = LANG_CODES[lang_label]
    mode = st.radio(
        "預測目標",
        ["評論數", f"估算銷量（評論 × {BOXLEITER_MULTIPLIER}）"],
    )
    st.divider()
    if st.button("清除題目快取", help="重新從 SteamSpy 抓題庫"):
        load_pool.clear()
        fetch_game.clear()
        if POOL_FILE.exists():
            POOL_FILE.unlink()
        st.success("已清除")

# 載入題庫
try:
    pool = load_pool()
except Exception as e:
    st.error(f"無法載入題庫：{e}")
    st.stop()

# 狀態
if "current" not in st.session_state:
    st.session_state.current = None
    st.session_state.revealed = False
    st.session_state.last_guess = None

col_a, col_b = st.columns([1, 1])
with col_a:
    if st.button("🎲 換一款", use_container_width=True):
        with st.spinner("抽題中…"):
            st.session_state.current = pick_new_game(lang, pool)
            st.session_state.revealed = False
            st.session_state.last_guess = None
with col_b:
    if st.session_state.current:
        appid = st.session_state.current["appid"]
        st.link_button(
            "在 Steam 開啟",
            f"https://store.steampowered.com/app/{appid}/",
            use_container_width=True,
        )

if st.session_state.current is None:
    st.info("按「換一款」開始")
    st.stop()

cur = st.session_state.current
d = cur["details"]

st.subheader(d.get("name", "（未知）"))

if d.get("header_image"):
    st.image(d["header_image"], use_container_width=True)

shots = d.get("screenshots") or []
if shots:
    cols = st.columns(min(3, len(shots)))
    for i, s in enumerate(shots[:3]):
        cols[i].image(s["path_thumbnail"], use_container_width=True)

if d.get("short_description"):
    st.write(d["short_description"])

meta_bits = []
if d.get("genres"):
    meta_bits.append("**類型：** " + ", ".join(g["description"] for g in d["genres"]))
if d.get("release_date", {}).get("date"):
    meta_bits.append(f"**發售日：** {d['release_date']['date']}")
if d.get("price_overview"):
    meta_bits.append(f"**價格：** {d['price_overview']['final_formatted']}")
elif d.get("is_free"):
    meta_bits.append("**價格：** 免費")
if d.get("developers"):
    meta_bits.append("**開發：** " + ", ".join(d["developers"]))
if meta_bits:
    st.markdown("  \n".join(meta_bits))

st.divider()

guess = st.number_input(
    f"你預測的{mode.split('（')[0]}",
    min_value=1,
    value=st.session_state.last_guess or 5000,
    step=500,
    format="%d",
)

if st.button("揭曉答案", type="primary", disabled=st.session_state.revealed):
    actual_reviews = cur["reviews"]
    if mode == "評論數":
        actual = actual_reviews
        label = "評論數"
    else:
        actual = actual_reviews * BOXLEITER_MULTIPLIER
        label = "估算銷量"

    s = score(guess, actual)
    ratio = guess / actual if actual else 0
    if ratio >= 1:
        diff_msg = f"高估了 {ratio:.2f}×"
    else:
        diff_msg = f"低估了 {1/ratio:.2f}×" if ratio > 0 else "—"

    st.metric(label=f"實際 {label}", value=f"{actual:,}", delta=diff_msg)
    st.metric(label="得分", value=f"{s} / 100")

    save_history(
        {
            "ts": int(time.time()),
            "appid": cur["appid"],
            "name": d.get("name"),
            "mode": mode,
            "guess": int(guess),
            "actual": int(actual),
            "score": s,
        }
    )
    st.session_state.revealed = True
    st.session_state.last_guess = int(guess)

# 歷史
hist = load_history()
if hist:
    st.divider()
    st.subheader(f"已練 {len(hist)} 題，平均 {sum(h['score'] for h in hist)/len(hist):.1f} 分")
    recent = list(reversed(hist[-10:]))
    st.dataframe(
        [
            {
                "遊戲": h["name"],
                "模式": h["mode"],
                "猜": f"{h['guess']:,}",
                "實際": f"{h['actual']:,}",
                "得分": h["score"],
            }
            for h in recent
        ],
        use_container_width=True,
        hide_index=True,
    )
