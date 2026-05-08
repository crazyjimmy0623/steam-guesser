# steam-guesser

看遊戲畫面與描述，猜 Steam 評論數 / 銷量，自我打分。

## Run

```
pip install -r requirements.txt
streamlit run app.py
```

預設開在 http://localhost:8501

## 計分

`score = max(0, 100 - 50 × |log10(guess) - log10(actual)|)`

完全猜中 100；差一個數量級 50；差兩個 0。

## 銷量推算

評論數 × 40 是 Boxleiter 法則中段值。獨立遊戲常見 30–60，3A 可達 80+。
想更準的話可改 `BOXLEITER_MULTIPLIER`，或之後依類型分倍率。

## 資料來源

- 題庫：SteamSpy `all` top 1000
- 詳情 / 評論：Steam Store API（`appdetails` + `appreviews`）

題庫與歷史紀錄都存在 `~/.config/steam-guesser/`。
