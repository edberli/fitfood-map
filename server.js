const express = require('express');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3001;

const OVERPASS_TIMEOUT_MS = 15000;
// 實測過 overpass.private.coffee 由香港連唔到、overpass.osm.jp 憑證過期，所以唔放入嚟
const OVERPASS_UPSTREAMS = [
  'https://overpass-api.de/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter'
];

// 主檔係根目錄嗰個 index.html，唔係 public/ 嗰份舊 copy
app.use(express.static(__dirname));
app.use(express.urlencoded({ extended: false, limit: '1mb' }));

// Proxy Overpass API (avoid CORS issues on frontend)
// 前端會 POST data=<query>（同直接打公共 server 一樣），亦保留 GET ?query= 方便手動測試
app.all('/api/overpass', async (req, res) => {
  const query = req.body?.data || req.body?.query || req.query.query;

  if (!query) {
    return res.status(400).json({ error: 'query is required' });
  }

  let lastStatus = 0;
  let lastError = null;

  // 逐個 mirror 試。公共 Overpass 成日 504，單一 server 唔夠穩。
  for (const upstream of OVERPASS_UPSTREAMS) {
    try {
      const response = await fetch(upstream, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          // 冇 User-Agent 嘅話 Overpass 會直接回 406
          'User-Agent': 'FitFoodMap/1.0'
        },
        body: `data=${encodeURIComponent(query)}`,
        // 唔設 timeout 嘅話，一個 hang 住嘅 mirror 會拖死成個請求
        signal: AbortSignal.timeout(OVERPASS_TIMEOUT_MS)
      });
      const contentType = response.headers.get('content-type') || '';
      const text = await response.text();

      if (response.ok && contentType.includes('json') && !text.startsWith('<')) {
        return res.type('application/json').send(text);
      }
      lastStatus = response.status;
    } catch (err) {
      lastError = err;
    }
  }

  // 全部撻先回 502。唔好扮成空結果，否則用戶會以為附近真係冇店。
  console.error('Overpass 全部 upstream 失敗:', lastStatus, lastError || '');
  res.status(502).json({
    error: '所有 Overpass server 都連唔到',
    upstreamStatus: lastStatus || undefined
  });
});

// Proxy Nominatim search (for text-based search)
app.get('/api/search', async (req, res) => {
  const { q, lat, lng } = req.query;

  if (!q) {
    return res.status(400).json({ error: 'q is required' });
  }

  const url = new URL('https://nominatim.openstreetmap.org/search');
  url.searchParams.set('q', q);
  url.searchParams.set('format', 'json');
  url.searchParams.set('limit', '20');
  url.searchParams.set('addressdetails', '1');
  if (lat && lng) {
    url.searchParams.set('viewbox', `${+lng - 0.02},${+lat + 0.02},${+lng + 0.02},${+lat - 0.02}`);
    url.searchParams.set('bounded', '1');
  }

  try {
    const response = await fetch(url.toString(), {
      headers: { 'User-Agent': 'FitFoodMap/1.0' }
    });
    const data = await response.json();
    res.json(data);
  } catch (err) {
    console.error('Nominatim error:', err);
    res.status(500).json({ error: 'Failed to search' });
  }
});

app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

app.listen(PORT, () => {
  console.log(`FitFood Map running at http://localhost:${PORT}`);
});
