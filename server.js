const express = require('express');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3001;

app.use(express.static(path.join(__dirname, 'public')));

// Proxy Overpass API (avoid CORS issues on frontend)
app.get('/api/overpass', async (req, res) => {
  const { query } = req.query;

  if (!query) {
    return res.status(400).json({ error: 'query is required' });
  }

  try {
    const response = await fetch('https://overpass-api.de/api/interpreter', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: `data=${encodeURIComponent(query)}`
    });
    const data = await response.json();
    res.json(data);
  } catch (err) {
    console.error('Overpass API error:', err);
    res.status(500).json({ error: 'Failed to fetch from Overpass API' });
  }
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
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`FitFood Map running at http://localhost:${PORT}`);
});
