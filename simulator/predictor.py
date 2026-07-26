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
        elif model == "simulated_accuracy":
            return self._predict_simulated_accuracy()
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
    
    def _predict_simulated_accuracy(self) -> PredictionResult:
        """
        Controlled accuracy mode: knows future but injects errors.
        
        Given target accuracy T (e.g. 0.7):
        - actual = union of experts across ALL layers for this token
          ~30-50 unique experts for 80 layers with inter-layer drift
        - Predict N experts (n_predict, default 64 to cover all actual)
        - Keep T * n_actual experts correct (so target = recall metric)
        - Fill remaining N - n_correct with random wrong experts
        - Return predictions with confidence scores
        
        This lets us directly measure: if we build a predictor with
        recall T, what buffer hit rate and throughput do we get?
        """
        if self._token_idx >= len(self._perfect_future):
            return PredictionResult([], [])
        
        accuracy = self.cfg.predictor.accuracy_level    # target recall
        n_predict = self.cfg.predictor.n_predict        # prediction window
        actual = self._perfect_future[self._token_idx]
        self._token_idx += 1
        
        actual_set = set(actual)
        n_actual = len(actual_set)
        
        # Target number of correct experts = recall * n_actual
        n_correct = max(1, min(n_actual, round(accuracy * n_actual)))
        
        # Pick n_correct experts from actual set (these will be correctly predicted)
        correct_set = set(self.rng.sample(list(actual_set), n_correct))
        
        # Fill up to n_predict with wrong experts (not in actual)
        n_wrong = n_predict - len(correct_set)
        wrong_set = set()
        if n_wrong > 0:
            # Bias toward hot experts (realistic MLP behavior)
            hot_pool = set(range(max(1, self.cfg.model.n_experts // 10)))
            pool = [e for e in hot_pool if e not in actual_set]
            if len(pool) < n_wrong:
                pool = [e for e in range(self.cfg.model.n_experts) if e not in actual_set]
            wrong_set = set(self.rng.sample(pool, min(n_wrong, len(pool))))
        
        predicted = sorted(correct_set | wrong_set)
        
        # Confidence: correct get high, wrong get low
        predictions = [
            (e, 0.95 if e in correct_set else 0.25)
            for e in predicted
        ]
        
        # Actual recall = overlap / n_actual
        overlap = len(correct_set)  # all correct_set are in actual
        
        return PredictionResult(
            predicted_experts=predictions,
            actual_experts=list(actual_set),
            n_correct=overlap,
            n_total=n_actual,
            hit_rate=overlap / max(1, n_actual)  # = accuracy (recall)
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
        """
        Evaluate how many predicted experts were actually used.
        
        Two metrics:
        1. hit_rate (recall/coverage): % of actual unique experts 
           covered by ANY prediction (up to n_predict)
        2. top16_precision: % of top-n_active predictions that are 
           correct (useful for priority boost analysis)
        
        hit_rate is the main metric (used for predictor_stats).
        """
        # Full recall: all predictions vs all actual unique experts
        pred_full = set(e for e, _ in pred.predicted_experts[:self.cfg.predictor.n_predict])
        actual_set = set(actual_experts)
        
        correct = pred_full & actual_set
        pred.n_correct = len(correct)
        pred.n_total = len(actual_set)
        pred.hit_rate = pred.n_correct / max(1, pred.n_total) if pred.n_total > 0 else 0.0
        pred.actual_experts = list(actual_set)
        
        return pred
