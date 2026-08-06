import { createServer } from 'http';
import { readFile, stat } from 'fs/promises';
import { join, extname } from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
// 主檔係 repo 根目錄嗰個 index.html，唔係 public/ 嗰份舊 copy
const rootDir = __dirname;
const port = parseInt(process.argv[2] || '3001');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css',
  '.js': 'application/javascript',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon'
};

function readBody(req) {
  return new Promise((resolve) => {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => resolve(body));
  });
}

const OVERPASS_TIMEOUT_MS = 15000;
// 實測過 overpass.private.coffee 由香港連唔到、overpass.osm.jp 憑證過期，所以唔放入嚟
const OVERPASS_UPSTREAMS = [
  'https://overpass-api.de/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter'
];

// 逐個 mirror 試。公共 Overpass 成日 504，單一 server 唔夠穩。
async function fetchOverpassUpstream(query) {
  let lastStatus = 0;
  let lastError = null;

  for (const upstream of OVERPASS_UPSTREAMS) {
    try {
      const r = await fetch(upstream, {
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
      const contentType = r.headers.get('content-type') || '';
      const text = await r.text();

      if (r.ok && contentType.includes('json') && !text.startsWith('<')) {
        return { ok: true, text };
      }
      lastStatus = r.status;
    } catch (err) {
      lastError = err;
    }
  }

  return { ok: false, lastStatus, lastError };
}

async function proxyOverpass(req, res) {
  let query;
  if (req.method === 'POST') {
    const body = await readBody(req);
    const contentType = req.headers['content-type'] || '';
    if (contentType.includes('form-urlencoded')) {
      // 前端送 data=<overpass query>，同直接打公共 server 一樣格式
      query = new URLSearchParams(body).get('data');
    } else {
      try { query = JSON.parse(body).query; } catch { query = body; }
    }
  } else {
    const url = new URL(req.url, 'http://localhost');
    query = url.searchParams.get('query');
  }

  if (!query) {
    res.writeHead(400, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'query is required' }));
    return;
  }
  // 以前所有錯誤都扮成「冇結果」回 200，令前端分唔到「搜尋失敗」同「附近冇店」。
  // 而家全部 mirror 都撻先回 502，前端就知要顯示錯誤而唔係空結果。
  const result = await fetchOverpassUpstream(query);

  if (!result.ok) {
    console.error('Overpass 全部 upstream 失敗:', result.lastStatus, result.lastError || '');
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      error: '所有 Overpass server 都連唔到',
      upstreamStatus: result.lastStatus || undefined,
      detail: result.lastError ? String(result.lastError) : undefined
    }));
    return;
  }

  res.writeHead(200, { 'Content-Type': 'application/json' });
  res.end(result.text);
}

async function proxySearch(url, res) {
  const q = url.searchParams.get('q');
  if (!q) {
    res.writeHead(400, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'q is required' }));
    return;
  }
  const lat = url.searchParams.get('lat');
  const lng = url.searchParams.get('lng');
  const nUrl = new URL('https://nominatim.openstreetmap.org/search');
  nUrl.searchParams.set('q', q);
  nUrl.searchParams.set('format', 'json');
  nUrl.searchParams.set('limit', '20');
  nUrl.searchParams.set('addressdetails', '1');
  if (lat && lng) {
    nUrl.searchParams.set('viewbox', `${+lng - 0.02},${+lat + 0.02},${+lng + 0.02},${+lat - 0.02}`);
    nUrl.searchParams.set('bounded', '1');
  }
  try {
    const r = await fetch(nUrl.toString(), {
      headers: { 'User-Agent': 'FitFoodMap/1.0' }
    });
    const data = await r.text();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(data);
  } catch (err) {
    res.writeHead(500, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Search failed' }));
  }
}

createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');

  // API routes
  if (url.pathname === '/api/overpass') return proxyOverpass(req, res);
  if (url.pathname === '/api/search') return proxySearch(url, res);

  // Static files
  let filePath = url.pathname === '/' ? '/index.html' : url.pathname;
  const fullPath = join(rootDir, decodeURIComponent(filePath));

  try {
    const s = await stat(fullPath);
    if (s.isDirectory()) {
      res.writeHead(404);
      res.end('Not found');
      return;
    }
    const data = await readFile(fullPath);
    res.writeHead(200, { 'Content-Type': MIME[extname(fullPath)] || 'application/octet-stream' });
    res.end(data);
  } catch {
    // 靜態資源（.json、.css 之類）搵唔到就實話實說回 404，
    // 唔好扮 SPA 回 index.html —— 否則前端會攞住一段 HTML 當 JSON parse。
    const ext = extname(fullPath);
    if (ext && ext !== '.html') {
      res.writeHead(404, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Not found', path: filePath }));
      return;
    }
    // SPA fallback
    try {
      const data = await readFile(join(rootDir, 'index.html'));
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(data);
    } catch {
      res.writeHead(404);
      res.end('Not found');
    }
  }
}).listen(port, () => console.log(`FitFood Map running at http://localhost:${port}`));
