#!/usr/bin/env python3
"""由 Overpass 全港 dump 整出前端用嘅精簡資料集。

輸入：hk-all.json（Overpass 原始 dump）
     ~/Downloads/offload-staging/fitfood-classify/*.md（LLM 分類結果）
     index.tsv（編號 → 店名 對照）
輸出：data/hk-places.json    前端直接載，唔使打 Overpass
     data/name-classes.json 店名 → 分類對照表
"""
import json, os, glob, sys

SRC = '/Volumes/core/fitfood-data'
DEST = '/Users/winstonli/Documents/fitfood-map/data'
CLS_DIR = os.path.expanduser('~/Downloads/offload-staging/fitfood-classify')

MEAT_OK = {'none', 'chicken', 'beef', 'pork', 'seafood', 'other', 'unknown'}
HEALTH_OK = {'best', 'normal', 'happy', 'unknown'}

# ---------- 1. 分類結果 ----------
idx2name = {}
for line in open(f'{SRC}/index.tsv', encoding='utf-8'):
    parts = line.rstrip('\n').split('\t')
    if len(parts) >= 2:
        idx2name[parts[0]] = parts[1]

classes, bad, missing = {}, 0, 0
for f in sorted(glob.glob(f'{CLS_DIR}/*.md')):
    for line in open(f, encoding='utf-8'):
        parts = line.rstrip('\n').split('\t')
        if len(parts) != 3:
            continue
        idx, meat, health = (p.strip() for p in parts)
        name = idx2name.get(idx)
        if not name:
            missing += 1
            continue
        if meat not in MEAT_OK or health not in HEALTH_OK:
            bad += 1
            continue
        classes[name] = {'m': meat, 'h': health}

print(f'分類：{len(classes)} / {len(idx2name)} 個店名'
      f'（格式錯 {bad}、對唔到編號 {missing}）')

# ---------- 2. 精簡 POI ----------
raw = json.load(open(f'{SRC}/hk-all.json', encoding='utf-8'))
places, skipped = [], 0

for el in raw['elements']:
    t = el.get('tags') or {}
    name = (t.get('name') or '').strip()
    if not name:
        skipped += 1
        continue
    lat = el.get('lat') or (el.get('center') or {}).get('lat')
    lng = el.get('lon') or (el.get('center') or {}).get('lon')
    if lat is None or lng is None:
        skipped += 1
        continue

    addr = ' '.join(filter(None, [
        t.get('addr:housenumber'), t.get('addr:street'), t.get('addr:district')
    ])).strip()

    # 用短 key，4,000+ 條記錄慳到幾百 KB
    p = {'n': name, 'a': round(lat, 6), 'o': round(lng, 6)}
    if t.get('name:en') and t['name:en'] != name: p['e'] = t['name:en']
    if t.get('cuisine'): p['c'] = t['cuisine']
    if addr: p['d'] = addr
    if t.get('phone') or t.get('contact:phone'): p['t'] = t.get('phone') or t['contact:phone']
    if t.get('website') or t.get('contact:website'): p['w'] = t.get('website') or t['contact:website']
    if t.get('opening_hours'): p['h'] = t['opening_hours']
    if t.get('amenity'): p['y'] = t['amenity']

    cls = classes.get(name)
    if cls:
        p['m'], p['s'] = cls['m'], cls['h']
    places.append(p)

os.makedirs(DEST, exist_ok=True)
stamp = (raw.get('osm3s') or {}).get('timestamp_osm_base', '')[:10]
json.dump({'date': stamp, 'places': places},
          open(f'{DEST}/hk-places.json', 'w', encoding='utf-8'),
          ensure_ascii=False, separators=(',', ':'))
json.dump(classes, open(f'{DEST}/name-classes.json', 'w', encoding='utf-8'),
          ensure_ascii=False, separators=(',', ':'))

from collections import Counter
sized = os.path.getsize(f'{DEST}/hk-places.json') / 1024
have_cls = sum(1 for p in places if 's' in p)
print(f'POI：{len(places)} 間（跳過 {skipped}），{sized:.0f} KB')
print(f'有分類：{have_cls} / {len(places)} ({have_cls*100//max(len(places),1)}%)')
print('健康分佈：', dict(Counter(p.get("s", "—") for p in places)))
print('肉類分佈：', dict(Counter(p.get("m", "—") for p in places)))
