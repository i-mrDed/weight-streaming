"""
Synthetic token workload — expert access pattern generation
Models K3-like behavior: 896 experts, 16 active/token, temporal locality
"""
import random
import math
from typing import List, Set, Tuple
from .config import SimConfig


class AccessPatternGenerator:
    """
    Generates synthetic expert access patterns for simulation.
    
    Features:
    - Zipf-distributed expert popularity (few experts get most traffic)
    - Temporal locality (adjacent tokens use similar experts)
    - Layer-aware: each layer has different active experts
    """
    
    def __init__(self, config: SimConfig):
        self.cfg = config
        self.rng = random.Random(config.workload.seed)
        
        # Pre-compute expert popularity (Zipf distribution)
        self.expert_popularity = self._zipf_distribution(
            config.model.n_experts, 
            config.workload.zipf_alpha
        )
        
        # Identify hot experts (top 10%)
        n_hot = max(1, config.model.n_experts // 10)
        self.hot_experts = set(range(n_hot))
        
    def _zipf_distribution(self, n: int, alpha: float) -> List[float]:
        """Generate Zipf-distributed popularity scores"""
        ranks = list(range(1, n + 1))
        weights = [1.0 / (r ** alpha) for r in ranks]
        total = sum(weights)
        return [w / total for w in weights]  # normalized probabilities
    
    def generate_token_sequence(self) -> List[List[int]]:
        """
        Generate a sequence of token expert sets.
        
        Returns:
            List of [expert_id, ...] for each token, one per layer.
            Shape: n_tokens lists, each with n_layers sub-lists of n_active expert IDs.
        """
        cfg = self.cfg.model
        wl = self.cfg.workload
        total_tokens = wl.n_tokens + wl.n_warmup
        
        sequence = []
        prev_experts: Set[int] = set()
        
        for _ in range(total_tokens):
            if wl.shared_experts_per_token:
                token_layers = self._generate_shared_token(prev_experts)
                prev_experts = set(token_layers[0])
            else:
                token_layers = self._generate_independent_token(prev_experts)
                prev_experts = set(token_layers[-1])
            sequence.append(token_layers)
        
        # Remove warmup tokens
        return sequence[wl.n_warmup:]
    
    def _generate_shared_token(self, prev: Set[int]) -> List[List[int]]:
        """
        K3-realistic mode: one expert set per token, reused across layers
        with inter_layer_similarity controlling layer-to-layer drift.
        """
        cfg = self.cfg.model
        wl = self.cfg.workload
        
        # Token-level expert selection (router output inspired by K3 KDA)
        base_experts = self._sample_experts(prev)
        
        # Each layer uses mostly the same experts with some drift
        token_layers = []
        for layer in range(cfg.n_layers):
            if self.rng.random() < wl.inter_layer_similarity:
                # Same experts (high similarity — Quantile Balancing effect)
                experts = set(base_experts)
            else:
                # Slightly different set: swap some experts
                n_swap = max(1, cfg.n_active // 4)
                to_swap = self.rng.sample(list(base_experts), n_swap)
                new_experts = set(base_experts) - set(to_swap)
                # Fill with new random experts (popularity-biased)
                replacements = self._sample_fresh(new_experts, n_swap)
                experts = new_experts | set(replacements)
            token_layers.append(sorted(experts))
        
        return token_layers
    
    def _generate_independent_token(self, prev: Set[int]) -> List[List[int]]:
        """
        Original mode: each layer independently selects experts
        with temporal similarity chain across layers.
        """
        cfg = self.cfg.model
        token_layers = []
        prev_experts = prev
        
        for layer in range(cfg.n_layers):
            if layer == 0:
                experts = self._sample_experts(prev_experts)
            else:
                experts = self._sample_experts(prev_experts, same_set_prob=0.7)
            token_layers.append(sorted(experts))
            prev_experts = experts
        
        return token_layers
    
    def _sample_experts(self, prev: Set[int], same_set_prob: float = 0.0) -> Set[int]:
        """Sample active experts with temporal locality bias"""
        cfg = self.cfg.model
        wl = self.cfg.workload
        
        # How many experts carry over from previous token?
        if prev and self.rng.random() < wl.temporal_locality:
            n_carry = min(len(prev) // 2, cfg.n_active // 2)
            carry = set(self.rng.sample(list(prev), n_carry))
        else:
            carry = set()
            n_carry = 0
        
        # Sample remaining from full pool (bias toward hot experts)
        n_new = cfg.n_active - n_carry
        if n_new <= 0:
            return carry
        
        # Weighted sample: bias toward hot + popularity
        candidates = [
            e for e in range(cfg.n_experts) 
            if e not in carry
        ]
        weights = [self.expert_popularity[e] for e in candidates]
        
        # Boost hot experts
        weights = [
            w * 3.0 if e in self.hot_experts else w 
            for e, w in zip(candidates, weights)
        ]
        
        # Normalize
        total = sum(weights)
        weights = [w / total for w in weights]
        
        sampled = self.rng.choices(candidates, weights=weights, k=n_new)
        return carry | set(sampled)
    
    def _sample_fresh(self, exclude: Set[int], k: int) -> List[int]:
        """Sample k experts not in exclude, biased toward popularity"""
        candidates = [
            e for e in range(self.cfg.model.n_experts)
            if e not in exclude
        ]
        if not candidates or k <= 0:
            return []
        weights = [self.expert_popularity[e] for e in candidates]
        # Boost hot experts
        weights = [
            w * 3.0 if e in self.hot_experts else w
            for e, w in zip(candidates, weights)
        ]
        total = sum(weights)
        weights = [w / total for w in weights]
        return self.rng.choices(candidates, weights=weights, k=min(k, len(candidates)))
    
    def get_expert_frequency(self, sequence: List[List[int]]) -> List[int]:
        """Count how many times each expert appears across sequence"""
        counts = [0] * self.cfg.model.n_experts
        for token_layers in sequence:
            for experts in token_layers:
                for e in experts:
                    counts[e] += 1
        return counts
