"""
GGUF parser wrapper — uses the official `gguf` library.

Provides expert-aware tensor information: maps tensor names to file offsets
and builds per-expert offset ranges for targeted prefetching.

Usage:
    parser = GGUFParser("model.gguf")
    for t in parser.expert_tensors:
        print(f"{t.name}: offset={t.file_offset}, size={t.size_mb:.1f}MB")
    expert_map = parser.get_expert_map()
"""
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from gguf import GGUFReader, GGMLQuantizationType

logger = logging.getLogger(__name__)


@dataclass
class TensorInfo:
    """Describes one tensor in the GGUF file."""
    name: str
    shape: Tuple[int, ...]
    ggml_type: int
    file_offset: int       # absolute file offset of tensor data
    size_bytes: int        # total data size
    
    @property
    def type_name(self) -> str:
        try:
            return GGMLQuantizationType(self.ggml_type).name
        except ValueError:
            return f'type_{self.ggml_type}'
    
    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)
    
    @property
    def is_expert_weight(self) -> bool:
        """True if this tensor contains MoE expert weights."""
        name = self.name.lower()
        return ('exps' in name or 'expert' in name or 'moe' in name) and len(self.shape) >= 3
    
    @property
    def layer_id(self) -> int:
        m = re.search(r'blk\.(\d+)', self.name)
        return int(m.group(1)) if m else -1
    
    @property
    def projection_type(self) -> str:
        n = self.name.lower()
        if 'gate' in n: return 'gate'
        if 'up' in n and 'down' not in n: return 'up'
        if 'down' in n: return 'down'
        return 'other'
    
    @property
    def n_experts(self) -> int:
        """Number of experts in this tensor (last dimension)."""
        if self.is_expert_weight and len(self.shape) >= 3:
            return self.shape[-1]
        return 1
    
    @property
    def per_expert_size(self) -> int:
        """Bytes per single expert slice."""
        if self.n_experts > 0:
            return self.size_bytes // self.n_experts
        return self.size_bytes


@dataclass
class ExpertRange:
    """File offset range for a single expert's weight data."""
    layer: int
    expert_idx: int
    projection: str     # 'gate', 'up', 'down'
    start_offset: int
    end_offset: int
    size_bytes: int
    tensor_name: str


class GGUFParser:
    """
    GGUF model parser — wraps the official `gguf` library.
    
    Provides expert-aware tensor lookup and file offset mapping
    for targeted weight prefetching.
    
    Usage:
        parser = GGUFParser("model.gguf")
        tensor = parser.get_tensor("blk.0.ffn_gate.weight")
        expert_map = parser.get_expert_map()
        experts_for_layer = expert_map[0][3]  # layer 0, expert 3
    """
    
    def __init__(self, model_path: str):
        self.path = Path(model_path)
        self.file_size = self.path.stat().st_size
        
        logger.info(f"Parsing GGUF: {self.path.name} ({self.file_size / 1024**3:.2f} GB)")
        self._reader = GGUFReader(str(self.path))
        
        # Metadata
        self.metadata: Dict[str, Any] = {}
        self._extract_metadata()
        
        # Tensors
        self.tensors: List[TensorInfo] = []
        self._tensors_by_name: Dict[str, TensorInfo] = {}
        self._parse_tensors()
        
        self.n_tensors = len(self.tensors)
        logger.info(
            f"Parsed: {self.n_tensors} tensors, "
            f"{len(self.get_expert_tensors())} expert tensors"
        )
    
    def close(self):
        pass  # GGUFReader doesn't need explicit close
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()
    
    # ── Public API ──────────────────────────────────────────────────
    
    def get_tensor(self, name: str) -> Optional[TensorInfo]:
        return self._tensors_by_name.get(name)
    
    def get_tensors_by_pattern(self, pattern: str) -> List[TensorInfo]:
        import fnmatch
        return [t for t in self.tensors if fnmatch.fnmatch(t.name, pattern)]
    
    def get_expert_tensors(self) -> List[TensorInfo]:
        return [t for t in self.tensors if t.is_expert_weight]
    
    def get_expert_map(self) -> Dict[int, Dict[int, List[ExpertRange]]]:
        """
        Build per-layer, per-expert offset map.
        
        Returns:
            {layer_id: {expert_idx: [ExpertRange(gate), ExpertRange(up), ExpertRange(down)]}}
        """
        expert_map: Dict[int, Dict[int, List[ExpertRange]]] = {}
        
        for t in self.get_expert_tensors():
            layer = t.layer_id
            if layer < 0:
                continue
            if layer not in expert_map:
                expert_map[layer] = {}
            
            for ei in range(t.n_experts):
                if ei not in expert_map[layer]:
                    expert_map[layer][ei] = []
                start = t.file_offset + ei * t.per_expert_size
                expert_map[layer][ei].append(ExpertRange(
                    layer=layer,
                    expert_idx=ei,
                    projection=t.projection_type,
                    start_offset=start,
                    end_offset=start + t.per_expert_size,
                    size_bytes=t.per_expert_size,
                    tensor_name=t.name,
                ))
        
        return expert_map
    
    def detect_architecture(self) -> Dict[str, Any]:
        """
        Auto-detect model architecture specs, MoE properties, and recommended chat template.
        
        Returns:
            Dict containing arch_name, is_moe, total_experts, active_experts,
            num_layers, context_length, chat_template_format, and quantization_summary.
        """
        arch_name = str(self.metadata.get('general.architecture', 'unknown')).lower()
        
        # Expert counts
        total_experts = 1
        for k in ['expert_count', f'{arch_name}.expert_count', 'n_expert']:
            if k in self.metadata:
                try:
                    total_experts = int(self.metadata[k])
                    break
                except (ValueError, TypeError):
                    pass

        active_experts = 1
        for k in ['expert_used_count', f'{arch_name}.expert_used_count', 'n_expert_used']:
            if k in self.metadata:
                try:
                    active_experts = int(self.metadata[k])
                    break
                except (ValueError, TypeError):
                    pass

        # Layer count
        num_layers = 0
        for k in [f'{arch_name}.block_count', 'block_count']:
            if k in self.metadata:
                try:
                    num_layers = int(self.metadata[k])
                    break
                except (ValueError, TypeError):
                    pass

        # Fallback layer count from tensor names
        if num_layers == 0:
            max_layer = -1
            for t in self.tensors:
                if t.layer_id > max_layer:
                    max_layer = t.layer_id
            num_layers = max_layer + 1 if max_layer >= 0 else 0

        # Context length
        context_length = 2048
        for k in [f'{arch_name}.context_length', 'context_length']:
            if k in self.metadata:
                try:
                    context_length = int(self.metadata[k])
                    break
                except (ValueError, TypeError):
                    pass

        # Chat template format recommendation based on architecture
        if 'llama' in arch_name or 'llama-3' in arch_name:
            template = 'llama-3'
        elif 'qwen' in arch_name or 'chatml' in arch_name or 'deepseek' in arch_name:
            template = 'chatml'
        elif 'glm' in arch_name:
            template = 'glm'
        else:
            template = 'generic'

        # Quantization types summary
        type_counts: Dict[str, int] = {}
        for t in self.tensors:
            tname = t.type_name
            type_counts[tname] = type_counts.get(tname, 0) + 1

        is_moe = len(self.get_expert_tensors()) > 0 or total_experts > 1

        return {
            "arch_name": arch_name,
            "is_moe": is_moe,
            "total_experts": total_experts if is_moe else 1,
            "active_experts": active_experts if is_moe else 1,
            "num_layers": num_layers,
            "context_length": context_length,
            "recommended_chat_template": template,
            "tensor_types_summary": type_counts,
            "file_size_gb": round(self.file_size / (1024 ** 3), 2),
            "total_tensors": self.n_tensors,
        }

    def __repr__(self) -> str:
        return (
            f"GGUFParser({self.path.name}, "
            f"{len(self.tensors)} tensors, "
            f"~{self.file_size / 1024**3:.2f} GB)"
        )
    
    # ── Internal ────────────────────────────────────────────────────
    
    def _extract_metadata(self):
        """Read important metadata fields from GGUF reader."""
        # Get architecture first (need it for prefixed keys)
        arch_field = self._reader.get_field('general.architecture')
        arch = ''
        if arch_field is not None:
            # For string values: parts[field.data[0]] gives the memmap
            arch_val = self._get_field_value(arch_field)
            if arch_val is not None:
                arch = str(arch_val.tolist()) if hasattr(arch_val, 'tolist') else str(arch_val)
                self.metadata['general.architecture'] = arch
        
        prefixes = [f'{arch}.'] if arch else []
        
        # Keys to extract
        keys_to_try = [
            'general.architecture', 'general.name', 'general.alignment',
            'general.file_type', 'expert_count', 'n_expert', 'n_expert_used',
        ]
        for prefix in prefixes:
            keys_to_try.extend([f'{prefix}{k}' for k in [
                'block_count', 'expert_count', 'expert_used_count',
                'embedding_length', 'feed_forward_length', 'context_length',
            ]])
        
        for key in keys_to_try:
            field = self._reader.get_field(key)
            if field is not None:
                val = self._get_field_value(field)
                if val is not None:
                    self.metadata[key] = val
    
    def _get_field_value(self, field) -> Any:
        """Extract the actual value from a GGUF ReaderField."""
        if not hasattr(field, 'data') or not hasattr(field, 'parts'):
            return None
        if len(field.data) == 0:
            return None
        
        idx = field.data[0]
        if idx < len(field.parts):
            raw = field.parts[idx]
            
            # String: stored as uint8 bytes — decode if applicable
            if hasattr(raw, 'dtype') and raw.dtype == np.uint8 and raw.ndim == 1:
                try:
                    return bytes(raw.tolist()).decode('utf-8')
                except (UnicodeDecodeError, ValueError):
                    pass
            
            # Integer/Float scalars: convert numpy → Python native
            if hasattr(raw, 'tolist'):
                result = raw.tolist()
                # If result is a single-element list, extract the value
                if isinstance(result, list) and len(result) == 1:
                    return result[0]
                return result
            
            return raw
        return None
    
    def _parse_tensors(self):
        """Parse all tensor infos from GGUF reader."""
        # Determine alignment for size calculations
        alignment = self.metadata.get('general.alignment', 32)
        
        for raw_tensor in self._reader.tensors:
            name = raw_tensor.name
            
            # Shape from gguf library (convert numpy types to int)
            shape = tuple(int(d) for d in raw_tensor.shape)
            if not shape:
                continue
            
            # Tensor type
            ggml_type = int(raw_tensor.tensor_type)
            
            # File offset: gguf library gives us absolute offset
            file_offset = int(raw_tensor.field.offset) if hasattr(raw_tensor.field, 'offset') else 0
            
            # Calculate size in bytes
            size = self._calc_tensor_size(shape, ggml_type, alignment)
            
            ti = TensorInfo(
                name=name,
                shape=shape,
                ggml_type=ggml_type,
                file_offset=file_offset,
                size_bytes=size,
            )
            self.tensors.append(ti)
            self._tensors_by_name[name] = ti
    
    def _calc_tensor_size(self, shape: Tuple[int, ...], ggml_type: int, alignment: int) -> int:
        """Calculate tensor data size from shape and type."""
        n_elems = 1
        for d in shape:
            n_elems *= d
        
        # GGML type traits: (type_size, block_size)
        traits = {
            0:  (4, 1),      # F32
            1:  (2, 1),      # F16
            10: (70, 256),   # Q2_K
            11: (112, 256),  # Q3_K
            12: (144, 256),  # Q4_K
            13: (176, 256),  # Q5_K
            14: (208, 256),  # Q6_K
            15: (392, 512),  # Q8_K
            20: (130, 256),  # IQ4_NL
        }
        
        trait = traits.get(ggml_type)
        if trait:
            type_size, block_size = trait
            raw_size = (n_elems * type_size) // block_size
        else:
            # Fallback: assume 2 bytes per param
            raw_size = n_elems * 2
        
        # Align to GGUF alignment
        padded = (raw_size + alignment - 1) // alignment * alignment
        return padded


@dataclass
class SplitTensorInfo(TensorInfo):
    """TensorInfo extended with split-shard location."""
    shard_index: int = 0
    global_offset: int = 0      # absolute offset across the concatenated shards
    offset_in_shard: int = 0    # absolute offset within its own shard file


class GGUFSplitParser:
    """
    GGUF parser for models split across multiple shard files (e.g.
    unsloth DS V4 Flash 4-shard UD-IQ3_XXS).

    Builds a unified tensor index across all shards with GLOBAL offsets
    (as if the shards were concatenated in order), so prefetch engines can
    address tensors by one absolute offset space.

    Offset math (verified against real 4-shard model, 2026-08-11):
        global_offset(t) = sum(file_size of shards before s)
                         + data_offset(shard s)
                         + sum(padded32(n_bytes) of tensors before t in shard s)

    Usage:
        parser = GGUFSplitParser([shard1, shard2, shard3, shard4])
        loc = parser.tensor_location("blk.0.ffn_gate_exps.weight")
        # -> (shard_index=1, offset_in_shard=..., global_offset=..., size_bytes=...)
        em = parser.get_expert_map_global()
    """

    ALIGNMENT = 32  # GGUF default data alignment (general.alignment)

    def __init__(self, model_paths: List[str]):
        if not model_paths:
            raise ValueError("model_paths must contain at least one shard")
        # Sort shards naturally: 00001-of-00004 < 00002-of-00004 ...
        self.shard_paths = sorted(model_paths)
        self.shard_count = len(self.shard_paths)

        self._shard_readers: List[GGUFReader] = []
        self._shard_sizes: List[int] = []
        self._shard_data_offsets: List[int] = []
        self._shard_base: List[int] = []      # global base of each shard
        self.tensors: List[SplitTensorInfo] = []
        self._tensors_by_name: Dict[str, SplitTensorInfo] = {}
        self.metadata: Dict[str, Any] = {}

        self._load()
        self.n_tensors = len(self.tensors)

    # ── loading ──────────────────────────────────────────────────────

    def _load(self):
        global_base = 0
        for s, path in enumerate(self.shard_paths):
            size = Path(path).stat().st_size
            reader = GGUFReader(str(path))
            self._shard_readers.append(reader)
            self._shard_sizes.append(size)
            self._shard_data_offsets.append(reader.data_offset)
            self._shard_base.append(global_base)

            # metadata: take from the shard that has real KV fields
            if not self.metadata and len(reader.fields) > 5:
                self._extract_metadata(reader)

            # tensors
            cum = reader.data_offset
            for raw in reader.tensors:
                shape = tuple(int(d) for d in raw.shape)
                if not shape:
                    continue
                ggml_type = int(raw.tensor_type)
                size_bytes = self._padded(int(raw.n_bytes))
                ti = SplitTensorInfo(
                    name=raw.name,
                    shape=shape,
                    ggml_type=ggml_type,
                    file_offset=cum,                 # offset within shard
                    size_bytes=size_bytes,
                    shard_index=s,
                    global_offset=global_base + cum,
                    offset_in_shard=cum,
                )
                self.tensors.append(ti)
                self._tensors_by_name[raw.name] = ti
                cum += size_bytes
            global_base += size

    @staticmethod
    def _padded(n: int) -> int:
        return (n + GGUFSplitParser.ALIGNMENT - 1) // GGUFSplitParser.ALIGNMENT * GGUFSplitParser.ALIGNMENT

    def _extract_metadata(self, reader: GGUFReader):
        """Copy the important KV fields from the primary shard."""
        for key, field in reader.fields.items():
            if key.startswith("GGUF."):
                continue
            try:
                if not field.data:
                    continue
                idx = field.data[0]
                if idx >= len(field.parts):
                    continue
                raw = field.parts[idx]
                if hasattr(raw, "tolist"):
                    val = raw.tolist()
                    if isinstance(val, list) and len(val) == 1:
                        val = val[0]
                    # bytes -> utf-8 string (GGUF strings are stored as uint8 arrays)
                    if isinstance(val, list):
                        try:
                            s = bytes(val).decode("utf-8", "replace")
                            if s.isprintable():
                                val = s
                        except Exception:
                            pass
                    # numpy scalar -> python native
                    if hasattr(val, "item"):
                        val = val.item()
                else:
                    val = raw
                self.metadata[key] = val
            except Exception:
                continue

    # ── public API ───────────────────────────────────────────────────

    def close(self):
        self._shard_readers.clear()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def get_tensor(self, name: str) -> Optional[SplitTensorInfo]:
        return self._tensors_by_name.get(name)

    def tensor_location(self, name: str) -> Optional[SplitTensorInfo]:
        """Location of a tensor across the split: (shard, global offset, size)."""
        return self._tensors_by_name.get(name)

    def get_tensors_by_pattern(self, pattern: str) -> List[SplitTensorInfo]:
        import fnmatch
        return [t for t in self.tensors if fnmatch.fnmatch(t.name, pattern)]

    def get_expert_tensors(self) -> List[SplitTensorInfo]:
        return [t for t in self.tensors
                if ("exps" in t.name.lower() or "expert" in t.name.lower()
                    or "moe" in t.name.lower()) and len(t.shape) >= 3]

    def get_expert_map_global(self) -> Dict[int, Dict[int, List[ExpertRange]]]:
        """Per-layer, per-expert offset map with GLOBAL offsets (split-aware)."""
        expert_map: Dict[int, Dict[int, List[ExpertRange]]] = {}
        for t in self.get_expert_tensors():
            layer = t.layer_id
            if layer < 0:
                continue
            if layer not in expert_map:
                expert_map[layer] = {}
            n_experts = t.shape[-1] if len(t.shape) >= 3 else 1
            per = t.size_bytes // n_experts
            for ei in range(n_experts):
                if ei not in expert_map[layer]:
                    expert_map[layer][ei] = []
                start = t.global_offset + ei * per
                expert_map[layer][ei].append(ExpertRange(
                    layer=layer,
                    expert_idx=ei,
                    projection=t.projection_type,
                    start_offset=start,
                    end_offset=start + per,
                    size_bytes=per,
                    tensor_name=t.name,
                ))
        return expert_map

    def detect_architecture(self) -> Dict[str, Any]:
        arch = str(self.metadata.get("general.architecture", "unknown")).lower()
        n_layers = 0
        for k in (f"{arch}.block_count", "deepseek4.block_count", "block_count"):
            if k in self.metadata:
                try:
                    n_layers = int(self.metadata[k])
                    break
                except (ValueError, TypeError):
                    pass
        total_experts = 1
        for k in (f"{arch}.expert_count", "deepseek4.expert_count", "expert_count"):
            if k in self.metadata:
                try:
                    total_experts = int(self.metadata[k])
                    break
                except (ValueError, TypeError):
                    pass
        active = 1
        for k in (f"{arch}.expert_used_count", "deepseek4.expert_used_count",
                  "expert_used_count"):
            if k in self.metadata:
                try:
                    active = int(self.metadata[k])
                    break
                except (ValueError, TypeError):
                    pass
        return {
            "arch_name": arch,
            "is_moe": len(self.get_expert_tensors()) > 0 or total_experts > 1,
            "total_experts": total_experts,
            "active_experts": active,
            "num_layers": n_layers,
            "file_size_gb": round(sum(self._shard_sizes) / (1024 ** 3), 2),
            "total_tensors": self.n_tensors,
            "shard_count": self.shard_count,
            "shard_sizes_gb": [round(s / (1024 ** 3), 2) for s in self._shard_sizes],
        }

    def __repr__(self) -> str:
        return (
            f"GGUFSplitParser({len(self.shard_paths)} shards, "
            f"{len(self.tensors)} tensors, "
            f"~{sum(self._shard_sizes) / 1024**3:.2f} GB)"
        )
