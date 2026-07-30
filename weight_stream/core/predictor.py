"""
HeuristicPredictor: Weight access prediction for MoE models.

Based on EXP-002 findings:
- No MLP needed: LRU handles temporal locality perfectly
- Simple heuristics are sufficient for cold-start and pattern detection
- Predictor is only useful for prefetch, not eviction (LRU handles eviction)

Strategies:
1. **Same-layer**: Experts that were just used will be reused (temporal locality)
2. **Sequential**: If expert X, X+1, X+2 were accessed, continue the pattern
3. **Co-occurrence**: Track which experts frequently appear together
"""
import time
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set, Tuple


class HeuristicPredictor:
    """
    Lightweight heuristic-based expert access predictor.
    
    No MLP, no fine-tuning — simple frequency + temporal heuristics
    based on empirical findings from EXP-002.
    
    Args:
        history_size: number of recent accesses to track (default: 100)
        window_size: lookback window for pattern detection (default: 10)
    """
    
    def __init__(self, history_size: int = 100, window_size: int = 10):
        self.history_size = history_size
        self.window_size = window_size
        
        # Access pattern tracking
        self._access_history: deque = deque(maxlen=history_size)
        self._frequency: Dict[int, int] = defaultdict(int)
        self._co_occurrence: Dict[int, Set[int]] = defaultdict(set)
        
        # Pending predictions
        self._predictions: deque = deque(maxlen=50)
    
    def observe(self, shard_id: int, step: int = 0):
        """
        Record an observed shard access.
        
        Args:
            shard_id: accessed shard ID
            step: optional step counter (for temporal ordering)
        """
        self._access_history.append(shard_id)
        self._frequency[shard_id] += 1
        
        # Track co-occurrence with recent accesses
        for prev_id in list(self._access_history)[-self.window_size:-1]:
            if prev_id != shard_id:
                self._co_occurrence[shard_id].add(prev_id)
                self._co_occurrence[prev_id].add(shard_id)
    
    def predict_next(self, current_shard: int, top_k: int = 3) -> List[int]:
        """
        Predict the next shard(s) that will be accessed.
        
        Uses a weighted combination of:
        1. Recent sequence continuation (if pattern detected)
        2. Co-occurring experts (from observed pairs)
        3. Most frequent experts (fallback)
        
        Returns list of predicted shard IDs, sorted by confidence (descending).
        """
        candidates: Dict[int, float] = {}
        
        # Strategy 1: Sequential pattern detection
        if len(self._access_history) >= 3:
            recent = list(self._access_history)[-3:]
            # Check for stride-1 pattern (x, x+1, x+2 ...)
            if (recent[-1] - recent[-2] == recent[-2] - recent[-3] and 
                recent[-1] - recent[-2] in (1, -1)):
                next_in_seq = recent[-1] + (recent[-1] - recent[-2])
                if next_in_seq >= 0:
                    candidates[next_in_seq] = 0.9
        
        # Strategy 2: Co-occurrence
        if current_shard in self._co_occurrence:
            weight = 0.5
            for peer in self._co_occurrence[current_shard]:
                if peer not in candidates:
                    candidates[peer] = weight
                else:
                    candidates[peer] += weight
        
        # Strategy 3: Frequency bias
        recent_set = set(self._access_history)
        for sid in recent_set:
            freq = self._frequency.get(sid, 0)
            if sid not in candidates and freq > 0:
                candidates[sid] = 0.1 * freq
        
        # Sort by confidence, take top_k
        sorted_candidates = sorted(
            candidates.items(), key=lambda x: -x[1]
        )
        predicted = [sid for sid, _ in sorted_candidates[:top_k]]
        
        # Store predictions for verification
        self._predictions.append(predicted)
        
        return predicted
    
    def get_frequency(self, shard_id: int) -> int:
        """Return observed frequency of a shard"""
        return self._frequency.get(shard_id, 0)
    
    def get_stats(self) -> Dict:
        """Return predictor statistics"""
        return {
            'history_size': len(self._access_history),
            'unique_shards': len(self._frequency),
            'top_frequent': sorted(
                self._frequency.items(), key=lambda x: -x[1]
            )[:5],
        }
