"""
Streaming Buffer — cache policy simulation
Polices: LRU, LFU, Priority-LRU (our proposed)
"""
import heapq
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass
from .config import SimConfig


@dataclass
class BufferStats:
    """Collected statistics from buffer simulation"""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    emergency_fetches: int = 0
    hit_rate: float = 0.0
    
    # Per-expert stats
    expert_hits: Dict[int, int] = None
    expert_misses: Dict[int, int] = None
    
    def __post_init__(self):
        self.expert_hits = defaultdict(int)
        self.expert_misses = defaultdict(int)
    
    def record_hit(self, expert_id: int):
        self.hits += 1
        self.expert_hits[expert_id] += 1
    
    def record_miss(self, expert_id: int):
        self.misses += 1
        self.expert_misses[expert_id] += 1


class StreamingBuffer:
    """
    Simulates the streaming buffer with different eviction policies.
    
    Buffer units: expert shards (~4 MB each)
    Capacity: number of shards (e.g., 256 MB / 4 MB = 64 shards)
    """
    
    def __init__(self, config: SimConfig):
        self.cfg = config
        self.capacity = config.shards_per_buffer()
        self.policy = config.buffer.eviction_policy
        
        # Current buffer state
        self._slots: Dict[int, 'CacheEntry'] = {}  # expert_id → entry
        self._access_clock: int = 0
        
        # Stats collection
        self.stats = BufferStats()
    
    def access(self, expert_id: int, priority: float = 0.0) -> bool:
        """
        Simulate accessing an expert shard.
        Returns True if hit, False if miss.
        """
        self._access_clock += 1
        
        if expert_id in self._slots:
            # HIT
            self._slots[expert_id].last_access = self._access_clock
            self._slots[expert_id].access_count += 1
            if self.cfg.buffer.predict_boost:
                self._slots[expert_id].priority = max(
                    self._slots[expert_id].priority, priority
                )
            self.stats.record_hit(expert_id)
            return True
        else:
            # MISS
            self.stats.record_miss(expert_id)
            self._load(expert_id, priority)
            return False
    
    def _load(self, expert_id: int, priority: float):
        """Load an expert into the buffer (may evict)"""
        if len(self._slots) >= self.capacity:
            self._evict()
        
        self._slots[expert_id] = CacheEntry(
            expert_id=expert_id,
            loaded_at=self._access_clock,
            last_access=self._access_clock,
            access_count=1,
            priority=priority
        )
    
    def _evict(self):
        """Evict one entry based on policy"""
        self.stats.evictions += 1
        
        if self.policy == "lru":
            # LRU: evict oldest last_access
            victim = min(self._slots.items(), 
                        key=lambda x: x[1].last_access)
            
        elif self.policy == "lfu":
            # LFU: evict least accessed
            victim = min(self._slots.items(),
                        key=lambda x: x[1].access_count)
            
        elif self.policy == "lru_priority":
            # Priority-LRU: score = α*age + β*(3-priority)
            current = self._access_clock
            def score(item):
                _, e = item
                age = current - e.last_access
                # priority is 0-1, invert so higher priority = harder to evict
                prio_score = (1.0 - e.priority) * 100
                return age - prio_score  # older age = easier evict
            victim = min(self._slots.items(), key=score)
        
        del self._slots[victim[0]]
    
    def get_stats(self) -> BufferStats:
        """Compute final statistics"""
        total = self.stats.hits + self.stats.misses
        if total > 0:
            self.stats.hit_rate = self.stats.hits / total
        return self.stats


@dataclass
class CacheEntry:
    expert_id: int
    loaded_at: int
    last_access: int
    access_count: int
    priority: float
