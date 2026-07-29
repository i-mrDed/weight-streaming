"""Python ctypes interface binding for weight-stream-core C/C++ library."""

import ctypes
import os
import sys
from typing import Optional, Tuple, Dict, Any

class WSShardMeta(ctypes.Structure):
    _fields_ = [
        ("shard_id", ctypes.c_uint32),
        ("file_offset", ctypes.c_uint64),
        ("shard_size", ctypes.c_uint32),
        ("layer_id", ctypes.c_uint16),
        ("expert_id", ctypes.c_uint16),
        ("shard_type", ctypes.c_uint8),
        ("popularity_score", ctypes.c_uint8),
    ]

class WSBufferStats(ctypes.Structure):
    _fields_ = [
        ("total_requests", ctypes.c_uint64),
        ("cache_hits", ctypes.c_uint64),
        ("cache_misses", ctypes.c_uint64),
        ("hit_rate", ctypes.c_double),
        ("current_memory_bytes", ctypes.c_size_t),
        ("capacity_bytes", ctypes.c_size_t),
    ]

class WSMemoryStats(ctypes.Structure):
    _fields_ = [
        ("working_set_bytes", ctypes.c_uint64),
        ("pagefile_usage_bytes", ctypes.c_uint64),
        ("total_physical_ram", ctypes.c_uint64),
        ("resident_ratio", ctypes.c_double),
    ]

class NativeCore:
    _lib = None

    @classmethod
    def load_library(cls, lib_path: Optional[str] = None) -> bool:
        if cls._lib is not None:
            return True

        if lib_path is None:
            dir_path = os.path.dirname(os.path.abspath(__file__))
            if sys.platform == "win32":
                dll_name = "weight_stream_core.dll"
            elif sys.platform == "darwin":
                dll_name = "libweight_stream_core.dylib"
            else:
                dll_name = "libweight_stream_core.so"
            lib_path = os.path.join(dir_path, dll_name)

        if not os.path.exists(lib_path):
            return False

        try:
            cls._lib = ctypes.CDLL(lib_path)
            cls._setup_prototypes()
            return True
        except Exception:
            return False

    @classmethod
    def _setup_prototypes(cls):
        lib = cls._lib
        if lib is None:
            return

        # ws_buffer_create
        lib.ws_buffer_create.argtypes = [ctypes.c_size_t, ctypes.c_int]
        lib.ws_buffer_create.restype = ctypes.c_void_p

        # ws_buffer_destroy
        lib.ws_buffer_destroy.argtypes = [ctypes.c_void_p]
        lib.ws_buffer_destroy.restype = None

        # ws_buffer_get
        lib.ws_buffer_get.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_size_t)]
        lib.ws_buffer_get.restype = ctypes.c_bool

        # ws_buffer_put
        lib.ws_buffer_put.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint8]
        lib.ws_buffer_put.restype = ctypes.c_bool

        # ws_buffer_get_stats
        lib.ws_buffer_get_stats.argtypes = [ctypes.c_void_p, ctypes.POINTER(WSBufferStats)]
        lib.ws_buffer_get_stats.restype = None

        # ws_get_memory_stats
        lib.ws_get_memory_stats.argtypes = [ctypes.POINTER(WSMemoryStats)]
        lib.ws_get_memory_stats.restype = ctypes.c_bool

        # ws_is_address_resident
        lib.ws_is_address_resident.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_double)]
        lib.ws_is_address_resident.restype = ctypes.c_bool

    @classmethod
    def get_memory_stats(cls) -> Dict[str, Any]:
        if cls._lib is None and not cls.load_library():
            return {"working_set_mb": 0, "resident_ratio": 0.0, "native_available": False}
        stats = WSMemoryStats()
        if cls._lib.ws_get_memory_stats(ctypes.byref(stats)):
            return {
                "working_set_mb": stats.working_set_bytes / (1024 * 1024),
                "pagefile_usage_mb": stats.pagefile_usage_bytes / (1024 * 1024),
                "total_ram_gb": stats.total_physical_ram / (1024 * 1024 * 1024),
                "resident_ratio": stats.resident_ratio,
                "native_available": True
            }
        return {"working_set_mb": 0, "resident_ratio": 0.0, "native_available": False}
