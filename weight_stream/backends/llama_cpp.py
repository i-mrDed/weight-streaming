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
from ..io.page_faults import page_fault_count, paging_demand, hard_fault_count
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
        arch_hint = self._detect_gguf_architecture(model_path)
        try:
            llm = _get_llama()
            # Leave chat_format unset by default. llama-cpp-python can then use
            # the tokenizer.chat_template embedded in the GGUF, instead of
            # incorrectly forcing ChatML on every architecture.
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
            if hasattr(self, '_gguf') and self._gguf:
                try:
                    self._gguf.close()
                except Exception:
                    pass
            err_msg = str(e)
            # Detect unsupported architecture and give actionable guidance
            if "unknown model architecture" in err_msg.lower() or "Failed to load model from file" in err_msg:
                raise ModelError(
                    f"Cannot load this model: architecture '{arch_hint or 'unknown'}' "
                    f"is not supported by the installed llama-cpp-python. "
                    f"Qwen3.5/Qwen3.6 models need a newer build. "
                    f"Upgrade with: pip install -U llama-cpp-python  "
                    f"(current may be too old). "
                    f"Or use a supported model (e.g. Qwen1.5/Qwen2/Llama/Mistral GGUF).",
                    model_path=model_path,
                    details={
                        "load_error": err_msg,
                        "architecture": arch_hint,
                        "hint": "pip install -U llama-cpp-python",
                    },
                )
            raise ModelError(
                f"Failed to load model with llama-cpp-python: {e}",
                model_path=model_path,
                details={"load_error": err_msg, "architecture": arch_hint},
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
        faults_before = page_fault_count()  # None if platform unsupported
        hard_before = hard_fault_count()    # POSIX only (None on Windows)
        # Cached residency sample (free — no new QueryWorkingSetEx call).
        res_before = (self._page_monitor.get_resident_bytes()
                      if self._page_monitor else None)
        
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
        paging = paging_demand(
            faults_before, page_fault_count(), token_count,
            hard_before=hard_before, hard_after=hard_fault_count(),
            residency_before_bytes=res_before,
            residency_after_bytes=(self._page_monitor.get_resident_bytes()
                                   if self._page_monitor else None),
        )
        if paging is not None:
            self._last_gen_stats['paging'] = paging
        
        return output
    
    def stream_chat(
        self,
        messages: List[dict],
        max_tokens: int = 128,
        temperature: float = 0.7,
        top_p: float = 0.9,
        repeat_penalty: float = 1.15,
        **kwargs,
    ) -> Iterator[str]:
        """
        Stream a chat response as text chunks through the public wrapper.

        This is the server-facing chat API: server code must consume this
        method and never touch ``_llm`` directly, so that generation stats
        and page-cache telemetry are always recorded.

        Uses the GGUF-native chat template first (``create_chat_completion``);
        GGUFs without a usable template fall back to the architecture-aware
        prompt formatter.

        Records generation stats (``_last_gen_stats``) on completion, on
        error, and on early close (client cancellation), and samples the OS
        page cache periodically during generation.

        No per-token prefetch is driven from here on purpose: expert routing
        is opaque from Python, so there is no real routing evidence to base
        prefetch decisions on.

        Yields:
            Text chunks (delta content) as strings.

        Raises:
            GenerationError: If the model is not loaded or generation fails.
        """
        if not self.is_loaded:
            raise GenerationError(
                "Model not loaded",
                details={"model_path": self._model_path},
            )

        use_native = True
        try:
            stream = self._llm.create_chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                repeat_penalty=repeat_penalty,
                stream=True,
                **kwargs,
            )
        except Exception as ex:
            # GGUFs without a usable template retain the legacy prompt
            # formatter as a compatibility fallback.
            logger.warning(
                f"Native chat template unavailable ({ex}); using fallback prompt"
            )
            use_native = False
            prompt = self._format_chat_prompt(messages, arch=self._get_arch())
            stream = self._llm(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                repeat_penalty=repeat_penalty,
                stop=[
                    "\nUser:", "\nSystem:", "\n\nUser", "\n\nSystem",
                    "<|im_end|>", "<|im_start|>", "<|eot_id|>",
                ],
                stream=True,
                **kwargs,
            )

        token_count = 0
        start_time = time.time()
        faults_before = page_fault_count()  # None if platform unsupported
        hard_before = hard_fault_count()    # POSIX only (None on Windows)
        # Cached residency sample (free — no new QueryWorkingSetEx call).
        res_before = (self._page_monitor.get_resident_bytes()
                      if self._page_monitor else None)
        try:
            for chunk in stream:
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                if use_native:
                    text = (choice.get("delta") or {}).get("content", "")
                else:
                    text = choice.get("text", "")
                if not text:
                    continue
                token_count += 1
                yield text

                # Sample the OS page cache periodically (real measurement).
                if token_count % 5 == 0 and self._page_monitor:
                    try:
                        self._page_monitor.sample_resident_pages()
                    except Exception:
                        pass
        except GeneratorExit:
            # Consumer stopped early (client disconnect / cancellation).
            # llama.cpp streams are lazy; stopping iteration also stops
            # further token computation.
            raise
        except Exception as e:
            raise GenerationError(
                f"Chat generation failed at token {token_count}: {e}",
                token_count=token_count or None,
                details={"error": str(e)},
            )
        finally:
            elapsed = time.time() - start_time
            tokens_per_sec = token_count / elapsed if elapsed > 0 else 0
            self._last_gen_stats = {
                "token_count": token_count,
                "elapsed": elapsed,
                "tokens_per_sec": tokens_per_sec,
                "prompt": self._summarize_messages(messages),
            }
            paging = paging_demand(
                faults_before, page_fault_count(), token_count,
                hard_before=hard_before, hard_after=hard_fault_count(),
                residency_before_bytes=res_before,
                residency_after_bytes=(self._page_monitor.get_resident_bytes()
                                       if self._page_monitor else None),
            )
            if paging is not None:
                self._last_gen_stats["paging"] = paging
            if self._page_monitor:
                try:
                    self._page_monitor.sample_resident_pages()
                except Exception:
                    pass

    @staticmethod
    def _format_chat_prompt(messages: List[dict], arch: str = "") -> str:
        """
        Format chat messages using native chat template markers
        (ChatML, Llama-3, Instruct). Fallback path only, used when a GGUF
        has no usable embedded chat template.
        """
        system = "You are a helpful assistant."
        for msg in messages:
            if msg.get("role") == "system" and msg.get("content"):
                system = msg["content"].strip()

        arch_lower = (arch or "").lower()
        if "qwen" in arch_lower or "deepseek" in arch_lower:
            prompt = f"<|im_start|>system\n{system}<|im_end|>\n"
            for msg in messages:
                r = msg.get("role")
                c = (msg.get("content") or "").strip()
                if r == "user":
                    prompt += f"<|im_start|>user\n{c}<|im_end|>\n"
                elif r == "assistant":
                    prompt += f"<|im_start|>assistant\n{c}<|im_end|>\n"
            prompt += "<|im_start|>assistant\n"
            return prompt
        elif "llama" in arch_lower:
            prompt = (
                f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>"
                f"\n\n{system}<|eot_id|>"
            )
            for msg in messages:
                r = msg.get("role")
                c = (msg.get("content") or "").strip()
                if r == "user":
                    prompt += (
                        f"<|start_header_id|>user<|end_header_id|>\n\n{c}<|eot_id|>"
                    )
                elif r == "assistant":
                    prompt += (
                        f"<|start_header_id|>assistant<|end_header_id|>"
                        f"\n\n{c}<|eot_id|>"
                    )
            prompt += "<|start_header_id|>assistant<|end_header_id|>\n\n"
            return prompt
        else:
            parts = []
            for msg in messages:
                role = msg.get("role", "user")
                content = (msg.get("content") or "").strip()
                if role == "system" and content:
                    system = content
                elif role == "user":
                    parts.append(f"User: {content}")
                elif role == "assistant":
                    parts.append(f"Assistant: {content}")
            prompt = f"System: {system}\n\n" + "\n".join(parts) + "\nAssistant:"
            return prompt

    @staticmethod
    def _summarize_messages(messages: List[dict]) -> str:
        """Short prompt label for generation stats."""
        last = ""
        for msg in messages:
            if msg.get("role") == "user" and msg.get("content"):
                last = msg["content"]
        if not last and messages:
            last = messages[-1].get("content") or ""
        last = str(last)
        return last[:50] + ("..." if len(last) > 50 else "")

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
    
    @staticmethod
    def _detect_gguf_architecture(model_path: str) -> str:
        """Read general.architecture from GGUF without full model load."""
        try:
            from gguf import GGUFReader
            reader = GGUFReader(model_path)
            field = reader.fields.get("general.architecture")
            if field is None:
                return "unknown"
            # gguf field parts: last part holds the string data
            try:
                data = field.parts[-1]
                if isinstance(data, (bytes, bytearray)):
                    return bytes(data).decode("utf-8", errors="replace").strip("\x00")
                if hasattr(data, "tobytes"):
                    return data.tobytes().decode("utf-8", errors="replace").strip("\x00")
                return str(data)
            except Exception:
                return "unknown"
        except Exception:
            return "unknown"
    
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
