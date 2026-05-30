import re
import requests
from urllib.parse import unquote_plus, urlparse, parse_qs, urlencode, urlunparse
from dataclasses import dataclass, field
from typing import Callable, List, Optional

GOOGLE_MAP_SHARE_URL_REGEX = r"https://maps\.app\.goo\.gl/[a-zA-Z0-9?_=]+"
GOOGLE_MAP_PLACE_URL_REGEX = r"https://www\.google\.[^/]+/maps/place/(?P<name>[^/@]+)/@(?P<lat>-?\d+\.\d+),(?P<lon>-?\d+\.\d+),\d+z"
PLACES_API_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
PLACES_NEARBY_API_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

# Places API v1 (textsearch) は汎用タイプしか返さないため、店名キーワードを第1優先にする
NAME_GENRE_PATTERNS = [
    (re.compile(r'居酒屋|酒場|もつ焼き?|串焼き?居酒', re.IGNORECASE), '居酒屋'),
    (re.compile(r'ラーメン|らーめん|拉麺', re.IGNORECASE), 'ラーメン'),
    (re.compile(r'寿司|すし|鮨|回転寿司', re.IGNORECASE), '寿司'),
    (re.compile(r'焼肉|焼き肉|やきにく', re.IGNORECASE), '焼肉'),
    (re.compile(r'焼鳥|焼き鳥|やきとり|炭火焼鳥|串鳥', re.IGNORECASE), '焼鳥'),
    (re.compile(r'天ぷら|てんぷら|天麩羅', re.IGNORECASE), '天ぷら'),
    (re.compile(r'とんかつ|トンカツ', re.IGNORECASE), 'とんかつ'),
    (re.compile(r'蕎麦|そば', re.IGNORECASE), '蕎麦'),
    (re.compile(r'うどん', re.IGNORECASE), 'うどん'),
    (re.compile(r'餃子|ぎょうざ|ギョウザ|gyoza', re.IGNORECASE), '中華'),
    (re.compile(r'中華|中国料理|チャイニーズ', re.IGNORECASE), '中華'),
    (re.compile(r'台湾料理|台湾', re.IGNORECASE), '台湾料理'),
    (re.compile(r'韓国料理|韓国|コリアン|korean', re.IGNORECASE), '韓国料理'),
    (re.compile(r'ビリヤニ|biryani', re.IGNORECASE), 'インド料理'),
    (re.compile(r'インド料理|インド|indian', re.IGNORECASE), 'インド料理'),
    (re.compile(r'カレー|curry', re.IGNORECASE), 'カレー'),
    (re.compile(r'タイ料理|タイ|thai', re.IGNORECASE), 'タイ料理'),
    (re.compile(r'ベトナム料理|ベトナム|vietnamese|pho|フォー', re.IGNORECASE), 'ベトナム料理'),
    (re.compile(r'タコス|taco|メキシカン|mexican', re.IGNORECASE), 'メキシカン'),
    (re.compile(r'ピザ|pizza', re.IGNORECASE), 'ピザ'),
    (re.compile(r'パスタ|イタリアン|italian', re.IGNORECASE), 'イタリアン'),
    (re.compile(r'ビストロ|bistro|フレンチ|french', re.IGNORECASE), 'フレンチ'),
    (re.compile(r'ステーキ|steak', re.IGNORECASE), 'ステーキ'),
    (re.compile(r'バーガー|burger|ハンバーガー', re.IGNORECASE), 'バーガー'),
    (re.compile(r'和食|日本料理|割烹', re.IGNORECASE), '和食'),
    (re.compile(r'定食|食堂', re.IGNORECASE), '定食'),
    (re.compile(r'丼|どんぶり', re.IGNORECASE), '丼'),
    (re.compile(r'鍋|しゃぶしゃぶ|すき焼き', re.IGNORECASE), '鍋料理'),
    (re.compile(r'串|くし料理', re.IGNORECASE), '串料理'),
    (re.compile(r'ベーカリー|bakery|パン屋|パン工房', re.IGNORECASE), 'ベーカリー'),
    (re.compile(r'カフェ|cafe|coffee|コーヒー', re.IGNORECASE), 'カフェ'),
    (re.compile(r'バー|bar\b|cocktail|カクテル', re.IGNORECASE), 'バー'),
]

# Places API types フォールバック（meal_takeaway は機能フラグのため除外）
GENRE_MAP = {
    'ramen_restaurant': 'ラーメン',
    'sushi_restaurant': '寿司',
    'japanese_restaurant': '和食',
    'chinese_restaurant': '中華',
    'korean_restaurant': '韓国料理',
    'italian_restaurant': 'イタリアン',
    'french_restaurant': 'フレンチ',
    'american_restaurant': 'アメリカン',
    'hamburger_restaurant': 'バーガー',
    'pizza_restaurant': 'ピザ',
    'indian_restaurant': 'インド料理',
    'thai_restaurant': 'タイ料理',
    'vietnamese_restaurant': 'ベトナム料理',
    'steak_house': 'ステーキ',
    'seafood_restaurant': 'シーフード',
    'izakaya_restaurant': '居酒屋',
    'restaurant': 'レストラン',
    'bar': 'バー',
    'cafe': 'カフェ',
    'bakery': 'ベーカリー',
    'night_club': 'クラブ',
}
GENRE_SKIP = frozenset({'food', 'point_of_interest', 'establishment', 'store', 'geocode'})

@dataclass
class ShopInfo:
    name: str
    lat: float
    lon: float
    place_key: str = field(default='')
    url: str = field(default='')
    genre: str = field(default='')

class URLParser:
    def __init__(self, geocoding_api_key: str = None):
        self._geocoding_api_key = geocoding_api_key

    def _remove_tracking_params(self, url: str) -> str:
        parsed = urlparse(url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        for key in ('g_st', 'g_ep', 'shh', 'lucs', 'skid', 'entry'):
            params.pop(key, None)
        return urlunparse(parsed._replace(query=urlencode(params, doseq=True)))

    # 外部URLへのアクセスなので後でインフラ層に切り出す
    def _get_response(self, url: str) -> requests.Response:
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
        }
        return requests.get(self._remove_tracking_params(url), allow_redirects=True, headers=headers)

    def _unquote_unicode(self, s: str) -> str:
        return unquote_plus(s, encoding='utf-8', errors='replace')

    def _extract_coords(self, text: str) -> tuple[Optional[float], Optional[float]]:
        lat_m = re.search(r'!3d(-?\d+\.\d+)', text)
        lon_m = re.search(r'!4d(-?\d+\.\d+)', text)
        if lat_m and lon_m:
            return float(lat_m.group(1)), float(lon_m.group(1))

        # /maps?q= 形式（GPSナビ共有など）のHTML内の APP_INITIALIZATION_STATE から抽出
        # フォーマット: [[[scale, lon, lat], ...
        init_m = re.search(r'APP_INITIALIZATION_STATE=\[\[\[[\d.]+,(-?\d+\.\d+),(-?\d+\.\d+)\]', text)
        if init_m:
            return float(init_m.group(2)), float(init_m.group(1))

        return None, None

    def _extract_place_key(self, url: str) -> str:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        # /maps?q= 形式: ftid が安定した場所識別子
        if parsed.path == '/maps' and 'ftid' in params:
            return params['ftid'][0]

        # /maps/place/NAME/data= 形式: data セグメントの CID を使用
        cid_m = re.search(r'!1s(0x[0-9a-f]+:0x[0-9a-f]+)', url)
        if cid_m:
            return cid_m.group(1)

        # /maps/place/NAME/@lat,lon 形式: 座標から生成
        match = re.search(GOOGLE_MAP_PLACE_URL_REGEX, url)
        if match:
            lat = round(float(match.group("lat")), 5)
            lon = round(float(match.group("lon")), 5)
            return f"{lat},{lon}"

        return ''

    def _genre_from_name(self, name: str) -> str:
        for pattern, genre in NAME_GENRE_PATTERNS:
            if pattern.search(name):
                return genre
        return ''

    def _extract_genre(self, types: list) -> str:
        for t in types:
            if t in GENRE_MAP:
                return GENRE_MAP[t]
        for t in types:
            if t not in GENRE_SKIP:
                return t
        return ''

    def _extract_from_sorry_redirect(self, sorry_url: str) -> Optional[ShopInfo]:
        """google.com/sorry/index へのリダイレクト時に continue パラメータから店情報を取得する"""
        sorry_qs = parse_qs(urlparse(sorry_url).query)
        if 'continue' not in sorry_qs:
            return None
        continue_url = unquote_plus(sorry_qs['continue'][0])
        c_qs = parse_qs(urlparse(continue_url).query)
        ftid = c_qs.get('ftid', [''])[0]
        q_value = c_qs.get('q', [''])[0]
        if not q_value or not self._geocoding_api_key:
            return None
        info = self._find_place(q_value)
        if info:
            info.place_key = ftid
        return info

    def _find_place_nearby(self, lat: float, lon: float) -> Optional[ShopInfo]:
        resp = requests.get(
            PLACES_NEARBY_API_URL,
            params={
                'location': f"{lat},{lon}",
                'rankby': 'distance',
                'key': self._geocoding_api_key,
                'language': 'ja'
            }
        )
        results = resp.json().get('results', [])
        if not results:
            return None
        result = results[0]
        loc = result['geometry']['location']
        name = result['name']
        genre = self._genre_from_name(name) or self._extract_genre(result.get('types', []))
        return ShopInfo(name=name, lat=loc['lat'], lon=loc['lng'], genre=genre)

    def _find_place(self, query: str) -> Optional[ShopInfo]:
        resp = requests.get(
            PLACES_API_URL,
            params={'query': query, 'key': self._geocoding_api_key, 'language': 'ja'}
        )
        results = resp.json().get('results', [])
        if not results:
            return None
        result = results[0]
        loc = result['geometry']['location']
        name = result['name']
        genre = self._genre_from_name(name) or self._extract_genre(result.get('types', []))
        return ShopInfo(name=name, lat=loc['lat'], lon=loc['lng'], genre=genre)

    def _extract_shop_info(self, url: str, html: str) -> Optional[ShopInfo]:
        combined = url + '\n' + html

        # パターン1: /maps/place/NAME/@lat,lon 形式
        match = re.search(GOOGLE_MAP_PLACE_URL_REGEX, combined)
        if match:
            name = self._unquote_unicode(match.group("name"))
            lat, lon = self._extract_coords(combined)
            if lat is None:
                lat, lon = float(match.group("lat")), float(match.group("lon"))
            genre = ''
            if self._geocoding_api_key:
                enriched = self._find_place(name)
                if enriched:
                    genre = enriched.genre
            return ShopInfo(name=name, lat=lat, lon=lon, genre=genre)

        # パターン1b: /maps/place/NAME/data= 形式（GPS共有など、座標なし）
        data_match = re.search(r'https://www\.google\.[^/]+/maps/place/(?P<name>[^/]+)/data=', url)
        if data_match:
            name_raw = self._unquote_unicode(data_match.group("name"))
            if self._geocoding_api_key:
                return self._find_place(name_raw)
            lat, lon = self._extract_coords(combined)
            if lat is not None:
                return ShopInfo(name=name_raw, lat=lat, lon=lon)

        # パターン2: /maps?q= 形式（GPSナビ共有など）
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if parsed.path == '/maps' and 'q' in params:
            address = self._unquote_unicode(params['q'][0])

            # Geocoding API が設定されていれば使用
            if self._geocoding_api_key:
                return self._find_place(address)

            # フォールバック: HTML解析
            og_m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html)
            if not og_m:
                og_m = re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:title"', html)
            name = ''
            if og_m:
                name = re.sub(r'\s*[-‐]\s*Google\s*(マップ|Maps)\s*$', '', og_m.group(1)).strip()
            if not name or name in ('Google Maps', 'Google マップ'):
                name = address

            lat, lon = self._extract_coords(combined)
            if lat is not None and name:
                return ShopInfo(name=name, lat=lat, lon=lon)

        # パターン3: /maps?ftid= 形式（q パラメータなしのGPSナビ共有）
        if parsed.path == '/maps' and 'ftid' in params:
            og_m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html)
            if not og_m:
                og_m = re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:title"', html)
            name = ''
            if og_m:
                name = re.sub(r'\s*[-‐]\s*Google\s*(マップ|Maps)\s*$', '', og_m.group(1)).strip()

            lat, lon = self._extract_coords(combined)

            if lat is not None and name and name not in ('Google Maps', 'Google マップ'):
                return ShopInfo(name=name, lat=lat, lon=lon)

            # og:title が使えない場合は Nearby Search で座標から店名を取得
            if lat is not None and self._geocoding_api_key:
                return self._find_place_nearby(lat, lon)

        return None

    def parse_google_map_share_url(self, content: str, is_cached: Optional[Callable[[str], bool]] = None) -> List[ShopInfo]:
        matched = re.findall(GOOGLE_MAP_SHARE_URL_REGEX, content)
        infos = []
        for url in matched:
            response = self._get_response(url)

            if '/sorry/' in response.url:
                # ボット検出でリダイレクトされた場合: continue URL から ftid を取り出してキャッシュ確認
                sorry_qs = parse_qs(urlparse(response.url).query)
                if 'continue' in sorry_qs:
                    c_qs = parse_qs(urlparse(unquote_plus(sorry_qs['continue'][0])).query)
                    ftid = c_qs.get('ftid', [''])[0]
                    if is_cached and ftid and is_cached(ftid):
                        continue
                info = self._extract_from_sorry_redirect(response.url)
                if info is None:
                    print(f"URLから情報を取得できませんでした: {url} -> {response.url}")
                else:
                    info.url = url
                    infos.append(info)
                continue

            place_key = self._extract_place_key(response.url)
            if is_cached and place_key and is_cached(place_key):
                continue
            info = self._extract_shop_info(response.url, response.text)
            if info:
                info.place_key = place_key
                info.url = url
                infos.append(info)
            else:
                print(f"URLから情報を取得できませんでした: {url} -> {response.url}")
        return infos
