# steam-guesser

看遊戲畫面與描述，猜 Steam 評論數落在哪個對數區間，比準度。

## Run

```
pip install -r requirements.txt
streamlit run app.py
```

或雙擊 `run.bat`。預設開在 http://localhost:8501

## 玩法

8 個對數區間：`<50`、`50–200`、`200–1K`、`1K–5K`、`5K–20K`、`20K–100K`、`100K–500K`、`500K+`

點哪個就直接送出。計分：

| 距離正解 | 分數 |
| --- | --- |
| 完全命中 | 100 |
| 差 1 格 | 50 |
| 差 2 格 | 20 |
| 更遠 | 0 |

## 資料來源

- 題庫：SteamSpy `all` top 1000
- 詳情 / 評論：Steam Store API（`appdetails` + `appreviews`）

題庫與歷史紀錄存在 `~/.config/steam-guesser/`。
