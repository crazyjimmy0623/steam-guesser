# steam-guesser

看遊戲畫面、影片、metadata,猜 Steam 評論數落在哪個區間。5 分鐘衝高分。

## Play

- **靜態網頁版** (GitHub Pages): https://crazyjimmy0623.github.io/steam-guesser/
- **Streamlit 線上版**: https://steam-guesser-t8jjjcq3oczgp5sw9usir2.streamlit.app/

## 玩法

5 分鐘倒數,連答衝累積分數。每題從 4 個評論區間挑一個:

| 區間 | 標籤 |
| --- | --- |
| A | 10 – 100 |
| B | 100 – 1K |
| C | 1K – 10K |
| D | 10K – 50K |

計分:

| 距離正解 | 分數 |
| --- | --- |
| 完美命中 | +100 |
| 相鄰一格 | +50 |
| 更遠 | 0 |

時間到後進結算畫面(總分 / 完美數 / 相鄰數 / 失準數),自動比對個人最佳紀錄。

## 架構

兩條路線並存,代碼共用同一份 CSS 動畫設計:

```
steam-guesser/
├── app.py                     # Streamlit 版本(本機 / streamlit cloud 用)
├── docs/                      # 靜態網頁版本(GitHub Pages 服務)
│   ├── index.html
│   ├── style.css              # 從 app.py CSS_TEMPLATE 移植
│   ├── app.js                 # 狀態機(idle/playing/revealed/ended)
│   ├── modules/               # bgm / particles / timer / sfx / i18n
│   └── data/
│       ├── games.json         # CI 預烘焙的遊戲資料(雙語、3000 款)
│       └── version.txt        # cachebust hash
├── scripts/
│   ├── build_pool.py          # 烘焙 games.json 的 Python 腳本
│   └── requirements-build.txt
└── .github/workflows/
    └── build-pool.yml         # 每週自動跑 build_pool.py 並 commit
```

靜態版本資料流:GitHub Actions 每週呼叫 Steam API(SteamSpy + Store + Reviews) → 烘成 `docs/data/games.json` → push main → GitHub Pages 自動 republish。前端純靜態,瀏覽器只 fetch JSON 不打 Steam API,避開 CORS。

## 本機開發

### Streamlit 路線

```
pip install -r requirements.txt
streamlit run app.py
# 或雙擊 run.bat;預設 http://localhost:8501
```

### 靜態網頁路線

```
# 烘一份小型 dev 資料(~50 款 × EN only,30 秒搞定)
pip install -r scripts/requirements-build.txt
python scripts/build_pool.py --limit 50

# 起本機 server
cd docs
python -m http.server 8080
# 開 http://localhost:8080
```

`docs/data/games.json` 的完整版本(3000 款雙語)會由 CI 寫入並 commit;`games.dev.json` 是本機開發用的小檔,被 `.gitignore` 排除。

## 部署到 GitHub Pages(一次性設定)

1. Push 此 repo 到 GitHub
2. Settings → Pages → Source = "Deploy from a branch"
3. Branch = `main`,Folder = `/docs`
4. Save → 等 1 分鐘第一次部署
5. Actions tab → 手動跑一次 `build-pool` workflow(否則 `docs/data/games.json` 還是 dev sample)

之後每週日 17:00 UTC 自動重抓資料 commit;也可隨時去 Actions 頁面手動 dispatch。

## 資料來源

- 題庫:SteamSpy `all`(10 頁 ≈ 10000 款),按 review 數預估桶分群、桶公平採樣 750/桶
- 詳情 / 評論:Steam Store API(`appdetails` + `appreviews`),雙語(`l=english` + `l=tchinese`)
- 過濾條件:評論數 `[10, 50000]`(對齊 [steamle.com](https://steamle.com/) 的桶區間)

Streamlit 版本把資料快取在 `~/.config/steam-guesser/`(本機,不會上傳)。
靜態版本在 localStorage(`sg_history` / `sg_best` / `sg_lang`)。
