"""
StreamingBuffer: LRU-based hot-set tracker for memory-mapped model files.

This is not a data store — it works with an mmap'd GGUF file and tracks
which shards (expert weights) are 'hot' (recently used). The actual data
lives in the mmap (zero-copy). The buffer uses OS-level prefetch to keep
hot shards in RAM and reduce page faults.

Design based on EXP-004 findings:
- LRU > LFU for shared MoE access pattern (93.8% hit at 64MB)
- 64 MB buffer is sufficient (no benefit from larger)
- Predictor not needed for eviction decisions
"""
import mmap
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Set


# K3 MXFP4: 4 MB per expert shard
# Qwen Q2_K: ~700 KB per expert, but aligned to 4MB for compatibility
SHARD_SIZE = 4 * 1024 * 1024  # 4 MB


class StreamingBuffer:
    """
    LRU buffer that tracks hot shards in a memory-mapped model file.
    
    Args:
        mmap_obj: memory-mapped file object (mmap.mmap)
        total_size: total file size in bytes
        capacity_mb: buffer capacity in MB (default: 64)
        shard_size: size of one shard in bytes (default: 4MB)
    """
    
    def __init__(
        self,
        mmap_obj: mmap.mmap,
        total_size: int,
        capacity_mb: int = 64,
        shard_size: int = SHARD_SIZE,
    ):
        self.mmap = mmap_obj
        self.total_size = total_size
        self.shard_size = shard_size
        self.n_shards = (total_size + shard_size - 1) // shard_size
        
        # LRU tracking: shard_id -> last_access_timestamp
        self._lru: OrderedDict = OrderedDict()
        self._capacity = max(1, (capacity_mb * 1024 * 1024) // shard_size)
        
        # Stats
        self.hits = 0
        self.misses = 0
        self.prefetches = 0
        self.evictions = 0
        self._access_count = 0
    
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
    
    @property
    def size(self) -> int:
        """Current number of shards in the hot set"""
        return len(self._lru)
    
    def access(self, shard_id: int) -> memoryview:
        """
        Record access to a shard and return its data.
        
        If shard is in hot set: LRU hit (fast).
        If not: LRU miss, load from mmap (may trigger page fault).
        
        Returns memoryview into the mmap (zero-copy).
        """
        self._access_count += 1
        offset = shard_id * self.shard_size
        length = min(self.shard_size, self.total_size - offset)
        
        if shard_id in self._lru:
            # HIT — move to end (most recently used)
            self._lru.move_to_end(shard_id)
            self._lru[shard_id] = self._access_count
            self.hits += 1
        else:
            # MISS — load into hot set
            self.misses += 1
            if len(self._lru) >= self._capacity:
                self._evict_lru()
            self._lru[shard_id] = self._access_count
        
        # Return zero-copy view into mmap
        return memoryview(self.mmap)[offset:offset + length]
    
    def prefetch(self, shard_ids: List[int]):
        """
        Prefetch predicted shards by touching their first byte.
        
        This triggers OS page loading for the touched page (4KB on Windows).
        For full-shard loading, sequential read is better.
        
        Args:
            shard_ids: list of shard IDs to prefetch
        """
        for sid in shard_ids:
            if sid not in self._lru and 0 <= sid < self.n_shards:
                offset = sid * self.shard_size
                if offset < self.total_size:
                    # Touch first byte → OS loads 4KB page
                    _ = self.mmap[offset]
                    self.prefetches += 1
                    # Add to LRU (marks as 'loaded')
                    if len(self._lru) >= self._capacity:
                        self._evict_lru()
                    self._lru[sid] = self._access_count
    
    def prefetch_full(self, shard_ids: List[int]):
        """
        Full sequential read of predicted shards.
        
        More expensive than prefetch() but loads entire shard.
        Use when confidence is high (>70%).
        """
        for sid in shard_ids:
            if sid not in self._lru and 0 <= sid < self.n_shards:
                offset = sid * self.shard_size
                length = min(self.shard_size, self.total_size - offset)
                if offset < self.total_size:
                    # Sequential read → OS loads all pages
                    _ = self.mmap[offset:offset + length]
                    self.prefetches += 1
                    if len(self._lru) >= self._capacity:
                        self._evict_lru()
                    self._lru[sid] = self._access_count
    
    def get_hot_set(self) -> Set[int]:
        """Return set of shard IDs currently in the hot set"""
        return set(self._lru.keys())
    
    def get_stats(self) -> Dict:
        """Return buffer statistics"""
        return {
            'capacity_shards': self._capacity,
            'hot_shards': len(self._lru),
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': self.hit_rate,
            'prefetches': self.prefetches,
            'evictions': self.evictions,
            'total_accesses': self._access_count,
        }
    
    def reset_stats(self):
        """Reset hit/miss counters (keeps LRU state)"""
        self.hits = 0
        self.misses = 0
        self.prefetches = 0
        self.evictions = 0
    
    def _evict_lru(self):
        """Evict least recently used shard"""
        if self._lru:
            self._lru.popitem(last=False)  # FIFO = LRU in OrderedDict
            self.evictions += 1
    
    def __len__(self) -> int:
        return len(self._lru)
    
    def __contains__(self, shard_id: int) -> bool:
        return shard_id in self._lru
