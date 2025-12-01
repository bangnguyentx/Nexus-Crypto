import json
import threading
import os
from datetime import datetime
from typing import Dict, Any, List

class Storage:
    def __init__(self, filename: str = "user_data.json"):
        self.filename = filename
        self.lock = threading.Lock()
        self._init_file()

    def _init_file(self):
        if not os.path.exists(self.filename):
            with self.lock:
                with open(self.filename, "w") as f:
                    json.dump({}, f, indent=2)

    def _read_all(self) -> Dict[str, Any]:
        with self.lock:
            try:
                with open(self.filename, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return {}

    def _write_all(self, data: Dict[str, Any]):
        with self.lock:
            with open(self.filename, "w") as f:
                json.dump(data, f, indent=2)

    def add_user(self, user_id: int):
        data = self._read_all()
        if str(user_id) not in data:
            data[str(user_id)] = {
                "joined_at": datetime.now().isoformat(),
                "signal_count": 0,
                "active": True
            }
            self._write_all(data)

    def get_users(self) -> List[int]:
        data = self._read_all()
        return [int(user_id) for user_id in data.keys() if data[user_id].get("active", True)]

    def increment_signal_count(self, user_id: int):
        data = self._read_all()
        user_id_str = str(user_id)
        if user_id_str in data:
            data[user_id_str]["signal_count"] = data[user_id_str].get("signal_count", 0) + 1
            self._write_all(data)

    def remove_user(self, user_id: int):
        data = self._read_all()
        user_id_str = str(user_id)
        if user_id_str in data:
            data[user_id_str]["active"] = False
            self._write_all(data)

    def get_stats(self) -> Dict[str, Any]:
        data = self._read_all()
        active_users = sum(1 for user_data in data.values() if user_data.get("active", True))
        total_signals = sum(user_data.get("signal_count", 0) for user_data in data.values())
        
        return {
            "total_users": len(data),
            "active_users": active_users,
            "total_signals": total_signals
        }
