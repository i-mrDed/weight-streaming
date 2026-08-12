"""
Simulation Configuration
"""
from dataclasses import dataclass, field
from typing import List

from . import physics


@dataclass
class ModelConfig:
    """Model architecture parameters"""
    n_experts: int = 896        # K3: 896 routed experts
    n_active: int = 16          # K3: 16 active per token
    n_layers: int = 80          # Estimated K3 layers
    shard_size_bytes: int = 4 * 1024 * 1024  # 4 MB per expert shard
    shard_read_time_us: int = 300  # ~300µs sequential read of 4MB @ 14GB/s
    active_params: float = 50e9   # K3: ~50B active params per token (EXP-004)
    bits_per_weight: float = 2.5  # Q2_K-family quant (same as Qwen EXP-004)


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
    
    # Per-layer expert sharing
    # True: token uses same experts across all layers (K3 realistic)
    # False: each layer independently selects experts (worst case)
    shared_experts_per_token: bool = True
    
    # Inter-layer similarity
    # 1.0 = same experts every layer, 0.0 = independent
    # Realistic K3: ~0.8-0.9 (Quantile Balancing)
    inter_layer_similarity: float = 0.9
    
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
    model: str = "heuristic"    # perfect | heuristic | simulated_accuracy | mlp
    
    # Heuristic params
    freq_window: int = 100      # lookback for frequency counts
    temporal_weight: float = 0.4  # weight for temporal vs frequency
    n_predict: int = 64         # how many experts to predict (covers ~30-50 actual unique per token)
    
    # Simulated accuracy params (model="simulated_accuracy")
    # Target prediction accuracy (0.0 = random, 1.0 = perfect)
    accuracy_level: float = 0.7


@dataclass
class TimingConfig:
    """I/O and compute timing parameters"""
    # NVMe — spec for the pre-fetch path (full sequential bandwidth).
    # The honest disk-mmap tier (cold faults) is ~0.3-0.6 GB/s (EXP-012).
    nvme_seq_bw_gbps: float = physics.NVME_SEQ_BW_GBPS   # PCIe 5.0 sequential
    nvme_rand_read_us: int = 60      # 4KB random read latency
    nvme_queue_depth: int = 64       # NVMe command queue depth
    
    # CPU compute — derived from physics (BW ÷ bytes/token), not hardcoded.
    # Calibrated in physics.py: Qwen 2.7B active @ 2.5bpw measured 22.73 tok/s
    # → effective BW 19.18 GB/s → K3 50B active = 815ms/token (matches EXP-004
    # scaling estimate 815.46ms to <0.1%).
    compute_time_per_token_us: int = field(
        default_factory=lambda: int(
            1_000_000 * physics.bytes_per_token_gb(
                physics.K3.active_params, physics.K3.bits_per_weight
            ) / physics.DEFAULT_EFFECTIVE_BW_GBPS["cpu-ram"]
        )
    )
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
