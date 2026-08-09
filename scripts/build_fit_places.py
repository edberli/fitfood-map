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
import json, math, os, re, sys, time, urllib.parse, urllib.request, glob

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
RCACHE_PATH = CACHE.replace('geocode-cache', 'reverse-cache')
rcache = json.load(open(RCACHE_PATH, encoding='utf-8')) if os.path.exists(RCACHE_PATH) else {}

def metres(p, q):
    R = 6371000
    dla = math.radians(q[0] - p[0]); dlo = math.radians(q[1] - p[1])
    h = (math.sin(dla / 2) ** 2 + math.cos(math.radians(p[0])) *
         math.cos(math.radians(q[0])) * math.sin(dlo / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(h))

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

def reverse(lat, lng):
    k = f'{lat},{lng}'
    if k in rcache:
        return rcache[k]
    q = urllib.parse.urlencode({'lat': lat, 'lon': lng, 'format': 'json',
                                'zoom': '16', 'accept-language': 'zh'})
    try:
        req = urllib.request.Request(f'https://nominatim.openstreetmap.org/reverse?{q}', headers=UA)
        j = json.load(urllib.request.urlopen(req, timeout=25))
        out = j.get('display_name', '')
    except Exception:
        out = ''
    time.sleep(1.1)
    rcache[k] = out
    json.dump(rcache, open(RCACHE_PATH, 'w', encoding='utf-8'), ensure_ascii=False)
    return out

def area_of(addr):
    """由地址抽出地區名（最長匹配先）。"""
    return next((a for a in AREAS if addr.startswith(a) or a in addr), None)

DISTRICTS = ['中西區','灣仔區','東區','南區','油尖旺區','深水埗區','九龍城區','黃大仙區',
             '觀塘區','荃灣區','葵青區','沙田區','大埔區','北區','元朗區','屯門區','西貢區','離島區']

def street_candidates(addr):
    """由地址抽街名，連埋「剝走頭幾個字」嘅變體。
    因為地區前綴長度唔一，「田灣興和街」剝唔乾淨就對唔到反查嘅「興和街」。"""
    out = []
    for m in re.finditer(r'([\u4e00-\u9fff]{2,10}?(?:街|道|路|里|巷|徑|坊))', addr):
        st = m.group(1)
        for cut in range(0, min(4, len(st) - 1)):
            if len(st[cut:]) >= 2:
                out.append(st[cut:])
    return out

def district_of_addr(addr):
    """由地址嘅地區名推返十八區。"""
    A2D = {'尖沙咀':'油尖旺區','旺角':'油尖旺區','油麻地':'油尖旺區','佐敦':'油尖旺區','太子':'油尖旺區',
      '深水埗':'深水埗區','長沙灣':'深水埗區','荔枝角':'深水埗區','石硤尾':'深水埗區',
      '紅磡':'九龍城區','黃埔':'九龍城區','土瓜灣':'九龍城區','九龍城':'九龍城區','何文田':'九龍城區','愛民':'九龍城區','啟德':'九龍城區',
      '觀塘':'觀塘區','九龍灣':'觀塘區','藍田':'觀塘區','油塘':'觀塘區',
      '新蒲崗':'黃大仙區','黃大仙':'黃大仙區','鑽石山':'黃大仙區',
      '中環':'中西區','上環':'中西區','西營盤':'中西區','堅尼地城':'中西區',
      '灣仔':'灣仔區','銅鑼灣':'灣仔區',
      '北角':'東區','鰂魚涌':'東區','太古':'東區','筲箕灣':'東區','柴灣':'東區',
      '香港仔':'南區','黃竹坑':'南區','田灣':'南區',
      '荃灣':'荃灣區','葵涌':'葵青區','葵芳':'葵青區','青衣':'葵青區',
      '沙田':'沙田區','石門':'沙田區','大圍':'沙田區','馬鞍山':'沙田區','火炭':'沙田區',
      '大埔':'大埔區','上水':'北區','粉嶺':'北區','元朗':'元朗區','天水圍':'元朗區',
      '屯門':'屯門區','西貢':'西貢區','將軍澳':'西貢區','東涌':'離島區'}
    for a in AREAS:
        if a in addr:
            return A2D.get(a)
    return None

def coord_matches_address(lat, lng, addr):
    """反查座標，對返**街道名**（唔係地區名）。

    唔用地區名嘅原因：香港分區界線重疊得好犀利，對地區會大量誤殺 ——
    「登龍街」橫跨銅鑼灣同灣仔、「彩虹道」橫跨鑽石山同新蒲崗、
    「馬頭圍道」反查出嚟叫鶴園。實測對地區會剷走 14 間全部正確嘅店。

    對街道名就準：真錯個案係「上環厚生街」落咗去筆架山歌和老街 —— 街名對唔上。"""
    rev = reverse(lat, lng)
    if not rev:
        return True, '（反查失敗，放行）'

    # 街名對到就放行（最強證據）
    for st in street_candidates(addr):
        if st in rev:
            return True, rev

    # 街名對唔到，退而求其次對十八區。兩樣都唔對先當錯 ——
    # 咁樣先揪得到 La Rotisserie（上環 → 九龍城區）呢種真錯，
    # 又唔會誤殺「麼地道 → 漆咸道南」呢啲門口喺街角嘅個案。
    d = district_of_addr(addr)
    if d and d in rev:
        return True, rev
    if not d:
        return True, rev + '（推唔到十八區，放行）'
    return False, rev

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

    out, nogeo, mismatch = [], [], []
    for i, r in enumerate(rows, 1):
        pos = geocode(r['addr'])
        if not pos:
            nogeo.append(r['name'])
            continue

        ok, rev = coord_matches_address(pos[0], pos[1], r['addr'])
        if not ok:
            mismatch.append((r['name'], r['addr'], rev))
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

    # 第三重：離群點檢查。
    # 街名對到都可以錯得好遠 —— 「大埔汀角路17號」同「汀角路大美督」街名一樣，
    # 但相距 7km。長街道嘅街道級回退會落喺錯嘅一端，反查對街名捉唔到。
    # 所以再比較同區其他店：如果距同區最近一間都超過 4km，當落錯位。
    from collections import defaultdict as _dd
    by_area = _dd(list)
    for p in out:
        a = next((x for x in AREAS if x in p['d']), None)
        if a:
            by_area[a].append(p)
    outliers = []
    for a, ps in by_area.items():
        if len(ps) < 3:
            continue                      # 同區得一兩間，冇參照，唔判
        for p in ps:
            dmin = min(metres((p['a'], p['o']), (q['a'], q['o'])) for q in ps if q is not p)
            if dmin > 4000:
                outliers.append((p, a, round(dmin)))
    for p, a, d in outliers:
        out.remove(p)

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
    if outliers:
        print(f'\n離群點（距同區其他店 >4km），冇入檔（{len(outliers)} 間）：')
        for p, a, d in outliers:
            print(f'  · {p["n"]} — 地址寫「{a}」但距同區最近一間 {d}m')
    if mismatch:
        print(f'\n座標同地址地區對唔上，冇入檔（{len(mismatch)} 間）：')
        for n, a, rev in mismatch:
            print(f'  · {n} — 地址「{a[:24]}」但落咗去 {rev[:40]}')

if __name__ == '__main__':
    main()
