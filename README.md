# steam-guesser

看遊戲畫面、影片、metadata,猜 Steam 評論數落在哪個區間。Cyberpunk 風格、5 分鐘衝高分。

## Run

```
pip install -r requirements.txt
streamlit run app.py
```

或雙擊 `run.bat`。預設開在 http://localhost:8501

## 玩法

5 分鐘倒數,連答衝累積分數。每題從 4 個評論區間挑一個:

| 區間 | 標籤 |
| --- | --- |
| A | < 100 |
| B | 100 – 1K |
| C | 1K – 10K |
| D | > 10K |

計分:

| 距離正解 | 分數 |
| --- | --- |
| 完美命中 | +100 |
| 相鄰一格 | +50 |
| 更遠 | 0 |

時間到後進結算畫面(總分 / 完美數 / 相鄰數 / 失準數),自動比對個人最佳紀錄。

## 資料來源

- 題庫:SteamSpy `all`(前 5 頁 ≈ 5000 款),按桶分群隨機抽,確保 4 桶機率均等
- 詳情 / 評論:Steam Store API(`appdetails` + `appreviews`)
- 過濾條件:評論數 `[20, 30000]` —— 排除明顯的 3A 大作

題庫、歷史、個人最佳分數都存在 `~/.config/steam-guesser/`(本機,不會上傳)。
