from ModuleFolders.Cache.CacheItem import CacheItem

import threading
from typing import Dict, List


class CacheFile:
    """文件级缓存容器"""
    def __init__(self, file_args: dict):
        # 文件元数据
        self.file_name: str = ""
        self.storage_path: str = ""
        self.file_encoding: str = "utf-8"  # 默认编码
        self.line_ending: str = "\n"        # 默认换行符
        
        # 初始化文件属性
        for k, v in file_args.items():
            setattr(self, k, v)
        
        # 缓存项存储
        self._items: Dict[int, CacheItem] = {}  # 使用text_index作为键
        self._lock = threading.RLock()  # 可重入锁

    def __repr__(self) -> str:
        return f"CacheFile({self.file_name}, items={len(self._items)})"

    def add_item(self, item: CacheItem) -> None:
        """线程安全添加缓存项"""
        with self._lock:
            self._items[item.text_index] = item

    def get_item(self, text_index: int) -> CacheItem:
        """线程安全获取缓存项"""
        with self._lock:
            return self._items.get(text_index)

    def get_all_items(self) -> List[CacheItem]:
        """获取全部缓存项的副本"""
        with self._lock:
            return list(self._items.values())

