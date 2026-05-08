# Cloudflare Worker — global leaderboard

提供全球排行榜的 GET/POST API,讓 GitHub Pages 上的前端可以撈跟送分數。

## 一次性部署

### 1. 註冊 Cloudflare(免費,無卡)

到 https://dash.cloudflare.com/sign-up 註冊一個帳號(Email + 密碼即可,不需要綁卡或網域)。

### 2. 安裝 wrangler CLI

```bash
npm install -g wrangler
wrangler login
```

`wrangler login` 會開瀏覽器讓你授權,授權完關掉視窗就好。

### 3. 建 KV namespace(資料儲存空間)

```bash
cd worker
wrangler kv:namespace create LB
```

終端機會印出類似:

```
🌀 Creating namespace with title "steam-guesser-leaderboard-LB"
✨ Success!
[[kv_namespaces]]
binding = "LB"
id = "abc123def456..."
```

把 `id` 貼到 `worker/wrangler.toml`,取代裡面的 `YOUR_KV_NAMESPACE_ID`。

### 4. 部署 Worker

```bash
wrangler deploy
```

成功的話會印出 Worker 公開網址,例如:

```
https://steam-guesser-leaderboard.your-username.workers.dev
```

### 5. 把網址貼到前端設定

打開 `docs/data/config.json`,把 `leaderboard_api` 改成上面那個網址(不要結尾的斜線):

```json
{
  "leaderboard_api": "https://steam-guesser-leaderboard.your-username.workers.dev"
}
```

Commit + push,GitHub Pages 自動 republish,前端就會啟用全球排行榜。

## 本機測試

```bash
cd worker
wrangler dev
# Worker 會跑在 http://localhost:8787
# 在 docs/data/config.json 裡先改成 http://localhost:8787 試
```

## API 規格

### `GET /top`

```json
[
  {"name": "...", "score": 420, "picks": 8, "perfects": 4, "nears": 0, "misses": 4, "ts": 1731234567},
  ...
]
```

最多 100 筆,依 `score` desc 排序;同分時較新者在前。

### `POST /submit`

Body:
```json
{"name": "Jimmy", "score": 420, "picks": 8, "perfects": 4, "nears": 0, "misses": 4}
```

驗證:
- `name`: 1-16 字元,移除控制字元
- `score`: 0-2000
- `picks`: 1-30(3 分鐘合理上限)
- `perfects + nears + misses === picks`
- `score === perfects*100 + nears*50`
- 同 IP 60 秒只能送一次

成功回:
```json
{"ok": true, "rank": 4, "top": [...], "entry_ts": 1731234567}
```

失敗回:
```json
{"error": "rate_limited"}    // 或 invalid_score / counts_mismatch / ...
```

## 反作弊說明

前端開源,有心人能用 DevTools 改 `state.session_score` 後送,Worker 不會察覺(因為 score 跟 perfects/nears 算術一致)。

要更嚴格的話可以:
- 加 HMAC 簽章驗證(secret 在 Worker 端,前端傳 game token)
- 加 hCaptcha / Turnstile(Cloudflare 自家免費 captcha)
- 比對最高合理分數(玩 30 題 perfect = 3000 但我們已壓 2000)
- 名稱 deny list(粗口 / 假名)

目前這個版本是**輕量擋意外亂打**,不是反 hardcore 作弊。對小型娛樂專案夠用。

## 操作 / 維運

### 看現在排行榜

```bash
wrangler kv:key get --binding=LB lb:top
```

### 清空排行榜

```bash
wrangler kv:key delete --binding=LB lb:top
```

### 看 logs

```bash
wrangler tail
```

### 用量監控

Cloudflare dashboard → Workers & Pages → 點你的 worker → Analytics 看請求量。

免費額度:
- Workers 100K req/day
- KV 100K read/day, 1K write/day, 1GB 儲存
- 對小遊戲完全夠用,單日 100 個玩家、每人玩 5 場 = 500 寫入,還在額度內
