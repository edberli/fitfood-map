#!/usr/bin/env python3
"""將研究結果（管道分隔文字）轉成 app 用嘅精選資料集。

輸入：raw/*.txt，每行
     區|店名|完整地址|分類|點解適合|來源網址

做嘅嘢：
  1. 去重（同名 + 同區）
  2. 地址 → 座標（Nominatim，1 req/sec，免費）
  3. 香港邊界檢查 —— 地理編碼跌出香港一律唔要
  4. 出 data/fit-places.json

冇座標嘅店唔會入檔 —— 個 app 靠距離排序，冇座標嘅記錄係廢嘅。
"""
import json, os, re, sys, time, urllib.parse, urllib.request, glob

SRC = '/Volumes/core/fitfood-data/raw'
DEST = '/Users/winstonli/Documents/fitfood-map/data/fit-places.json'
CACHE = '/Volumes/core/fitfood-data/geocode-cache.json'
UA = {'User-Agent': 'FitFoodMap/1.0 (dataset build)'}
HK = {'minLat': 22.13, 'maxLat': 22.58, 'minLng': 113.82, 'maxLng': 114.44}

MEAT_MAP = {'chicken': 'chicken', 'beef': 'beef', 'salad': 'none',
            'vegan': 'none', 'vegetarian': 'none', 'protein': 'other'}

# 香港地區名（長嘅行先，否則「尖沙咀」會被「尖沙」搶咗）
AREAS = sorted([
    '尖沙咀','旺角','油麻地','佐敦','深水埗','長沙灣','荔枝角','美孚','石硤尾',
    '紅磡','黃埔','土瓜灣','九龍城','何文田','觀塘','九龍灣','牛頭角','藍田','油塘',
    '新蒲崗','黃大仙','鑽石山','慈雲山','樂富','中環','上環','西環','金鐘','灣仔',
    '銅鑼灣','北角','鰂魚涌','太古','西灣河','筲箕灣','柴灣','香港仔','黃竹坑','赤柱',
    '荃灣','葵芳','葵涌','青衣','沙田','大圍','馬鞍山','大埔','上水','粉嶺','元朗',
    '天水圍','屯門','西貢','將軍澳','東涌','堅尼地城','西營盤'
], key=len, reverse=True)

cache = json.load(open(CACHE, encoding='utf-8')) if os.path.exists(CACHE) else {}

def _one(q):
    """打一次 Nominatim，回香港範圍內嘅座標，否則 None。"""
    params = urllib.parse.urlencode({'q': q, 'format': 'json', 'limit': 1})
    try:
        req = urllib.request.Request(f'https://nominatim.openstreetmap.org/search?{params}', headers=UA)
        d = json.load(urllib.request.urlopen(req, timeout=25))
    except Exception:
        d = []
    time.sleep(1.1)                      # Nominatim 使用守則：每秒最多一次
    if not d:
        return None
    lat, lng = float(d[0]['lat']), float(d[0]['lon'])
    if HK['minLat'] <= lat <= HK['maxLat'] and HK['minLng'] <= lng <= HK['maxLng']:
        return [round(lat, 6), round(lng, 6)]
    return None

def variants(addr):
    """香港地址由詳細到粗略嘅退化階梯。
    Nominatim 認唔到舖位級（「通菜街43號地下B舖」），但認得「通菜街43號」同「通菜街」。"""
    out = [addr]
    # 剪走舖位／樓層／單位尾巴，只留到「…N號」
    m = re.match(r'^(.*?\d+(?:-\d+[A-Za-z]?)?號)', addr)
    if m:
        out.append(m.group(1))
    # 淨返「街道名 + 地區」。地區前綴長度唔一（尖沙咀 3 字、旺角 2 字），
    # 所以要用已知地區表剝，唔可以靠字數估 —— 靠估會切成「咀海防道 / 尖沙」。
    area = ''
    rest = addr
    for a in AREAS:
        if addr.startswith(a):
            area, rest = a, addr[len(a):]
            break
    m2 = re.match(r'^([\u4e00-\u9fff]+?(?:街|道|路|里|巷|徑|坊|園))', rest)
    if m2:
        street = m2.group(1)
        if area:
            out.append(f'{street}, {area}, 香港')
        out.append(f'{street}, 香港')
    seen, uniq = set(), []
    for v in out:
        if v and v not in seen:
            seen.add(v); uniq.append(v)
    return uniq

def geocode(addr):
    """地址 → (lat,lng)。逐級退化去試；全部唔得回 None，唔會估。"""
    if addr in cache:
        return cache[addr]
    res = None
    for v in variants(addr):
        res = _one(v if v.endswith('香港') else f'{v}, 香港')
        if res:
            break
    cache[addr] = res
    json.dump(cache, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False)
    return res

def main():
    rows, seen = [], set()
    for f in sorted(glob.glob(f'{SRC}/*.txt')):
        for line in open(f, encoding='utf-8'):
            parts = [p.strip() for p in line.rstrip('\n').split('|')]
            if len(parts) < 5 or not parts[1] or not parts[2]:
                continue
            district, name, addr, cat = parts[0], parts[1], parts[2], parts[3].lower()
            why = parts[4] if len(parts) > 4 else ''
            src = parts[5] if len(parts) > 5 else ''
            # 地址太籠統（例如淨係「港島」「中環」）唔可以入 —— 地理編碼會落錯位。
            # 實測 Root Vegan 只寫「港島」，結果落咗去淺水灣。要有街道或者門牌先算數。
            if not re.search(r'[街道路里巷徑坊里村]|\d+號|Street|Road|Avenue', addr):
                print(f'  地址太籠統，剔走：{name}（{addr}）', file=sys.stderr)
                continue

            key = (re.sub(r'\W', '', name.lower()), district)
            if key in seen:
                continue
            seen.add(key)
            rows.append({'district': district, 'name': name, 'addr': addr,
                         'cat': cat, 'why': why, 'src': src})

    print(f'讀入 {len(rows)} 間（已去重）', file=sys.stderr)

    out, nogeo = [], []
    for i, r in enumerate(rows, 1):
        pos = geocode(r['addr'])
        if not pos:
            nogeo.append(r['name'])
            continue
        out.append({
            'n': r['name'], 'a': pos[0], 'o': pos[1], 'd': r['addr'],
            'r': r['district'],
            'm': MEAT_MAP.get(r['cat'], 'other'),
            's': 'best',                 # 呢個名單本身就係「揀出嚟啱健身」，所以全部 best
            'why': r['why'], 'src': r['src'],
        })
        if i % 20 == 0:
            print(f'  …{i}/{len(rows)}', file=sys.stderr)

    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    json.dump({'date': time.strftime('%Y-%m-%d'), 'places': out},
              open(DEST, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))

    from collections import Counter
    print(f'\n出檔 {len(out)} 間，{os.path.getsize(DEST)/1024:.0f} KB')
    print('分區：', dict(Counter(p["r"] for p in out)))
    print('分類：', dict(Counter(p["m"] for p in out)))
    if nogeo:
        print(f'\n地址轉唔到座標，冇入檔（{len(nogeo)} 間）：')
        for n in nogeo[:20]:
            print('  ·', n)

if __name__ == '__main__':
    main()
