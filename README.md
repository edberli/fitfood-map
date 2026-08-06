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

- **OpenStreetMap / Overpass API** — 一次過攞 3km 內嘅餐廳，按 `cuisine` tag 同店名 pattern 分類
- **`data/curated-chains.json`** — 人手整理嘅連鎖店。OSM 資料唔齊，呢個名單補返香港健身人士常去嘅店

## 「附近」點計

Overpass 一次過攞 3km，之後喺前端逐層收窄，唔使為咗擴大範圍再打多次 API：

| 層 | 條件 |
|---|---|
| 800m | 預設。約 10 分鐘步程，夠 8 間就停喺呢層 |
| 1.5km | 800m 內少過 8 間先擴大 |
| 3km | 1.5km 內都唔夠先用 |

每個篩選各自計自己嘅半徑（例如「沙律」800m 內冇，會自動放到 3km），面板頂會寫住實際範圍。

## 分類分兩層

- **明確分類** — `chicken`、`protein`、`healthy`、`salad`，有彩色標籤，四個篩選掣對應呢四類
- **「可健康」（`maybe`）** — 唔係主打健康，但揀得啱一樣食得健康：日式、韓式燒肉、越南、泰式、粥品、點心、海鮮、三文治等。標籤刻意用淡灰色，只喺「全部」入面出現

之前淨係認明確分類，結果 95% 附近餐廳被剷走 —— 觀塘 500m 內 48 間有名餐廳只認到 5 間，要拉到 3km 先湊夠數，所以個「附近」一啲都唔附近。加咗中間層之後同一位置 500m 內有 8 間、800m 內 13 間。

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

`categories` 可揀：`chicken`（雞肉）、`protein`（高蛋白）、`healthy`（健康）、`salad`（沙律）。`maybe` 係俾 OSM 結果自動判斷用嘅，curated 名單唔應該用。

## 已知限制

- `data/curated-chains.json` 嘅座標係人手輸入，分店有變唔會自動更新
- 部分 curated 座標記錄咗商場位置而唔係實際舖位，所以有 5 組分店（10 間）共用同一個座標，距離會有幾百米誤差。同一間店如果 OSM 都有，去重會保留 OSM 嗰個較準嘅位置（名要對得上，而且相距 500m 內）
- 「高蛋白」分類靠 curated 名單同店名 pattern，OSM 冇對應 tag，所以純 OSM 結果會偏少
- 「可健康」係按 cuisine tag 同店名推測，一定有睇漏同誤中，所以標籤刻意做得淡
- 定位靠瀏覽器 GPS，失敗時要人手輸入地址；用地址搜尋嘅話個中心點係地區中心，唔係你實際企喺邊
