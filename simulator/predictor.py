"""
Weight Predictor — simulation of different prediction models
Models: perfect (upper bound), heuristic (baseline), MLP (future)
"""
import random
import math
from typing import Dict, List, Set, Tuple
from collections import Counter, defaultdict
from dataclasses import dataclass
from .config import SimConfig


@dataclass
class PredictionResult:
    """Result from predictor for one token step"""
    predicted_experts: List[Tuple[int, float]]  # (expert_id, confidence)
    actual_experts: List[int]
    n_correct: int = 0
    n_total: int = 0
    hit_rate: float = 0.0


class Predictor:
    """
    Simulates different prediction strategies for expert routing.
    
    Models:
    - perfect: knows future (upper bound)
    - heuristic: frequency + temporal locality (baseline)
    """
    
    def __init__(self, config: SimConfig, access_generator=None):
        self.cfg = config
        self.generator = access_generator
        self.rng = random.Random(config.workload.seed + 1)
        
        # Frequency tracking (for heuristic)
        self.freq_counts: Dict[int, int] = defaultdict(int)
        self.recent_experts: List[int] = []  # sliding window
        
        # Perfect predictor pre-computes
        self._perfect_future: List[Set[int]] = []
        self._token_idx: int = 0
    
    def set_perfect_future(self, sequence):
        """Feed full sequence for perfect prediction"""
        for token_layers in sequence:
            # Union of all experts across layers for this token
            layer_experts = set()
            for experts in token_layers:
                layer_experts.update(experts)
            self._perfect_future.append(layer_experts)
        self._token_idx = 0
    
    def predict(self, token_idx: int) -> PredictionResult:
        """
        Predict which experts will be needed.
        Returns predicted set with confidence scores.
        """
        model = self.cfg.predictor.model
        
        if model == "perfect":
            return self._predict_perfect()
        elif model == "heuristic":
            return self._predict_heuristic()
        else:
            raise ValueError(f"Unknown predictor model: {model}")
    
    def observe(self, actual_experts: List[int]):
        """Update predictor with actual expert usage (online learning)"""
        for e in actual_experts:
            self.freq_counts[e] += 1
        self.recent_experts.extend(actual_experts)
        
        # Keep sliding window
        max_window = self.cfg.predictor.freq_window * self.cfg.model.n_active
        if len(self.recent_experts) > max_window:
            self.recent_experts = self.recent_experts[-max_window:]
    
    def _predict_perfect(self) -> PredictionResult:
        """Perfect predictor — knows future (upper bound)"""
        if self._token_idx >= len(self._perfect_future):
            return PredictionResult([], [])
        
        future = self._perfect_future[self._token_idx]
        self._token_idx += 1
        
        predictions = [(e, 1.0) for e in future]
        return PredictionResult(
            predicted_experts=predictions,
            actual_experts=list(future),
            n_correct=len(future),
            n_total=len(future),
            hit_rate=1.0
        )
    
    def _predict_heuristic(self) -> PredictionResult:
        """
        Heuristic predictor using frequency + temporal locality.
        
        Strategy:
        1. Top-K most frequent experts in recent window
        2. Boost experts seen in last token (temporal)
        3. Fill remaining with random popular experts
        """
        cfg = self.cfg.predictor
        n_predict = cfg.n_predict
        
        # Score every expert based on frequency and recency
        scores: Dict[int, float] = defaultdict(float)
        
        # Frequency score
        if self.freq_counts:
            max_freq = max(self.freq_counts.values())
            for e, count in self.freq_counts.items():
                scores[e] += cfg.temporal_weight * (count / max_freq)
        
        # Temporal boost for recently seen experts
        recent_set = set(self.recent_experts[-self.cfg.model.n_active * 3:])
        for e in recent_set:
            scores[e] += (1.0 - cfg.temporal_weight)
        
        # If we have a generator, use expert popularity as prior
        if self.generator:
            for e in range(self.cfg.model.n_experts):
                if e not in scores:
                    scores[e] = self.generator.expert_popularity[e] * 0.1
        
        # Sort by score, take top-K
        top_experts = sorted(scores.items(), key=lambda x: -x[1])[:n_predict]
        
        predictions = [(e, min(1.0, s)) for e, s in top_experts]
        return PredictionResult(
            predicted_experts=predictions,
            actual_experts=[]  # filled later by caller
        )
    
    def evaluate_prediction(self, pred: PredictionResult, 
                          actual_experts: List[int]) -> PredictionResult:
        """Evaluate how many predicted experts were actually used"""
        pred_set = set(e for e, _ in pred.predicted_experts[:self.cfg.model.n_active])
        actual_set = set(actual_experts)
        
        correct = pred_set & actual_set
        pred.n_correct = len(correct)
        pred.n_total = len(actual_set)
        pred.hit_rate = pred.n_correct / max(1, pred.n_total) if pred.n_total > 0 else 0.0
        pred.actual_experts = list(actual_set)
        
        return pred
