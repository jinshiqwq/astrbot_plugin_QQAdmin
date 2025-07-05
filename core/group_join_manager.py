
from typing import Dict, List
import json
import os



class GroupJoinData:
    def __init__(self,path: str = "group_join_data.json"):
        self.path = path
        self.accept_keywords: Dict[str, List[str]] = {}
        self.reject_ids: Dict[str, List[str]] = {}
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            self._save()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.accept_keywords = data.get("accept_keywords", {})
            self.reject_ids = data.get("reject_ids", {})
        except Exception as e:
            print(f"加载 group_join_data 失败: {e}")
            self._save()

    def _save(self):
        data = {
            "accept_keywords": self.accept_keywords,
            "reject_ids": self.reject_ids,
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def save(self):
        self._save()



class GroupJoinManager:
    def __init__(self, json_path: str):
        self.data = GroupJoinData(json_path)

    def should_reject(self, group_id: str, user_id: str) -> bool:
        return (
            group_id in self.data.reject_ids
            and user_id in self.data.reject_ids[group_id]
        )

    def should_approve(self, group_id: str, comment: str) -> bool:
        if group_id not in self.data.accept_keywords:
            return False
        return any(
            kw.lower() in comment.lower() for kw in self.data.accept_keywords[group_id]
        )

    def add_keyword(self, group_id: str, keywords: List[str]):
        self.data.accept_keywords.setdefault(group_id, []).extend(keywords)
        self.data.accept_keywords[group_id] = list(
            set(self.data.accept_keywords[group_id])
        )
        self.data.save()

    def remove_keyword(self, group_id: str, keywords: List[str]):
        if group_id in self.data.accept_keywords:
            for k in keywords:
                if k in self.data.accept_keywords[group_id]:
                    self.data.accept_keywords[group_id].remove(k)
            self.data.save()

    def get_keywords(self, group_id: str) -> List[str]:
        return self.data.accept_keywords.get(group_id, [])

    def add_reject_id(self, group_id: str, ids: List[str]):
        self.data.reject_ids.setdefault(group_id, []).extend(ids)
        self.data.reject_ids[group_id] = list(set(self.data.reject_ids[group_id]))
        self.data.save()

    def remove_reject_id(self, group_id: str, ids: List[str]):
        if group_id in self.data.reject_ids:
            for uid in ids:
                if uid in self.data.reject_ids[group_id]:
                    self.data.reject_ids[group_id].remove(uid)
            self.data.save()

    def get_reject_ids(self, group_id: str) -> List[str]:
        return self.data.reject_ids.get(group_id, [])

    def blacklist_on_leave(self, group_id: str, user_id: str) -> None:
        self.data.reject_ids.setdefault(group_id, []).append(user_id)
        self.data.save()

