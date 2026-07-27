#!/usr/bin/env python3
"""
Speculative Weight Streaming — Main Simulator
"""
import json
import sys
import os
from typing import Dict, List
from dataclasses import dataclass

# Add parent to path for direct execution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulator.config import SimConfig
from simulator.access_pattern import AccessPatternGenerator
from simulator.buffer import StreamingBuffer
from simulator.predictor import Predictor
from simulator.timing import TimingSimulator


@dataclass
class SimulationResult:
    """Complete simulation results"""
    config: Dict
    buffer_stats: Dict
    predictor_stats: Dict
    timing_stats: Dict
    
    def print_summary(self):
        print("=" * 60)
        print("SPECULATIVE WEIGHT STREAMING - SIMULATION RESULTS")
        print("=" * 60)
        
        print(f"\nCONFIG:")
        print(f"  Model: {self.config['model']}")
        print(f"  Buffer: {self.config['buffer_size_mb']} MB")
        print(f"  Predictor: {self.config['predictor']}")
        print(f"  Tokens: {self.config['n_tokens']}")
        
        print(f"\nBUFFER PERFORMANCE:")
        bs = self.buffer_stats
        print(f"  Hit rate:  {bs['hit_rate']*100:.1f}%")
        print(f"  Hits:      {bs['hits']}")
        print(f"  Misses:    {bs['misses']}")
        print(f"  Evictions: {bs['evictions']}")
        
        print(f"\nPREDICTOR ACCURACY:")
        ps = self.predictor_stats
        print(f"  Avg hit rate:   {ps['avg_hit_rate']*100:.1f}%")
        print(f"  Best token:     {ps['best_token']*100:.1f}%")
        print(f"  Worst token:    {ps['worst_token']*100:.1f}%")
        
        print(f"\nTIMING:")
        ts = self.timing_stats
        print(f"  Avg total/token: {ts['avg_total_ms']:.1f} ms")
        print(f"  Avg stall:       {ts['avg_stall_ms']:.1f} ms")
        print(f"  Avg overlap:     {ts['avg_overlap_ms']:.1f} ms")
        print(f"  Tokens/sec:      {ts['tokens_per_sec']:.2f}")
        
        if ps['hot_hit_rate'] is not None:
            print(f"\nHOT EXPERTS:")
            print(f"  Hit rate on hot:     {ps['hot_hit_rate']*100:.1f}%")
            print(f"  Hit rate on cold:    {ps['cold_hit_rate']*100:.1f}%")
        
        print("=" * 60)


def run_simulation(config: SimConfig, verbose: bool = False) -> SimulationResult:
    """Run a complete simulation"""
    
    # 1. Generate workload
    gen = AccessPatternGenerator(config)
    sequence = gen.generate_token_sequence()
    n_tokens = len(sequence)
    
    if verbose:
        print(f"Generated {n_tokens} tokens * {config.model.n_layers} layers")
        # Print expert popularity stats
        freq = gen.get_expert_frequency(sequence)
        top_n = sorted(enumerate(freq), key=lambda x: -x[1])[:5]
        print(f"Top 5 experts: {top_n}")
        hot_total = sum(freq[e] for e in gen.hot_experts)
        print(f"Hot expert traffic: {hot_total/sum(freq)*100:.1f}%")
    
    # 2. Initialize buffer + predictor
    buffer = StreamingBuffer(config)
    predictor = Predictor(config, access_generator=gen)
    
    # Set up future-aware predictor if needed
    if config.predictor.model in ("perfect", "simulated_accuracy"):
        predictor.set_perfect_future(sequence)
    
    # 3. Timing simulator
    timing = TimingSimulator(config)
    
    # 4. Run token-by-token
    all_timings = []
    predictor_hit_rates = []
    
    for token_idx, token_layers in enumerate(sequence):
        # a) Predict weights
        pred_result = predictor.predict(token_idx)
        
        # Evaluate prediction accuracy (skip perfect = always 100%)
        if config.predictor.model != "perfect":
            # Get all experts used across all layers for this token
            token_experts = []
            for layer_experts in token_layers:
                token_experts.extend(layer_experts)
            
            pred_result = predictor.evaluate_prediction(pred_result, token_experts)
            predictor_hit_rates.append(pred_result.hit_rate)
            
            # Update predictor for online-learning models
            if config.predictor.model == "heuristic":
                predictor.observe(token_experts)
        
        # b) Access buffer for each layer
        pre_fetched = 0
        missed = 0
        layer_hits = []
        
        for experts in token_layers:
            for exp_id in experts:
                # Check if expert is in predicted set → priority boost
                predicted_priority = 0.0
                if config.buffer.predict_boost:
                    for pe, pc in pred_result.predicted_experts:
                        if pe == exp_id:
                            predicted_priority = pc
                            break
                
                hit = buffer.access(exp_id, priority=predicted_priority)
                if hit:
                    pre_fetched += 1
                    layer_hits.append(exp_id)
                else:
                    missed += 1
        
        # c) Simulate timing
        timing_result = timing.simulate_token(
            token_idx, pre_fetched, missed, 
            predictor_confidence=pred_result.hit_rate if pred_result.hit_rate > 0 else 0.0
        )
        all_timings.append(timing_result)
        
        if verbose and token_idx % 200 == 0:
                print(f"  Token {token_idx}: buf_hit={buffer.get_stats().hit_rate*100:.1f}% "
                      f"pred_hit={pred_result.hit_rate*100:.1f}% "
                      f"time_ms={timing_result.total_time_us/1000:.1f}")
    
    # 5. Collect stats
    buffer_stats = buffer.get_stats()
    
    # Predictor stats
    avg_pred_hit = sum(predictor_hit_rates) / max(1, len(predictor_hit_rates)) if predictor_hit_rates else 0.0
    best_pred = max(predictor_hit_rates) if predictor_hit_rates else 0.0
    worst_pred = min(predictor_hit_rates) if predictor_hit_rates else 0.0
    
    # Hot vs cold expert hit rates
    hot_hits = sum(buffer_stats.expert_hits[e] for e in gen.hot_experts if e in buffer_stats.expert_hits)
    hot_misses = sum(buffer_stats.expert_misses[e] for e in gen.hot_experts if e in buffer_stats.expert_misses)
    cold_hits = sum(v for k, v in buffer_stats.expert_hits.items() if k not in gen.hot_experts)
    cold_misses = sum(v for k, v in buffer_stats.expert_misses.items() if k not in gen.hot_experts)
    
    hot_hit_rate = hot_hits / max(1, hot_hits + hot_misses)
    cold_hit_rate = cold_hits / max(1, cold_hits + cold_misses)
    
    # Timing stats
    avg_total = sum(t.total_time_us for t in all_timings) / max(1, len(all_timings))
    avg_stall = sum(t.stall_time_us for t in all_timings) / max(1, len(all_timings))
    avg_overlap = sum(t.overlap_time_us for t in all_timings) / max(1, len(all_timings))
    
    result = SimulationResult(
        config={
            "model": "K3-sim",
            "n_experts": config.model.n_experts,
            "n_active": config.model.n_active,
            "n_layers": config.model.n_layers,
            "buffer_size_mb": config.buffer.size_mb,
            "eviction_policy": config.buffer.eviction_policy,
            "predictor": config.predictor.model,
            "n_tokens": n_tokens,
            "zipf_alpha": config.workload.zipf_alpha,
            "temporal_locality": config.workload.temporal_locality,
        },
        buffer_stats={
            "hit_rate": buffer_stats.hit_rate,
            "hits": buffer_stats.hits,
            "misses": buffer_stats.misses,
            "evictions": buffer_stats.evictions,
        },
        predictor_stats={
            "avg_hit_rate": avg_pred_hit,
            "best_token": best_pred,
            "worst_token": worst_pred,
            "hot_hit_rate": hot_hit_rate,
            "cold_hit_rate": cold_hit_rate,
        },
        timing_stats={
            "avg_total_ms": avg_total / 1000,
            "avg_stall_ms": avg_stall / 1000,
            "avg_overlap_ms": avg_overlap / 1000,
            "tokens_per_sec": 1_000_000 / max(1, avg_total),
        }
    )
    
    return result


def sweep_buffer_size():
    """Sweep: buffer size vs hit rate"""
    timing_ms = SimConfig().timing.compute_time_per_token_us / 1000
    print(f"\nSWEEP: Buffer Size vs Hit Rate (timing: {timing_ms:.0f}ms/token)")
    print("-" * 60)
    
    sizes = [64, 128, 256, 512, 1024]
    policies = ["lru", "lfu", "lru_priority"]
    
    for policy in policies:
        print(f"\nPolicy: {policy}")
        for size in sizes:
            cfg = SimConfig()
            cfg.buffer.size_mb = size
            cfg.buffer.eviction_policy = policy
            cfg.predictor.model = "heuristic"
            
            result = run_simulation(cfg)
            bs = result.buffer_stats
            ts = result.timing_stats
            print(f"  {size:>4} MB -> hit={bs['hit_rate']*100:5.1f}%  "
                  f"t/s={ts['tokens_per_sec']:.2f}  "
                  f"stall={ts['avg_stall_ms']:5.0f}ms")


def sweep_predictor():
    """Compare predictor models"""
    print("\nSWEEP: Predictor Comparison")
    print("-" * 50)
    
    # Perfect predictor (upper bound)
    cfg = SimConfig()
    cfg.predictor.model = "perfect"
    result = run_simulation(cfg)
    print(f"\n  Perfect predictor:")
    print(f"    Buffer hit: {result.buffer_stats['hit_rate']*100:.1f}%")
    print(f"    Tokens/sec: {result.timing_stats['tokens_per_sec']:.2f}")
    
    # Heuristic predictor (baseline)
    cfg2 = SimConfig()
    cfg2.predictor.model = "heuristic"
    result2 = run_simulation(cfg2)
    print(f"\n  Heuristic predictor:")
    print(f"    Predictor hit: {result2.predictor_stats['avg_hit_rate']*100:.1f}%")
    print(f"    Buffer hit:    {result2.buffer_stats['hit_rate']*100:.1f}%")
    print(f"    Tokens/sec:    {result2.timing_stats['tokens_per_sec']:.2f}")


def sweep_accuracy():
    """
    Sweep: predictor accuracy vs buffer hit rate vs throughput.
    
    Tests both LFU (best static) and LRU+priority (prediction-aware)
    to find the accuracy threshold where LRU+priority becomes competitive.
    
    Uses simulated_accuracy mode to inject controlled prediction errors.
    With shared_experts_per_token=True for realistic K3 workload.
    """
    print("\nSWEEP: Predictor Accuracy vs Performance")
    print("=" * 60)
    
    accuracies = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    policies = ["lfu", "lru_priority"]
    
    results = {p: [] for p in policies}
    
    for policy in policies:
        print(f"\n--- Policy: {policy.upper()} ---")
        
        for target_acc in accuracies:
            cfg = SimConfig()
            cfg.predictor.model = "simulated_accuracy"
            cfg.predictor.accuracy_level = target_acc
            cfg.buffer.eviction_policy = policy
            cfg.buffer.size_mb = 512
            cfg.buffer.predict_boost = True
            
            res = run_simulation(cfg)
            actual_acc = res.predictor_stats['avg_hit_rate']
            results[policy].append((target_acc, res))
            
            print(f"  Acc {target_acc:.0%} -> actual={actual_acc*100:5.1f}%  "
                  f"buf={res.buffer_stats['hit_rate']*100:5.1f}%  "
                  f"stall={res.timing_stats['avg_stall_ms']:5.1f}ms  "
                  f"t/s={res.timing_stats['tokens_per_sec']:5.2f}")
    
    # Comparison table
    print(f"\n{'=' * 100}")
    print(f"{'ACCURACY SWEEP — LFU vs LRU+PRIORITY':^100}")
    print(f"{'=' * 100}")
    header = f"{'Accuracy':>10} | {'Actual':>7} | "
    header += f"{'B.Hit(LFU)':>10} | {'t/s(LFU)':>9} | "
    header += f"{'B.Hit(LRU+P)':>11} | {'t/s(LRU+P)':>10}"
    print(header)
    print(f"{'-'*10}-+-{'-'*7}-+-{'-'*10}-+-{'-'*9}-+-{'-'*11}-+-{'-'*10}")
    
    for i, target_acc in enumerate(accuracies):
        actual = results["lfu"][i][1].predictor_stats['avg_hit_rate'] * 100
        lfu_hit = results["lfu"][i][1].buffer_stats['hit_rate'] * 100
        lfu_tps = results["lfu"][i][1].timing_stats['tokens_per_sec']
        lru_hit = results["lru_priority"][i][1].buffer_stats['hit_rate'] * 100
        lru_tps = results["lru_priority"][i][1].timing_stats['tokens_per_sec']
        
        print(f"{target_acc:>9.0%} | {actual:>6.1f}% | "
              f"{lfu_hit:>9.1f}% | {lfu_tps:>8.2f} | "
              f"{lru_hit:>10.1f}% | {lru_tps:>9.2f}")
    
    # Perfect reference (LRU+priority, 100% accuracy)
    cfg_perf = SimConfig()
    cfg_perf.predictor.model = "perfect"
    cfg_perf.buffer.eviction_policy = "lru_priority"
    cfg_perf.buffer.size_mb = 512
    res_perf = run_simulation(cfg_perf)
    
    print(f"{'100%(perfect)':>10} | {'100.0%':>7} | "
          f"{'n/a':>9} | {'n/a':>8} | "
          f"{res_perf.buffer_stats['hit_rate']*100:>10.1f}% | {res_perf.timing_stats['tokens_per_sec']:>9.2f}")
    print(f"{'=' * 100}")
    
    # Compute crossover point
    print(f"\nCROSSOVER ANALYSIS:")
    print(f"  LFU baseline:      {results['lfu'][5][1].buffer_stats['hit_rate']*100:.1f}% "
          f"(@ {results['lfu'][5][0]:.0%} accuracy)")
    print(f"  LRU+P best:        {res_perf.buffer_stats['hit_rate']*100:.1f}% "
          f"(@ perfect predictor)")
    
    for i, target_acc in enumerate(accuracies):
        lfu_hit = results["lfu"][i][1].buffer_stats['hit_rate'] * 100
        lru_hit = results["lru_priority"][i][1].buffer_stats['hit_rate'] * 100
        if lru_hit >= lfu_hit:
            print(f"  ==> CROSSOVER at ~{target_acc:.0%} accuracy "
                  f"(LRU+P {lru_hit:.1f}% >= LFU {lfu_hit:.1f}%)")
            break
    else:
        print(f"  ==> No crossover: LRU+P never exceeds LFU in tested range")
    
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Speculative Weight Streaming Simulator")
    parser.add_argument("--mode", choices=["single", "sweep-buffer", "sweep-predictor", "sweep-accuracy"],
                       default="single", help="Simulation mode")
    parser.add_argument("--buffer-size", type=int, default=256, help="Buffer size in MB")
    parser.add_argument("--policy", choices=["lru", "lfu", "lru_priority"],
                       default="lru_priority", help="Eviction policy")
    parser.add_argument("--predictor", choices=["perfect", "heuristic", "simulated_accuracy"],
                       default="heuristic", help="Predictor model")
    parser.add_argument("--accuracy", type=float, default=0.7, help="Target accuracy (simulated_accuracy)")
    parser.add_argument("--tokens", type=int, default=1000, help="Number of tokens")
    parser.add_argument("--verbose", "-v", action="store_true")
    
    args = parser.parse_args()
    
    if args.mode == "sweep-buffer":
        sweep_buffer_size()
    elif args.mode == "sweep-predictor":
        sweep_predictor()
    elif args.mode == "sweep-accuracy":
        sweep_accuracy()
    else:
        cfg = SimConfig()
        cfg.buffer.size_mb = args.buffer_size
        cfg.buffer.eviction_policy = args.policy
        cfg.predictor.model = args.predictor
        cfg.predictor.accuracy_level = args.accuracy
        cfg.workload.n_tokens = args.tokens
        
        result = run_simulation(cfg, verbose=args.verbose)
        result.print_summary()
