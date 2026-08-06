# FitFood Map — 健身飲食地圖

搵附近高蛋白、雞肉、健康餐廳嘅單頁地圖 app（香港）。

## 點跑

```bash
npm install      # 只係 server.js 需要 express
npm start        # http://localhost:3001
```

或者用零依賴版本（唔使 npm install）：

```bash
node serve.mjs 3001
```

兩個 server 都 **serve repo 根目錄**，入口係根目錄嘅 `index.html`。

## 檔案

| 檔案 | 用途 |
|---|---|
| `index.html` | 主檔。HTML + CSS + JS 全部喺入面，Leaflet 由 CDN 載 |
| `data/curated-chains.json` | 手動整理嘅連鎖店名單（8 個品牌、54 間分店） |
| `server.js` | Express server，帶 `/api/overpass` 同 `/api/search` proxy |
| `serve.mjs` | 零依賴 Node server，功能同上 |
| `public/index.html` | **舊 copy，已經冇用。** 兩個 server 以前 serve 呢個目錄，而家改咗 serve 根目錄 |

## 資料源

- **OpenStreetMap / Overpass API** — 即時搜附近 3km 嘅餐廳，按 `cuisine` tag 同店名 pattern 分類
- **`data/curated-chains.json`** — 人手整理嘅連鎖店。OSM 資料唔齊，呢個名單補返香港健身人士常去嘅店

前端會**優先行同源 proxy**（`api/overpass`、`api/search`）。冇 proxy 嘅話（例如直接開 HTML 檔）自動跌落去直接打公共 server。

Overpass 公共 server 經常過載，所以排咗 4 個 mirror 逐個試，每個試兩次。全部失敗會顯示「搜尋失敗」同重試掣 —— **唔會**扮成「附近冇店」。

## 加新店

改 `data/curated-chains.json` 就得，唔使郁 code：

```json
{
  "brand": "品牌名",
  "categories": ["chicken", "protein", "healthy"],
  "description": "營養角度嘅簡介",
  "branches": [
    { "name": "品牌名 (分店)", "address": "地址", "lat": 22.3, "lng": 114.2 }
  ]
}
```

`categories` 可揀：`chicken`（雞肉）、`protein`（高蛋白）、`healthy`（健康）、`salad`（沙律）。

## 已知限制

- `data/curated-chains.json` 嘅座標係人手輸入，分店有變唔會自動更新
- 「高蛋白」分類靠 curated 名單同店名 pattern，OSM 冇對應 tag，所以純 OSM 結果會偏少
- 定位靠瀏覽器 GPS，失敗時要人手輸入地址
