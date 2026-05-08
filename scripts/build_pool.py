"""Build games.json for the static GitHub Pages frontend.

Workflow:
  1. Fetch SteamSpy /api.php?request=all 10 pages → candidate pool
  2. Bucket-fair sample (deterministic seed) — ~750 per bucket × 4 buckets
  3. For each appid: fetch /api/appdetails?l=english + ?l=tchinese + /appreviews/{id}
  4. Filter games where reviews ∈ [10, 50000] AND both langs have name
  5. Pre-resolve hero_video_url, truncate genres/developers, resolve price string
  6. Atomic write docs/data/games.json + docs/data/version.txt (cachebust hash)

Incremental reuse: if a previous games.json exists AND last_full_refresh < 28 days ago,
games whose appid hasn't been re-sampled this run are reused from the previous build.
Saves ~3 API calls per game.

Dev mode: `--limit 50` → 50 games × EN only → writes games.dev.json (gitignored).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import random
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import requests
from tenacity import (
    retry, retry_if_exception_type, stop_after_attempt,
    wait_exponential, before_sleep_log,
)
import logging


# ---------- 常數 ----------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "docs" / "data"
GAMES_JSON = DATA_DIR / "games.json"
VERSION_TXT = DATA_DIR / "version.txt"
GAMES_DEV_JSON = DATA_DIR / "games.dev.json"

POOL_PAGES = 10
MIN_REVIEWS = 10
MAX_REVIEWS = 50_000
PER_BUCKET_TARGET = 750
SAMPLE_SEED = 0xCAFE
FULL_REFRESH_DAYS = 28
RATE_LIMIT_SLEEP = 0.4   # 約 150 req/min,Steam 觀察上限約 200/min
FAILURE_THRESHOLD = 0.20  # 連續 50 次中失敗率 > 20% → 推測 IP 被擋,abort

BUCKETS = [
    (10,       100,    "10–100"),
    (100,      1_000,  "100–1K"),
    (1_000,    10_000, "1K–10K"),
    (10_000,   50_000, "10K–50K"),
]
BUCKETS_META = [
    {"lo": lo, "hi": hi, "label": label}
    for (lo, hi, label) in BUCKETS
]


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("build_pool")


# ---------- HTTP ----------
class RateLimitError(Exception):
    pass


@retry(
    retry=retry_if_exception_type((requests.RequestException, RateLimitError)),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    reraise=True,
    before_sleep=before_sleep_log(log, logging.WARNING),
)
def http_get(url: str, params: Optional[dict] = None, timeout: int = 30) -> requests.Response:
    r = requests.get(
        url, params=params, timeout=timeout,
        headers={"User-Agent": "steam-guesser-build/0.7"},
    )
    if r.status_code == 429:
        retry_after = r.headers.get("Retry-After")
        if retry_after:
            try:
                time.sleep(min(int(retry_after), 60))
            except ValueError:
                pass
        raise RateLimitError(f"429 from {url}")
    if r.status_code >= 500:
        raise requests.HTTPError(f"{r.status_code} from {url}")
    return r


# ---------- pool fetch ----------
def fetch_steamspy_pool() -> list[dict]:
    """從 SteamSpy /api.php?request=all 抓 10 頁(~10000 款),回傳
    [{appid, name, reviews_estimate}]。沿用 app.py:197-220 的邏輯。"""
    pool: list[dict] = []
    seen: set[int] = set()
    for page in range(POOL_PAGES):
        log.info(f"steamspy page {page + 1}/{POOL_PAGES}")
        try:
            r = http_get("https://steamspy.com/api.php",
                         params={"request": "all", "page": page})
            if r.status_code != 200:
                log.warning(f"  steamspy page {page} returned {r.status_code}, skip")
                continue
            for k, v in r.json().items():
                if not v.get("name"):
                    continue
                appid = int(k)
                if appid in seen:
                    continue
                seen.add(appid)
                pool.append({
                    "appid": appid,
                    "name": v["name"],
                    "reviews_estimate": int(v.get("positive", 0)) + int(v.get("negative", 0)),
                })
            time.sleep(0.3)
        except Exception as e:
            log.warning(f"  steamspy page {page} failed: {e}")
    log.info(f"steamspy pool size: {len(pool)}")
    return pool


# ---------- bucket-fair sample ----------
def bucket_of(n: int) -> int:
    for i, (lo, hi, _) in enumerate(BUCKETS):
        if lo <= n < hi:
            return i
    return len(BUCKETS) - 1


def bucket_fair_sample(pool: list[dict], per_bucket: int, seed: int) -> list[dict]:
    """依 reviews_estimate 分桶,每桶 deterministic shuffle 後取前 per_bucket 款。
    確保即使 SteamSpy 池子被熱門款淹沒,每桶仍有公平採樣。"""
    by_bucket: list[list[dict]] = [[] for _ in BUCKETS]
    for p in pool:
        n = p["reviews_estimate"]
        if MIN_REVIEWS <= n <= MAX_REVIEWS:
            by_bucket[bucket_of(n)].append(p)

    rng = random.Random(seed)
    sampled: list[dict] = []
    for i, b in enumerate(by_bucket):
        rng.shuffle(b)
        take = b[:per_bucket]
        sampled.extend(take)
        log.info(f"bucket {chr(65+i)} ({BUCKETS[i][2]}): {len(b)} candidates → take {len(take)}")
    return sampled


# ---------- per-game fetch ----------
def fetch_appdetails(appid: int, lang: str) -> Optional[dict]:
    """打 /api/appdetails?appids=X&l=LANG,回傳 details dict 或 None。
    對齊 app.py:233-243 的取法。"""
    try:
        r = http_get(
            "https://store.steampowered.com/api/appdetails",
            params={"appids": appid, "l": lang},
        )
        d = r.json()
        node = d.get(str(appid), {})
        if not node.get("success"):
            return None
        return node.get("data")
    except Exception as e:
        log.debug(f"  appdetails {appid}/{lang} failed: {e}")
        return None


def fetch_review_count(appid: int) -> Optional[int]:
    """打 /appreviews/{appid} 拿 query_summary.total_reviews。對齊 app.py:244-254。"""
    try:
        r = http_get(
            f"https://store.steampowered.com/appreviews/{appid}",
            params={"json": 1, "num_per_page": 0, "purchase_type": "all", "language": "all"},
        )
        return r.json().get("query_summary", {}).get("total_reviews")
    except Exception as e:
        log.debug(f"  reviews {appid} failed: {e}")
        return None


def hero_video_url(details: dict) -> Optional[str]:
    """直譯 app.py:295-306 — 解析 trailer URL。
    優先序:legacy mp4 480 → webm 480 → akamai store_trailers 構造式。"""
    movies = details.get("movies") or []
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


def resolve_price(details: dict, free_label: str) -> str:
    """價格字串:有 price_overview 用 final_formatted、is_free 用本地化 free_label、否則 —"""
    if details.get("price_overview"):
        return details["price_overview"].get("final_formatted") or "—"
    if details.get("is_free"):
        return free_label
    return "—"


def build_lang_block(details: dict, free_label: str) -> dict:
    """組單一語言版本的 block(對齊 games.json schema 的 tc/en 內容)。"""
    return {
        "name": details.get("name") or "",
        "short_description": details.get("short_description") or "",
        "genres": [g["description"] for g in (details.get("genres") or []) if g.get("description")][:4],
        "release_date": (details.get("release_date") or {}).get("date", ""),
        "price": resolve_price(details, free_label),
        "developers": (details.get("developers") or [])[:2],
    }


def assemble_entry(appid: int, en: dict, tc: Optional[dict], rev: int) -> dict:
    """把英文 + 中文 details + 評論數組成 games.json 的單筆 entry。"""
    # screenshots: 取前 3 個 path_thumbnail
    shots = [s["path_thumbnail"] for s in (en.get("screenshots") or [])[:3] if s.get("path_thumbnail")]
    # 從英文 details 解析媒體(中英文 movies 通常一致)
    trailer = hero_video_url(en)
    return {
        "appid": appid,
        "reviews": rev,
        "bucket": bucket_of(rev),
        "header_image": en.get("header_image") or "",
        "screenshots": shots,
        "trailer_url": trailer,
        "en": build_lang_block(en, "Free"),
        "tc": build_lang_block(tc, "免費") if tc else build_lang_block(en, "Free"),
    }


# ---------- existing games.json reuse ----------
def load_existing() -> Optional[dict]:
    if not GAMES_JSON.exists():
        return None
    try:
        return json.loads(GAMES_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"existing games.json unreadable: {e}")
        return None


def needs_full_refresh(existing: Optional[dict]) -> bool:
    if not existing:
        return True
    last = existing.get("last_full_refresh")
    if not last:
        return True
    try:
        last_dt = dt.datetime.fromisoformat(last.rstrip("Z"))
    except ValueError:
        return True
    age = (dt.datetime.utcnow() - last_dt).days
    return age >= FULL_REFRESH_DAYS


# ---------- atomic write ----------
def write_atomic(path: Path, content: str) -> None:
    """先寫到 tmp 再 rename,避免半寫狀態。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", delete=False,
        dir=path.parent, prefix=path.stem + ".", suffix=".tmp",
    )
    try:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, path)
    finally:
        # 萬一 rename 失敗 tmp 還在
        if os.path.exists(tmp.name):
            try: os.unlink(tmp.name)
            except OSError: pass


# ---------- main ----------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0,
                        help="dev mode: 限制遊戲數,只抓 EN,輸出 games.dev.json")
    parser.add_argument("--seed", type=int, default=SAMPLE_SEED,
                        help="bucket-fair sample 的隨機種子")
    args = parser.parse_args()
    dev_mode = args.limit > 0

    out_path = GAMES_DEV_JSON if dev_mode else GAMES_JSON

    # 1. existing & full refresh check
    existing = None if dev_mode else load_existing()
    full_refresh = needs_full_refresh(existing)
    if dev_mode:
        log.info(f"DEV MODE: limit={args.limit}, output={out_path.name}")
    else:
        log.info(f"full_refresh={full_refresh} (FULL_REFRESH_DAYS={FULL_REFRESH_DAYS})")

    # 2. pool
    pool = fetch_steamspy_pool()
    if not pool:
        log.error("steamspy pool empty — abort, keep existing games.json")
        sys.exit(2)

    # 3. bucket-fair sample
    sampled = bucket_fair_sample(pool, PER_BUCKET_TARGET, args.seed)
    if dev_mode:
        sampled = sampled[:args.limit]
        log.info(f"DEV MODE truncated to {len(sampled)} games")

    # 4. per-game fetch
    last_by_id = {g["appid"]: g for g in (existing or {}).get("games", [])}
    games_out: list[dict] = []
    recent_window: list[bool] = []   # True=success, False=fail
    skipped_reuse = 0

    for i, p in enumerate(sampled):
        appid = p["appid"]
        if i and i % 50 == 0:
            log.info(f"progress {i}/{len(sampled)} (saved={len(games_out)} reused={skipped_reuse})")
            # 失敗率檢查
            if len(recent_window) >= 50 and (recent_window[-50:].count(False) / 50) > FAILURE_THRESHOLD:
                log.error(f"recent failure rate > {FAILURE_THRESHOLD:.0%} — likely Steam IP block, abort")
                sys.exit(3)

        # incremental reuse
        if not full_refresh and not dev_mode and appid in last_by_id:
            games_out.append(last_by_id[appid])
            skipped_reuse += 1
            continue

        en = fetch_appdetails(appid, "english")
        if not en:
            recent_window.append(False)
            time.sleep(RATE_LIMIT_SLEEP)
            continue
        tc = None
        if not dev_mode:
            tc = fetch_appdetails(appid, "tchinese")
        rev = fetch_review_count(appid)
        if rev is None:
            recent_window.append(False)
            time.sleep(RATE_LIMIT_SLEEP)
            continue
        if not (MIN_REVIEWS <= rev <= MAX_REVIEWS):
            recent_window.append(True)   # 成功取資料,只是不在範圍
            time.sleep(RATE_LIMIT_SLEEP)
            continue
        if not dev_mode and not tc:
            # tc 抓不到 → 兩語覆蓋率不足,丟掉(維持前端假設兩語都有)
            recent_window.append(False)
            time.sleep(RATE_LIMIT_SLEEP)
            continue
        if not en.get("name"):
            recent_window.append(False)
            time.sleep(RATE_LIMIT_SLEEP)
            continue

        games_out.append(assemble_entry(appid, en, tc, rev))
        recent_window.append(True)
        time.sleep(RATE_LIMIT_SLEEP)

    log.info(f"final games count: {len(games_out)} (reused={skipped_reuse})")

    # 5. bucket distribution log
    counts = [0, 0, 0, 0]
    for g in games_out:
        b = g.get("bucket", -1)
        if 0 <= b < 4:
            counts[b] += 1
    log.info("bucket distribution: " + " · ".join(
        f"{chr(65+i)}({BUCKETS[i][2]})={counts[i]}" for i in range(4)
    ))

    # 6. assemble + write
    games_payload = json.dumps(games_out, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    build_hash = hashlib.sha256(games_payload).hexdigest()[:6]
    now_iso = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    out = {
        "version": now_iso,
        "build_hash": build_hash,
        "count": len(games_out),
        "buckets": BUCKETS_META,
        "last_full_refresh": now_iso if full_refresh else (existing or {}).get("last_full_refresh", now_iso),
        "games": games_out,
    }
    write_atomic(out_path, json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    if not dev_mode:
        write_atomic(VERSION_TXT, build_hash + "\n")

    log.info(f"wrote {out_path} ({out_path.stat().st_size / 1024 / 1024:.2f} MB) build_hash={build_hash}")


if __name__ == "__main__":
    main()
