"""
Prefetcher: Orchestrates speculative weight loading for MoE models.

The prefetcher sits between the predictor and the buffer:
1. Predictor suggests which shards will be needed
2. Prefetcher decides WHETHER to actually load them (confidence threshold)
3. Buffer performs the actual I/O (prefetch or full load)
4. During compute time, prefetcher overlaps I/O with execution

Based on EXP-004 findings:
- Compute (815ms per token) >> I/O (0-67ms stall)
- Prefetch window: ~400ms (half of compute time) for safety
- Only prefetch when confident (>70% based on pattern)
"""
import threading
import time
from typing import Callable, List, Optional

from .buffer import StreamingBuffer
from .predictor import HeuristicPredictor


class Prefetcher:
    """
    Prefetch orchestrator: runs predictions and issues I/O in background.
    
    Uses a background thread to avoid blocking the main inference thread.
    When compute is running (~815ms on K3), the prefetcher has time to
    load the next token's experts.
    
    Args:
        buffer: StreamingBuffer instance
        predictor: HeuristicPredictor instance
        prefetch_window: how far ahead to prefetch (in tokens, default: 2)
        high_confidence: threshold for full load (default: 0.7)
    """
    
    def __init__(
        self,
        buffer: StreamingBuffer,
        predictor: HeuristicPredictor,
        prefetch_window: int = 2,
        high_confidence: float = 0.7,
    ):
        self.buffer = buffer
        self.predictor = predictor
        self.prefetch_window = prefetch_window
        self.high_confidence = high_confidence
        
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Performance tracking
        self.prefetched_count = 0
        self.useful_prefetches = 0
        self.missed_predictions = 0
    
    def on_access(self, shard_id: int, step: int = 0):
        """
        Called when a shard is accessed.
        
        Records the access and kicks off background prefetch.
        This runs synchronously (fast — just records access),
        then spawns prefetch in background thread.
        """
        # Record access (always fast)
        self.predictor.observe(shard_id, step)
        
        # Generate predictions
        next_shards = self.predictor.predict_next(shard_id)
        
        # Kick off background prefetch
        self._prefetch_async(next_shards)
    
    def start(self):
        """Start background prefetch thread"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._prefetch_loop, daemon=True, name="prefetcher"
        )
        self._thread.start()
    
    def stop(self):
        """Stop background prefetch thread"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
    
    @property
    def prefetch_hit_rate(self) -> float:
        total = self.useful_prefetches + self.missed_predictions
        return self.useful_prefetches / total if total > 0 else 0.0
    
    def _prefetch_async(self, predicted_shards: List[int]):
        """Queue predicted shards for background prefetch"""
        with self._lock:
            self._pending = predicted_shards.copy()
    
    def _prefetch_loop(self):
        """Background thread: performs prefetch I/O"""
        pending = []
        while self._running:
            # Get latest predictions
            with self._lock:
                if hasattr(self, '_pending') and self._pending:
                    pending = self._pending.copy()
                    self._pending = []
            
            # Execute prefetches
            if pending:
                # Check which are already in buffer
                to_load = [
                    sid for sid in pending 
                    if sid not in self.buffer
                ]
                if to_load:
                    # Use staggered confidence:
                    # First predicted = full load (high confidence)
                    # Second = light prefetch (medium confidence)
                    # Third = skip (low confidence unless pattern strong)
                    self.buffer.prefetch_full(to_load[:1])
                    if len(to_load) > 1:
                        self.buffer.prefetch(to_load[1:2])
                    self.prefetched_count += len(to_load)
            
            # Sleep to yield CPU during compute
            time.sleep(0.01)  # 10ms polling interval
