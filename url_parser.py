import re
import requests
from urllib.parse import unquote_plus
from dataclasses import dataclass
from typing import List

GOOGLE_MAP_SHARE_URL_REGEX = r"https://maps.app.goo.gl/[a-zA-Z0-9]+"
GOOGLE_MAP_REDIRECTED_URL_REGEX = r"https://www.google.co.jp/maps/place/(?P<name>[^/]+)/@(?P<lat>-?\d+\.\d+),(?P<lon>-?\d+\.\d+),\d+z/(?P<remain>[^/]+)"

@dataclass
class ShopInfo:
    name: str
    lat: float
    lon: float

class URLParser:
    def __init__(self):
        pass
    # 外部URLへのアクセスなので後でインフラ層に切り出す
    def _get_redirected_url(self, url):
        response = requests.get(url, allow_redirects=True)
        return response.url
    def unquote_unicode(self, s):
        return unquote_plus(s, encoding='utf-8', errors='replace')
    def parse_google_map_share_url(self, content) -> List[ShopInfo]:
        matched = re.findall(GOOGLE_MAP_SHARE_URL_REGEX, content)
        infos = []
        for url in matched:
            match = re.search(GOOGLE_MAP_REDIRECTED_URL_REGEX, self._get_redirected_url(url))
            if match:
                name = self.unquote_unicode(match.group("name"))
                remain = match.group("remain")
                lat = re.search(r"!3d(-?\d+\.\d+)", remain).group(1)
                lon = re.search(r"!4d(-?\d+\.\d+)", remain).group(1)
                infos.append(ShopInfo(name=name, lat=float(lat), lon=float(lon)))
        return infos