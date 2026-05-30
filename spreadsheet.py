import re
import gspread
from google.oauth2.service_account import Credentials
from url_parser import ShopInfo
import json
import os
from dotenv import load_dotenv

load_dotenv()

# 経度138°E未満 → 大阪圏 (umeda シート)、以上 → 東京圏 (main シート)
OSAKA_LNG_THRESHOLD = 138.0

class GoogleSpreadsheetClient:
    def __init__(self):
        self._scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        self._credentials = Credentials.from_service_account_file("credentials.json", scopes=self._scope)
        self._gspread_client = gspread.authorize(self._credentials)
        self._spreadsheet = self._gspread_client.open_by_url(os.getenv("SPREADSHEET_URL"))

        self._worksheet_main  = self._spreadsheet.worksheet("main")
        self._worksheet_umeda = self._get_or_create_umeda_worksheet()

        self._cache_file = "shop_cache.json"
        self._cache = self._load_cache()

    def _get_or_create_umeda_worksheet(self):
        try:
            return self._spreadsheet.worksheet("umeda")
        except gspread.exceptions.WorksheetNotFound:
            ws = self._spreadsheet.add_worksheet(title="umeda", rows=1000, cols=4)
            ws.append_row(["name", "lat", "lon", "timestamp"])
            print("umeda シートを新規作成しました。")
            return ws

    def _worksheet_for(self, shop: ShopInfo):
        return self._worksheet_umeda if shop.lon < OSAKA_LNG_THRESHOLD else self._worksheet_main

    def _is_place_key(self, s: str) -> bool:
        return bool(
            re.match(r'^-?\d+\.\d+,-?\d+\.\d+$', s) or
            re.match(r'^0x[0-9a-f]+:0x[0-9a-f]+$', s)
        )

    def _build_cache_from_spreadsheet(self) -> set:
        keys = set()
        for ws in [self._worksheet_main, self._worksheet_umeda]:
            for r in ws.get_all_records():
                try:
                    lat = round(float(r['lat']), 5)
                    lon = round(float(r['lon']), 5)
                    keys.add(f"{lat},{lon}")
                except (KeyError, ValueError):
                    pass
        return keys

    def _load_cache(self) -> set:
        if os.path.exists(self._cache_file):
            with open(self._cache_file, "r") as f:
                data = json.load(f)
            if data and self._is_place_key(data[0]):
                return set(data)
        cache = self._build_cache_from_spreadsheet()
        with open(self._cache_file, "w") as f:
            json.dump(list(cache), f, ensure_ascii=False, indent=4)
        return cache

    def _save_cache(self):
        with open(self._cache_file, "w") as f:
            json.dump(list(self._cache), f, ensure_ascii=False, indent=4)

    def is_cached(self, place_key: str) -> bool:
        return place_key in self._cache

    def get_all_records(self):
        return self._worksheet_main.get_all_records()

    def append_row(self, row: ShopInfo, timestamp: str) -> bool:
        coords_key = f"{round(row.lat, 5)},{round(row.lon, 5)}"
        if row.place_key in self._cache or coords_key in self._cache:
            return False
        ws = self._worksheet_for(row)
        ws.append_row([row.name, row.lat, row.lon, timestamp])
        if row.place_key:
            self._cache.add(row.place_key)
        self._cache.add(coords_key)
        self._save_cache()
        return True
