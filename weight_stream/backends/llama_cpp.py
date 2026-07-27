"""
llama-cpp-python backend adapter for weight streaming.

Architecture:
- Opens GGUF model via llama-cpp-python (uses mmap=True by default)
- Creates a StreamingBuffer tracking the same memory-mapped file
- During generation, tracks shard-level access patterns
- Prefetches predicted shards during compute time (~815ms per token)

NOTE: Expert-level routing is opaque from Python (internal to C++).
      We use file-level shard tracking + pattern learning instead.
      Expert routing interception requires a C++ patch (Phase 4).

Usage:
    from weight_stream.backends.llama_cpp import WeightStreamModel
    
    model = WeightStreamModel("model.gguf", buffer_mb=64)
    output = model.generate("Hello", max_tokens=100)
"""
import logging
import mmap
import os
import time
from typing import Any, Dict, Iterator, List, Optional

from ..core.buffer import StreamingBuffer, SHARD_SIZE
from ..core.predictor import HeuristicPredictor
from ..core.prefetcher import Prefetcher
from ..gguf import GGUFParser

logger = logging.getLogger(__name__)

# Lazy import so this module is loadable without llama-cpp-python installed
_llama_cpp = None


def _get_llama():
    global _llama_cpp
    if _llama_cpp is None:
        import llama_cpp as _llama_cpp
    return _llama_cpp


class WeightStreamModel:
    """
    Weight-streaming model that wraps llama-cpp-python with speculative prefetch.
    
    Opens the GGUF model with mmap and overlays a smart buffer that tracks
    which shards are hot and predicts which will be needed next.
    
    Args:
        model_path: path to GGUF model file
        buffer_mb: buffer size in MB (default: 64)
        n_ctx: context size (default: 512)
        n_threads: inference threads (default: CPU count)
        verbose: enable detailed logging (default: False)
        **kwargs: additional args passed to llama_cpp.Llama
    """
    
    def __init__(
        self,
        model_path: str,
        buffer_mb: int = 64,
        n_ctx: int = 512,
        n_threads: Optional[int] = None,
        verbose: bool = False,
        **kwargs,
    ):
        self.model_path = model_path
        self.buffer_mb = buffer_mb
        self.n_ctx = n_ctx
        self.verbose = verbose
        
        if verbose:
            logging.basicConfig(level=logging.DEBUG)
        
        # Resolve file path
        model_path = os.path.abspath(model_path)
        file_size = os.path.getsize(model_path)
        logger.info(
            f"Loading model: {model_path} "
            f"({file_size / 1024**3:.2f} GB)"
        )
        
        # Step 1: Open the model file as mmap (independent of llama-cpp-python)
        self._file = open(model_path, "rb")
        self._mmap = mmap.mmap(
            self._file.fileno(),
            file_size,
            access=mmap.ACCESS_READ,
        )
        logger.info(f"File mmap'd: {file_size / 1024**3:.2f} GB")
        
        # Step 2: Create buffer + predictor + prefetcher
        self.buffer = StreamingBuffer(
            mmap_obj=self._mmap,
            total_size=file_size,
            capacity_mb=buffer_mb,
        )
        self.predictor = HeuristicPredictor()
        self.prefetcher = Prefetcher(
            buffer=self.buffer,
            predictor=self.predictor,
        )
        
        # Step 3: Parse GGUF for expert-aware tensor mapping
        self._gguf = GGUFParser(model_path)
        self._expert_map = self._gguf.get_expert_map()
        self._expert_tensors = self._gguf.get_expert_tensors()
        logger.info(
            f"Expert map: {len(self._expert_map)} layers, "
            f"{sum(len(e) for e in self._expert_map.values())} experts total, "
            f"per-expert ~{self._get_avg_expert_size() / 1024:.1f} KB"
        )
        
        # Step 4: Open the model with llama-cpp-python
        llm = _get_llama()
        self._llm = llm.Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_threads=n_threads or os.cpu_count() or 4,
            use_mmap=True,
            verbose=verbose,
            **kwargs,
        )
        
        # Metadata
        self._metadata = self._llm.metadata if hasattr(self._llm, 'metadata') else {}
        self.n_experts = int(
            self._metadata.get(
                f"{self._get_arch()}.expert_count",
                self._metadata.get("expert_count", 0)
            )
        )
        self.n_experts_used = int(
            self._metadata.get(
                f"{self._get_arch()}.expert_used_count",
                self._metadata.get("expert_used_count", 0)
            )
        )
        logger.info(
            f"Model: {self.n_experts} experts, "
            f"{self.n_experts_used} used per token"
        )
        
        # Warm up buffer with initial shards
        self._warm_up_buffer()
        
        self.prefetcher.start()
        logger.info("WeightStreamModel ready")
    
    def generate(
        self,
        prompt: str,
        max_tokens: int = 128,
        temperature: float = 0.7,
        top_p: float = 0.9,
        **kwargs,
    ) -> str:
        """
        Generate text with weight streaming.
        
        During generation, the prefetcher runs in background,
        predicting and loading hot shards during compute time.
        """
        output = ""
        
        # Track which shards are accessed during generation
        shard_access_log = []
        
        # Use streaming to track per-token progress
        stream = self._llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stream=True,
            **kwargs,
        )
        
        start_time = time.time()
        token_count = 0
        
        for chunk in stream:
            if "choices" in chunk and len(chunk["choices"]) > 0:
                text = chunk["choices"][0].get("text", "")
                output += text
                token_count += 1
                
                # Record file access pattern for this token
                # We can't see expert routing, but we can infer from
                # which file regions were accessed (via buffer stats)
                
                        # Expert-aware prefetch: load next token's experts during compute
                # Since expert routing is opaque from Python, we prefetch via
                # round-robin across layers. Each token loads ~1 layer worth of experts.
                if token_count > 0 and token_count % 3 == 0:
                    target_layer = (token_count // 3) % max(len(self._expert_map), 1)
                    self._prefetch_layer_experts(target_layer)
                
                # Record buffer state
                if hasattr(self.buffer, 'get_hot_set'):
                    shard_access_log.append({
                        'token': token_count,
                        'hot_shards': len(self.buffer),
                        'hit_rate': self.buffer.hit_rate,
                    })
        
        elapsed = time.time() - start_time
        tokens_per_sec = token_count / elapsed if elapsed > 0 else 0
        
        stats = self.buffer.get_stats()
        logger.info(
            f"Generation: {token_count} tokens in {elapsed:.2f}s "
            f"({tokens_per_sec:.2f} tok/s), "
            f"buffer hit rate: {stats['hit_rate']:.1%}"
        )
        
        return output
    
    def close(self):
        """Clean up resources"""
        self.prefetcher.stop()
        self._llm.close()
        if self._mmap:
            self._mmap.close()
        if self._file:
            self._file.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """Return all system statistics"""
        return {
            'buffer': self.buffer.get_stats(),
            'predictor': self.predictor.get_stats(),
            'prefetcher': {
                'prefetched': self.prefetcher.prefetched_count,
                'useful': self.prefetcher.useful_prefetches,
            },
        }
    
    def _get_arch(self) -> str:
        """Get model architecture name from metadata"""
        return self._metadata.get(
            "general.architecture", 
            self._metadata.get("architecture", "unknown")
        )
    
    def _warm_up_buffer(self):
        """Preload initial shards into buffer"""
        # Touch first 64MB of file to ensure metadata tensors are hot
        # Preload first 64MB (metadata + shared layers)
        warm_size = min(
            self.buffer_mb * 1024 * 1024,
            self._mmap.size() // 4
        )
        _ = self._mmap[:warm_size]
        logger.info(f"Warm-up: {warm_size / 1024**2:.1f} MB loaded")
        
        # Prefetch layer-0 experts for first-token acceleration
        self._prefetch_layer0()
        
        # Warm up predictor with initial knowledge
        self._warm_predictor()
    
    def _prefetch_layer0(self):
        """Prefetch all experts in layer 0 for faster first-token."""
        if 0 in self._expert_map:
            for ei, ranges in self._expert_map[0].items():
                for r in ranges:
                    offset = r.start_offset
                    length = min(r.size_bytes, self._mmap.size() - offset)
                    _ = self._mmap[offset:offset + length]
            logger.info(
                f"Prefetched layer-0: "
                f"{len(self._expert_map[0])} experts"
            )
    
    def _get_avg_expert_size(self) -> int:
        """Get average per-expert size in bytes."""
        if not self._expert_tensors:
            return 4 * 1024 * 1024  # default 4MB
        total = 0
        count = 0
        for t in self._expert_tensors:
            total += t.per_expert_size
            count += 1
        return total // count if count > 0 else 4 * 1024 * 1024
    
    def _prefetch_layer_experts(self, layer_id: int):
        """Prefetch all experts in a given layer using GGUF expert map."""
        if layer_id in self._expert_map:
            for ei, ranges in self._expert_map[layer_id].items():
                self.prefetcher.prefetch_experts(ranges, self._mmap)
    
    def _warm_predictor(self):
        """Warm up heuristic predictor with sequential pattern knowledge."""
        n_layers = len(self._expert_map)
        n_experts = max((len(e) for e in self._expert_map.values()), default=60)
        
        # Seed predictor with sequential access pattern
        for i in range(min(100, n_layers * n_experts)):
            layer = i % n_layers if n_layers > 0 else 0
            expert = i % n_experts if n_experts > 0 else 0
            # Predictor records shard access pattern
            self.predictor.observe(expert)
        
        logger.debug(f"Predictor warmed: {n_layers}L x {n_experts}E pattern")
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()
