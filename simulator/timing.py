"""
Timing Simulation — I/O + compute latency model
Models NVMe bandwidth, compute overlap, and overall timing
"""
from typing import List, Tuple
from dataclasses import dataclass
from .config import SimConfig


@dataclass
class TimingResult:
    """Results from timing simulation for one token"""
    token_id: int
    compute_time_us: int
    io_time_us: int
    overlap_time_us: int
    stall_time_us: int  # time wasted waiting for I/O
    total_time_us: int
    pre_fetched_count: int
    miss_count: int


class TimingSimulator:
    """
    Simulates I/O + compute timing with overlap.
    
    Models:
    - NVMe sequential read bandwidth
    - Async I/O overlap with compute
    - Predictor overhead
    - Stall when buffer misses
    """
    
    def __init__(self, config: SimConfig):
        self.cfg = config.timing
    
    def simulate_token(
        self,
        token_id: int,
        pre_fetched_shards: int,
        miss_shards: int,
        predictor_confidence: float = 1.0
    ) -> TimingResult:
        """
        Simulate timing for one token.
        
        Timeline:
        [Draft | Predict | Scheduler overhead | NVMe read]
        [Compute                              ]
        [Overlap region                        ]
        
        Predictor confidence affects I/O overlap efficiency:
        - High confidence (>0.7): scheduler pre-fetches in large batches
          overlapping with compute → minimal stall
        - Low confidence (<0.3): scheduler waits for confirmation
          → more on-demand reads → more stall
        """
        t = self.cfg
        
        # Phase 1: Draft + Predict (sequential, small)
        prep_time = t.draft_time_us + t.predictor_time_us + t.scheduler_overhead_us
        
        # Phase 2: I/O time
        #   Sequential read (pre-fetch): full bandwidth
        #   Random read (miss): penalty per shard
        sequential_bytes = pre_fetched_shards * 4 * 1024 * 1024  # 4 MB per shard
        sequential_time = (sequential_bytes / (t.nvme_seq_bw_gbps * 1e9 / 1e6))
        random_time = miss_shards * t.nvme_rand_read_us
        io_time = int(sequential_time + random_time)
        
        # Phase 3: Compute time (target: 350ms per token)
        compute_time = t.compute_time_per_token_us
        
        # Predictor confidence scales how much I/O can be overlapped
        # High confidence → speculative pre-fetch overlaps with compute
        # Low confidence → mostly on-demand reads, less overlap
        overlap_efficiency = predictor_confidence  # 0.0 to 1.0
        
        # Overlap: sequential I/O (pre-fetched) can overlap
        # Random I/O (miss) causes stall (on-demand fetch)
        overlap_time = min(
            int(sequential_time * overlap_efficiency + prep_time),
            compute_time
        )
        
        # Stall: random (miss) reads are urgent, they block compute
        stall_time = random_time  # emergency miss fetch stalls compute
        
        # Effective I/O time (after overlap)
        effective_io = max(0, io_time - overlap_time)
        
        total = max(compute_time, prep_time + effective_io) + stall_time
        
        return TimingResult(
            token_id=token_id,
            compute_time_us=compute_time,
            io_time_us=io_time,
            overlap_time_us=overlap_time,
            stall_time_us=stall_time,
            total_time_us=total,
            pre_fetched_count=pre_fetched_shards,
            miss_count=miss_shards,
        )
    
    @staticmethod
    def format_time(us: int) -> str:
        """Format microseconds to human-readable string"""
        if us < 1000:
            return f"{us}µs"
        elif us < 1_000_000:
            return f"{us / 1000:.1f}ms"
        else:
            return f"{us / 1_000_000:.2f}s"
