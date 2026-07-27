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
import ctypes
import logging
import mmap
import os
import time
from typing import Any, Dict, Iterator, List, Optional

from ..core.buffer import StreamingBuffer, SHARD_SIZE
from ..core.predictor import HeuristicPredictor
from ..core.prefetcher import Prefetcher
from ..gguf import GGUFParser
from ..io.win_perf import WindowsPageMonitor
from ._base import WeightStreamBackend
from ..core.exceptions import ModelError, GenerationError, ConfigError

logger = logging.getLogger(__name__)

# Lazy import so this module is loadable without llama-cpp-python installed
_llama_cpp = None


def _get_llama():
    global _llama_cpp
    if _llama_cpp is None:
        import llama_cpp as _llama_cpp
    return _llama_cpp


class WeightStreamModel(WeightStreamBackend):
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
        # Validate parameters
        if buffer_mb < 1:
            raise ConfigError("buffer_mb must be >= 1", {"buffer_mb": buffer_mb})
        if n_ctx < 8:
            raise ConfigError("n_ctx must be >= 8", {"n_ctx": n_ctx})
        
        self._model_path = model_path
        self._initialized = False
        self.buffer_mb = buffer_mb
        self.n_ctx = n_ctx
        self.verbose = verbose
        
        if verbose:
            logging.basicConfig(level=logging.DEBUG)
        
        # Resolve file path — early validation
        try:
            resolved_path = os.path.abspath(model_path)
            if not os.path.isfile(resolved_path):
                raise ModelError(
                    f"Model file not found: {model_path}",
                    model_path=model_path,
                )
            file_size = os.path.getsize(resolved_path)
        except OSError as e:
            raise ModelError(
                f"Cannot access model file: {e}",
                model_path=model_path,
                details={"os_error": str(e)},
            )
        
        model_path = resolved_path
        logger.info(
            f"Loading model: {model_path} "
            f"({file_size / 1024**3:.2f} GB)"
        )
        
        # Step 1: Open the model file as mmap (independent of llama-cpp-python)
        try:
            self._file = open(model_path, "rb")
            self._mmap = mmap.mmap(
                self._file.fileno(),
                file_size,
                access=mmap.ACCESS_READ,
            )
        except (OSError, ValueError) as e:
            raise ModelError(
                f"Failed to mmap model file: {e}",
                model_path=model_path,
                details={"os_error": str(e)},
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
        try:
            self._gguf = GGUFParser(model_path)
            self._expert_map = self._gguf.get_expert_map()
            self._expert_tensors = self._gguf.get_expert_tensors()
        except Exception as e:
            raise ModelError(
                f"Failed to parse GGUF metadata: {e}",
                model_path=model_path,
                details={"parse_error": str(e)},
            )
        logger.info(
            f"Expert map: {len(self._expert_map)} layers, "
            f"{sum(len(e) for e in self._expert_map.values())} experts total, "
            f"per-expert ~{self._get_avg_expert_size() / 1024:.1f} KB"
        )
        
        # Step 4: Open the model with llama-cpp-python
        try:
            llm = _get_llama()
            # Prefer ChatML format (Qwen, many instruct models) unless caller overrides
            if "chat_format" not in kwargs:
                kwargs["chat_format"] = "chatml"
            self._llm = llm.Llama(
                model_path=model_path,
                n_ctx=n_ctx,
                n_threads=n_threads or os.cpu_count() or 4,
                use_mmap=True,
                verbose=verbose,
                **kwargs,
            )
        except Exception as e:
            # Clean up mmap before re-raising
            self._mmap.close()
            self._file.close()
            raise ModelError(
                f"Failed to load model with llama-cpp-python: {e}",
                model_path=model_path,
                details={"load_error": str(e)},
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
        
        # Step 5: Get mmap address for page monitoring
        self._page_monitor = None
        try:
            import numpy as np
            # Keep numpy buffer alive (holds pointer to mmap address)
            self._mmap_buf = np.frombuffer(self._mmap, dtype=np.uint8, count=1)
            mmap_addr = self._mmap_buf.ctypes.data
            logger.debug(f"mmap address: 0x{mmap_addr:x}")
            self._page_monitor = WindowsPageMonitor(
                mmap_addr=mmap_addr,
                mmap_size=file_size,
            )
            # Test sample
            res = self._page_monitor.sample_resident_pages()
            logger.info(
                f"Page cache monitor active: "
                f"{self._page_monitor.get_resident_ratio():.1%} resident"
            )
        except Exception as e:
            import traceback
            logger.warning(f"Page monitor init failed: {e}\n{traceback.format_exc()}")
        
        # Warm up buffer with initial shards
        self._warm_up_buffer()
        
        self.prefetcher.start()
        self._initialized = True
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
        if not self.is_loaded:
            raise GenerationError("Model not loaded", details={"model_path": self._model_path})
        
        output = ""
        shard_access_log = []
        start_time = time.time()
        token_count = 0
        
        # Use streaming to track per-token progress
        try:
            stream = self._llm(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stream=True,
                **kwargs,
            )
        except Exception as e:
            raise GenerationError(
                f"Inference engine error: {e}",
                details={"error": str(e)},
            )
        
        try:
            for chunk in stream:
                if "choices" in chunk and len(chunk["choices"]) > 0:
                    text = chunk["choices"][0].get("text", "")
                    output += text
                    token_count += 1
                    
                    # Expert-aware prefetch: load next token's experts during compute
                    # Since expert routing is opaque from Python, we prefetch via
                    # round-robin across layers. Each token loads ~1 layer worth of experts.
                    if token_count > 0 and token_count % 3 == 0:
                        target_layer = (token_count // 3) % max(len(self._expert_map), 1)
                        self._prefetch_layer_experts(target_layer)
                    
                    # Sample page cache every 5 tokens
                    if token_count % 5 == 0 and self._page_monitor:
                        self._page_monitor.sample_resident_pages()
                    
                    # Record buffer state
                    if hasattr(self.buffer, 'get_hot_set'):
                        shard_access_log.append({
                            'token': token_count,
                            'hot_shards': len(self.buffer),
                            'hit_rate': self.buffer.hit_rate,
                        })
        except Exception as e:
            raise GenerationError(
                f"Generation failed at token {token_count}: {e}",
                token_count=token_count or None,
                details={"error": str(e)},
            )
        
        elapsed = time.time() - start_time
        tokens_per_sec = token_count / elapsed if elapsed > 0 else 0
        
        stats = self.buffer.get_stats()
        cache_info = ""
        if self._page_monitor:
            ratio = self._page_monitor.get_resident_ratio()
            cache_info = f", page cache: {ratio:.1%} resident"
        
        logger.info(
            f"Generation: {token_count} tokens in {elapsed:.2f}s "
            f"({tokens_per_sec:.2f} tok/s), "
            f"buffer hit rate: {stats['hit_rate']:.1%}"
            f"{cache_info}"
        )
        
        # Save generation stats for get_stats()
        self._last_gen_stats = {
            'token_count': token_count,
            'elapsed': elapsed,
            'tokens_per_sec': tokens_per_sec,
            'prompt': prompt[:50] + ('...' if len(prompt) > 50 else ''),
        }
        
        return output
    
    def close(self):
        """Clean up all resources. Safe to call multiple times."""
        if not self.is_loaded:
            return
        
        # Stop prefetcher first
        if hasattr(self, 'prefetcher') and self.prefetcher:
            self.prefetcher.stop()
        
        # Close inference engine
        if hasattr(self, '_llm') and self._llm:
            try:
                self._llm.close()
            except Exception:
                pass
            self._llm = None
        
        # Release numpy buffer before closing mmap
        if hasattr(self, '_mmap_buf') and self._mmap_buf is not None:
            self._mmap_buf = None
        
        # Close mmap
        if hasattr(self, '_mmap') and self._mmap:
            try:
                self._mmap.close()
            except BufferError:
                pass  # Some references may still exist
            self._mmap = None
        
        # Close file handle
        if hasattr(self, '_file') and self._file:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None
        
        # Close GGUF parser
        if hasattr(self, '_gguf') and self._gguf:
            try:
                self._gguf.close()
            except Exception:
                pass
            self._gguf = None
        
        self._initialized = False
        logger.debug("WeightStreamModel closed")
    
    def get_stats(self) -> Dict[str, Any]:
        """Return all system statistics"""
        buf_stats = self.buffer.get_stats()
        buf_stats['capacity_mb'] = self.buffer_mb
        
        pref_stats = {
            'prefetched': self.prefetcher.prefetched_count,
            'useful': getattr(self.prefetcher, 'useful_prefetches', 0),
            'queued': self.prefetcher._queue.qsize() if hasattr(self.prefetcher, '_queue') else 0,
        }
        
        gen_stats = {}
        if hasattr(self, '_last_gen_stats'):
            gen_stats = self._last_gen_stats
        
        page_stats = {}
        if self._page_monitor:
            page_stats = {
                'resident_ratio': self._page_monitor.get_resident_ratio(),
                'resident_gb': (self._page_monitor.get_resident_ratio() 
                               * self._page_monitor.mmap_size / 1024**3),
                'total_gb': self._page_monitor.mmap_size / 1024**3,
            }
        
        return {
            'buffer': buf_stats,
            'predictor': self.predictor.get_stats(),
            'prefetcher': pref_stats,
            'generation': gen_stats,
            'page_cache': page_stats,
            'model': {
                'path': self._model_path,
                'arch': self._get_arch(),
                'n_experts': getattr(self, 'n_experts', 0),
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
    
    @property
    def is_loaded(self) -> bool:
        """True if the model is loaded."""
        return hasattr(self, '_llm') and self._llm is not None
