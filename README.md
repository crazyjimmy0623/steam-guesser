# steam-guesser

看遊戲畫面、影片、metadata,猜 Steam 評論數落在哪個區間。

## Play

**https://crazyjimmy0623.github.io/steam-guesser/**

## 玩法

兩個模式自選:
- **計時挑戰**:3 分鐘倒數衝高分
- **無盡模式**:沒倒數,玩到累自己按 END RUN 結算

每題看遊戲影片 + 截圖 + 描述 + 類型 + 開發商 + 售價,從 4 個評論區間挑一個:

| 區間 | 標籤 |
| --- | --- |
| A | 10 – 100 |
| B | 100 – 1K |
| C | 1K – 10K |
| D | 10K – 50K |

計分:

| 距離正解 | 分數 |
| --- | --- |
| 完美命中 | +100 (×combo) |
| 相鄰一格 | +50 |
| 更遠 | 0 |

連續 perfect 啟動倍率(2 連 ×1.5 / 3 連 ×2 / 5 連 ×3),斷一次清零。鍵盤可按 `A/B/C/D` 直接選桶,`Enter` 推進階段。

## 架構

純靜態前端 + GitHub Actions 預烘資料 + Cloudflare Worker 全球榜:

```
steam-guesser/
├── docs/                       # GitHub Pages 服務根目錄
│   ├── index.html
│   ├── style.css               # 完整 CSS(主題、CRT、curtain、進場動畫)
│   ├── app.js                  # 狀態機 (idle/playing/revealed/ended) + 互動
│   ├── modules/
│   │   ├── i18n.js             # 繁中 / EN 翻譯字典
│   │   ├── bgm.js              # WebAudio 環境音 drone
│   │   ├── particles.js        # 滑鼠粒子 grid
│   │   ├── timer.js            # 計時挑戰倒數 widget + onTick callback
│   │   ├── sfx.js              # hover/press/clock/tick/score 音效
│   │   ├── fx.js               # perfect flash、miss shake、TIME UP、toast
│   │   └── colorize.js         # 從 header 圖抽主色 → CSS variable
│   ├── data/
│   │   ├── games.json          # CI 預烘:3000 款雙語
│   │   ├── version.txt         # cachebust hash
│   │   └── config.json         # leaderboard_api 設定
│   └── assets/favicon.svg
├── scripts/
│   ├── build_pool.py           # 烘 games.json 的 Python 腳本
│   └── requirements-build.txt  # requests, tenacity
├── worker/
│   ├── index.js                # Cloudflare Worker 全球排行榜 API
│   ├── wrangler.toml
│   └── README.md               # Worker 部署說明
└── .github/workflows/
    └── build-pool.yml          # 每週自動烘 + commit
```

資料流:GitHub Actions 每週呼叫 Steam API(SteamSpy + Store + Reviews) → 烘成 `docs/data/games.json` → push master → GitHub Pages 自動 republish。前端純靜態載入,瀏覽器不打 Steam API,避開 CORS。

## 本機開發

```bash
# 1. 烘一份小型 dev 資料(~50 款 × EN only,30 秒)
pip install -r scripts/requirements-build.txt
python scripts/build_pool.py --limit 50

# 2. 起本機 server
cd docs
python -m http.server 8080
# 開 http://localhost:8080
```

`docs/data/games.json` 的完整版本(3000 款雙語)由 CI 寫入並 commit;`games.dev.json` 是本機開發用的小檔,被 `.gitignore` 排除。

## 部署到 GitHub Pages(一次性設定)

1. Settings → Pages → Source = "Deploy from a branch"
2. Branch = `master`,Folder = `/docs`
3. Save → 等 ~1 分鐘第一次部署
4. Actions tab → 手動跑 `build-pool` workflow 烘 3000 款真資料

之後每週日 17:00 UTC 自動重抓 + commit;也可隨時去 Actions 頁面手動 dispatch。

## 全球排行榜(Cloudflare Worker)

跟著 [`worker/README.md`](worker/README.md) 走 5 步驟,部署免費 Cloudflare Worker(KV-backed,IP throttle + 資料驗證),把 URL 填進 `docs/data/config.json` 的 `leaderboard_api`。

不部署也 OK — 結算頁仍有「個人最佳」(本機 top 10)、「本場遊戲」(連 Steam 商店頁)、「成就」、「分享」等所有功能。

## 資料來源

- 題庫:SteamSpy `all`(10 頁 ≈ 10000 款),按 review 數預估分桶、桶公平採樣 750/桶
- 詳情 / 評論:Steam Store API(`appdetails` + `appreviews`),雙語(`l=english` + `l=tchinese`)
- 過濾條件:評論數 `[10, 50000]`(對齊 [steamle.com](https://steamle.com/) 的桶區間)

玩家本機資料(歷史、最佳、模式偏好、玩家暱稱)存 localStorage(`sg_history` / `sg_best` / `sg_mode` / `sg_player_name` 等)。
