"""
Simulation Configuration
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class ModelConfig:
    """Model architecture parameters"""
    n_experts: int = 896        # K3: 896 routed experts
    n_active: int = 16          # K3: 16 active per token
    n_layers: int = 80          # Estimated K3 layers
    shard_size_bytes: int = 4 * 1024 * 1024  # 4 MB per expert shard
    shard_read_time_us: int = 300  # ~300µs sequential read of 4MB @ 14GB/s


@dataclass
class WorkloadConfig:
    """Token workload parameters"""
    n_tokens: int = 1000        # tokens per simulation run
    n_warmup: int = 10          # warmup tokens (cold start)
    
    # Expert popularity distribution
    # Zipf-like: few experts get most traffic
    zipf_alpha: float = 0.9    # skew (higher = more concentrated)
    
    # Temporal locality
    # Probability that next token uses same experts
    temporal_locality: float = 0.3
    
    # Random seed for reproducibility
    seed: int = 42


@dataclass
class BufferConfig:
    """Streaming buffer parameters"""
    size_mb: int = 256          # total buffer size in MB
    eviction_policy: str = "lru_priority"  # lru | lfu | lru_priority
    
    # Priority boost
    # Experts with confidence > threshold get priority boost
    predict_boost: bool = True
    confidence_threshold: float = 0.7


@dataclass
class PredictorConfig:
    """Predictor model parameters"""
    model: str = "heuristic"    # perfect | heuristic | mlp
    
    # Heuristic params
    freq_window: int = 100      # lookback for frequency counts
    temporal_weight: float = 0.4  # weight for temporal vs frequency
    n_predict: int = 32         # how many experts to predict (safety margin > 16)


@dataclass
class TimingConfig:
    """I/O and compute timing parameters"""
    # NVMe
    nvme_seq_bw_gbps: float = 14.0   # PCIe 5.0 sequential
    nvme_rand_read_us: int = 60      # 4KB random read latency
    nvme_queue_depth: int = 64       # NVMe command queue depth
    
    # CPU compute
    compute_time_per_token_us: int = 350_000  # 350ms per token (target)
    draft_time_us: int = 3_000                # 3ms draft head
    predictor_time_us: int = 2_000            # 2ms MLP prediction
    scheduler_overhead_us: int = 500          # 0.5ms scheduler


@dataclass
class SimConfig:
    """Top-level simulation configuration"""
    model: ModelConfig = field(default_factory=ModelConfig)
    workload: WorkloadConfig = field(default_factory=WorkloadConfig)
    buffer: BufferConfig = field(default_factory=BufferConfig)
    predictor: PredictorConfig = field(default_factory=PredictorConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    
    def shards_per_buffer(self) -> int:
        return (self.buffer.size_mb * 1024 * 1024) // self.model.shard_size_bytes
