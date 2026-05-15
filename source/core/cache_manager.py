"""
—, 
"""
import os
import shutil
from dataclasses import dataclass


@dataclass
class CacheInfo:
    step: str
    path: str
    file_count: int
    size_mb: float


class CacheManager:
    """Project"""

    def get_cache_info(self, cache_dir: str) -> list[CacheInfo]:
        """Step"""
        if not os.path.isdir(cache_dir):
            return []

        infos = []
        for entry in sorted(os.listdir(cache_dir)):
            subdir = os.path.join(cache_dir, entry)
            if os.path.isdir(subdir):
                file_count = 0
                total_size = 0
                for root, dirs, files in os.walk(subdir):
                    for f in files:
                        fp = os.path.join(root, f)
                        file_count += 1
                        total_size += os.path.getsize(fp)
                infos.append(CacheInfo(
                    step=entry,
                    path=subdir,
                    file_count=file_count,
                    size_mb=round(total_size / (1024 * 1024), 2),
                ))
        return infos

    def get_total_size_mb(self, cache_dir: str) -> float:
        """ (MB)"""
        infos = self.get_cache_info(cache_dir)
        return sum(i.size_mb for i in infos)

    def clear_step_cache(self, cache_dir: str, step: str):
        """Step"""
        target = os.path.join(cache_dir, step)
        if os.path.isdir(target):
            shutil.rmtree(target)
            os.makedirs(target, exist_ok=True)

    def clear_temp(self, cache_dir: str):
        """file"""
        self.clear_step_cache(cache_dir, "temp")

    def has_cache(self, cache_dir: str, step: str, filename: str = "") -> bool:
        """Step"""
        step_dir = os.path.join(cache_dir, step)
        if filename:
            return os.path.isfile(os.path.join(step_dir, filename))
        return os.path.isdir(step_dir) and len(os.listdir(step_dir)) > 0
