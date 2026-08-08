#!/usr/bin/env python3
"""洗乾淨全港食肆資料集。

做四件事，每件都輸出點解剷咗／標咗：
  1. 剷走 OSM 重複記錄（同名 + 極近）
  2. 剷走明確已結業（disused:/was:/abandoned: 前綴，或者 opening_hours=closed）
  3. 標記「資料極薄」（冇地址／電話／網站／營業時間）
  4. 標記「好耐冇人更新」（最後編輯超過 N 年）—— 需要 hk-meta.json

輸出：data/hk-places.json（帶 q 欄 = 資料可信度標記）
"""
import json, math, os, re, sys, collections, datetime

SRC = '/Volumes/core/fitfood-data'
DEST = '/Users/winstonli/Documents/fitfood-map/data'
STALE_YEARS = 6          # 超過呢個年期冇人改就標記
DUP_METRES = 40          # 同名兼咁近，當係同一筆記錄重複

NOW = datetime.datetime.utcnow()

def norm(n):
    n = (n or '').lower()
    n = re.sub(r'[（(][^)）]*[)）]', '', n)
    return re.sub(r'[^a-z0-9一-鿿]', '', n)

def metres(p, q):
    R = 6371000
    dla = math.radians(q[0] - p[0]); dlo = math.radians(q[1] - p[1])
    h = (math.sin(dla / 2) ** 2 + math.cos(math.radians(p[0])) *
         math.cos(math.radians(q[0])) * math.sin(dlo / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(h))

# ---------- 載入 ----------
raw = json.load(open(f'{SRC}/hk-all.json', encoding='utf-8'))
classes = json.load(open(f'{DEST}/name-classes.json', encoding='utf-8'))

# 最後編輯時間（可有可冇）
edited = {}
meta_path = f'{SRC}/hk-meta.json'
if os.path.exists(meta_path):
    try:
        for e in json.load(open(meta_path, encoding='utf-8'))['elements']:
            if e.get('timestamp'):
                edited[(e['type'], e['id'])] = e['timestamp'][:10]
    except Exception as err:
        print(f'（讀唔到 hk-meta.json，跳過陳舊度分析：{err}）', file=sys.stderr)

# ---------- 1. 攤平 + 剷走明確結業 ----------
CLOSED_PREFIX = ('disused:', 'was:', 'abandoned:', 'removed:', 'demolished:')
rows, closed = [], 0

for el in raw['elements']:
    t = el.get('tags') or {}
    name = (t.get('name') or '').strip()
    if not name:
        continue
    lat = el.get('lat') or (el.get('center') or {}).get('lat')
    lng = el.get('lon') or (el.get('center') or {}).get('lon')
    if lat is None or lng is None:
        continue

    if any(k.startswith(CLOSED_PREFIX) for k in t) or t.get('opening_hours') == 'closed':
        closed += 1
        continue

    rows.append({'name': name, 'key': norm(name), 'lat': lat, 'lng': lng,
                 'tags': t, 'type': el['type'], 'id': el['id']})

# ---------- 2. 剷走重複 ----------
by_key = collections.defaultdict(list)
for i, r in enumerate(rows):
    by_key[r['key']].append(i)

drop = set()
for key, idxs in by_key.items():
    if len(idxs) < 2:
        continue
    for a in range(len(idxs)):
        for b in range(a + 1, len(idxs)):
            i, j = idxs[a], idxs[b]
            if i in drop or j in drop:
                continue
            if metres((rows[i]['lat'], rows[i]['lng']), (rows[j]['lat'], rows[j]['lng'])) <= DUP_METRES:
                # 留資料多嗰筆
                score = lambda r: sum(1 for k in ('addr:street', 'phone', 'contact:phone',
                                                 'website', 'contact:website', 'opening_hours',
                                                 'cuisine') if r['tags'].get(k))
                drop.add(j if score(rows[i]) >= score(rows[j]) else i)

# ---------- 3./4. 出檔 ----------
RICH = ('addr:street', 'addr:housenumber', 'phone', 'contact:phone',
        'website', 'contact:website', 'opening_hours')
places, thin_n, stale_n = [], 0, 0

for i, r in enumerate(rows):
    if i in drop:
        continue
    t = r['tags']
    addr = ' '.join(filter(None, [t.get('addr:housenumber'), t.get('addr:street'),
                                  t.get('addr:district')])).strip()

    p = {'n': r['name'], 'a': round(r['lat'], 6), 'o': round(r['lng'], 6)}
    if t.get('name:en') and t['name:en'] != r['name']: p['e'] = t['name:en']
    if t.get('cuisine'): p['c'] = t['cuisine']
    if addr: p['d'] = addr
    if t.get('phone') or t.get('contact:phone'): p['t'] = t.get('phone') or t['contact:phone']
    if t.get('website') or t.get('contact:website'): p['w'] = t.get('website') or t['contact:website']
    if t.get('opening_hours'): p['h'] = t['opening_hours']
    if t.get('amenity'): p['y'] = t['amenity']

    cls = classes.get(r['name'])
    if cls:
        p['m'], p['s'] = cls['m'], cls['h']

    # q = 可信度標記：thin（資料極薄）、stale（好耐冇更新）
    flags = []
    if not any(t.get(k) for k in RICH):
        flags.append('thin'); thin_n += 1
    ts = edited.get((r['type'], r['id']))
    if ts:
        p['u'] = ts
        age = (NOW - datetime.datetime.strptime(ts, '%Y-%m-%d')).days / 365.25
        if age >= STALE_YEARS:
            flags.append('stale'); stale_n += 1
    if flags:
        p['q'] = flags

    places.append(p)

os.makedirs(DEST, exist_ok=True)
stamp = (raw.get('osm3s') or {}).get('timestamp_osm_base', '')[:10]
json.dump({'date': stamp, 'places': places},
          open(f'{DEST}/hk-places.json', 'w', encoding='utf-8'),
          ensure_ascii=False, separators=(',', ':'))

size = os.path.getsize(f'{DEST}/hk-places.json') / 1024
print(f'原始有名記錄   {len(rows) + closed}')
print(f'  剷走 明確結業  {closed}')
print(f'  剷走 重複記錄  {len(drop)}')
print(f'留低           {len(places)} 間，{size:.0f} KB')
print(f'  標記 資料極薄  {thin_n} ({thin_n * 100 // max(len(places),1)}%)')
print(f'  標記 {STALE_YEARS} 年冇更新 {stale_n} ({stale_n * 100 // max(len(places),1)}%)')
