import re
import requests
from urllib.parse import unquote_plus, urlparse, parse_qs, urlencode, urlunparse
from dataclasses import dataclass, field
from typing import Callable, List, Optional

GOOGLE_MAP_SHARE_URL_REGEX = r"https://maps\.app\.goo\.gl/[a-zA-Z0-9?_=]+"
GOOGLE_MAP_PLACE_URL_REGEX = r"https://www\.google\.[^/]+/maps/place/(?P<name>[^/@]+)/@(?P<lat>-?\d+\.\d+),(?P<lon>-?\d+\.\d+),\d+z"
PLACES_API_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
PLACES_NEARBY_API_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

@dataclass
class ShopInfo:
    name: str
    lat: float
    lon: float
    place_key: str = field(default='')

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
        return requests.get(self._remove_tracking_params(url), allow_redirects=True)

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
        return ShopInfo(name=result['name'], lat=loc['lat'], lon=loc['lng'])

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
        return ShopInfo(
            name=result['name'],
            lat=loc['lat'],
            lon=loc['lng']
        )

    def _extract_shop_info(self, url: str, html: str) -> Optional[ShopInfo]:
        combined = url + '\n' + html

        # パターン1: /maps/place/NAME/@lat,lon 形式
        match = re.search(GOOGLE_MAP_PLACE_URL_REGEX, combined)
        if match:
            name = self._unquote_unicode(match.group("name"))
            lat, lon = self._extract_coords(combined)
            if lat is None:
                lat, lon = float(match.group("lat")), float(match.group("lon"))
            return ShopInfo(name=name, lat=lat, lon=lon)

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
            place_key = self._extract_place_key(response.url)
            if is_cached and place_key and is_cached(place_key):
                continue
            info = self._extract_shop_info(response.url, response.text)
            if info:
                info.place_key = place_key
                infos.append(info)
            else:
                print(f"URLから情報を取得できませんでした: {url} -> {response.url}")
        return infos
