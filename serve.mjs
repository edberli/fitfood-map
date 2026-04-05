import { createServer } from 'http';
import { readFile, stat } from 'fs/promises';
import { join, extname } from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const publicDir = join(__dirname, 'public');
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

async function proxyOverpass(req, res) {
  let query;
  if (req.method === 'POST') {
    const body = await readBody(req);
    try { query = JSON.parse(body).query; } catch { query = body; }
  } else {
    const url = new URL(req.url, 'http://localhost');
    query = url.searchParams.get('query');
  }

  if (!query) {
    res.writeHead(400, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'query is required' }));
    return;
  }
  try {
    const r = await fetch('https://overpass-api.de/api/interpreter', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: `data=${encodeURIComponent(query)}`
    });
    const contentType = r.headers.get('content-type') || '';
    const data = await r.text();
    // If Overpass returns XML error page, return empty results
    if (!contentType.includes('json') || data.startsWith('<?xml') || data.startsWith('<')) {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ elements: [] }));
      return;
    }
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(data);
  } catch (err) {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ elements: [] }));
  }
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
  const fullPath = join(publicDir, decodeURIComponent(filePath));

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
    // SPA fallback
    try {
      const data = await readFile(join(publicDir, 'index.html'));
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(data);
    } catch {
      res.writeHead(404);
      res.end('Not found');
    }
  }
}).listen(port, () => console.log(`FitFood Map running at http://localhost:${port}`));
