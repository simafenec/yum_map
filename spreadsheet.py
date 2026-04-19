import gspread
from google.oauth2.service_account import Credentials
from url_parser import ShopInfo
import json
import os


class GoogleSpreadsheetClient:
    def __init__(self):
        self._scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        self._credentials = Credentials.from_service_account_file("credentials.json", scopes=self._scope)
        self._gspread_client = gspread.authorize(self._credentials)
        self._spreadsheet = self._gspread_client.open_by_url("https://docs.google.com/spreadsheets/d/1JCH0ZoYHMAf6Muxq6aRsCE86j7YEjgisv_U9zMeZJXo/edit?usp=sharing")
        self._worksheet = self._spreadsheet.sheet1

        self._cache_file = "shop_cache.json"
        self._cache = self._load_cache()

    def _load_cache(self):
        if os.path.exists(self._cache_file):
            with open(self._cache_file, "r") as f:
                return set(json.load(f))
        return set({r["name"] for r in self.get_all_records()})
    def _save_cache(self):
        with open(self._cache_file, "w") as f:
            json.dump(list(self._cache), f, ensure_ascii=False, indent=4)
    def get_all_records(self):
        return self._worksheet.get_all_records()
    def append_row(self, row : ShopInfo, timestamp : str) -> bool:
        if row.name in self._cache:
            return False
        self._worksheet.append_row(
            [
                row.name, 
                row.lat, 
                row.lon,
                timestamp
            ]
        )
        self._cache.add(row.name)
        self._save_cache()
        return True