"""
Atomic JSON storage helper.
Menggunakan tulis-ke-tmp lalu os.replace() supaya data tidak corrupt
kalau bot crash/restart di tengah proses save (aman untuk Railway).
"""
import json
import os
import copy
import asyncio
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


class JSONStore:
    def __init__(self, filename: str):
        self.path = DATA_DIR / filename
        self._lock = asyncio.Lock()
        if not self.path.exists():
            self._write_sync({})

    def _write_sync(self, data: dict):
        tmp_path = self.path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, self.path)

    def _read_sync(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    async def read(self) -> dict:
        async with self._lock:
            return self._read_sync()

    async def write(self, data: dict):
        async with self._lock:
            self._write_sync(data)

    async def get_path(self, *keys, default=None):
        """Ambil nested value. Kalau belum ada, otomatis dibuat dari default."""
        data = await self.read()
        node = data
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                node = None
                break
            node = node[k]
        if node is None:
            return copy.deepcopy(default) if default is not None else None
        return node

    async def set_path(self, *keys_and_value):
        """Simpan nested value. Panggil: set_path(guild_id, 'join', config_dict)"""
        *keys, value = keys_and_value
        data = await self.read()
        node = data
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value
        await self.write(data)
