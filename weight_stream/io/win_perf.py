"""
Windows performance monitoring for page cache analysis.

Uses Windows Performance Counters to measure:
- Page faults/sec during inference
- Working set size (RAM usage) of the model
- Cache hit/miss rates at the OS page level

This allows us to measure prefetcher effectiveness without
modifying llama.cpp's C++ code.
"""
import ctypes
import ctypes.wintypes
import logging
import time
from ctypes import POINTER, Structure, byref, sizeof
from typing import Optional

logger = logging.getLogger(__name__)

# ── Windows API constants ───────────────────────────────────────────

MEM_RESET = 0x00080000
PAGE_READWRITE = 0x04

# Process access rights
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

# ── PSAPI_WORKING_SET_EX_INFORMATION ────────────────────────────────

class PSAPI_WORKING_SET_EX_BLOCK(ctypes.Structure):
    _fields_ = [
        ("Flags", ctypes.c_uint64),
    ]

class PSAPI_WORKING_SET_EX_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("VirtualAddress", ctypes.c_void_p),
        ("VirtualAttributes", PSAPI_WORKING_SET_EX_BLOCK),
    ]

# ── SYSTEM_INFO ─────────────────────────────────────────────────────

class SYSTEM_INFO(ctypes.Structure):
    _fields_ = [
        ("wProcessorArchitecture", ctypes.c_uint16),
        ("wReserved", ctypes.c_uint16),
        ("dwPageSize", ctypes.c_uint32),
        ("lpMinimumApplicationAddress", ctypes.c_void_p),
        ("lpMaximumApplicationAddress", ctypes.c_void_p),
        ("dwActiveProcessorMask", ctypes.c_void_p),
        ("dwNumberOfProcessors", ctypes.c_uint32),
        ("dwProcessorType", ctypes.c_uint32),
        ("dwAllocationGranularity", ctypes.c_uint32),
        ("wProcessorLevel", ctypes.c_uint16),
        ("wProcessorRevision", ctypes.c_uint16),
    ]

# ── Performance counter ─────────────────────────────────────────────

class WindowsPageMonitor:
    """
    Monitors OS page cache behavior for memory-mapped model files.
    
    Uses QueryWorkingSetEx to check which pages of the mmap'd model
    are physically resident in RAM (hot) vs on disk (cold).
    
    This allows us to measure prefetcher effectiveness indirectly:
    - More resident pages = better prefetch hit rate
    - Fewer page faults = smoother inference
    
    Args:
        mmap_addr: starting virtual address of the mmap
        mmap_size: size of the mmap in bytes
        page_size: system page size (usually 4096)
    """
    
    def __init__(
        self,
        mmap_addr: int,
        mmap_size: int,
        page_size: int = 0,
    ):
        self.mmap_addr = mmap_addr
        self.mmap_size = mmap_size
        
        # Load Windows API functions
        self._kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self._psapi = ctypes.WinDLL('psapi', use_last_error=True)
        
        # Set up QueryWorkingSetEx prototype
        self._psapi.QueryWorkingSetEx.argtypes = [
            ctypes.wintypes.HANDLE,
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        self._psapi.QueryWorkingSetEx.restype = ctypes.wintypes.BOOL
        
        # Get current process handle
        self._hProcess = self._kernel32.GetCurrentProcess()
        
        self.page_size = page_size or self._get_page_size()
        self.n_pages = (mmap_size + self.page_size - 1) // self.page_size
        
        # Get current process handle
        self._hProcess = self._kernel32.GetCurrentProcess()
        
        # Cache: which page ranges are in RAM
        self._cache: Optional[bytearray] = None
        self._last_sample = 0.0
    
    def sample_resident_pages(self) -> bytearray:
        """
        Sample which pages of the mmap are in the working set.
        
        Returns bytearray where bit n = 1 if page n is resident in RAM.
        Uses QueryWorkingSetEx for precise per-page info.
        
        NOTE: Only samples first page of each 1MB chunk for speed.
        For a 5GB file: 5000 samples, each ~0.1ms = ~500ms total.
        """
        chunk_size = 1024 * 1024  # 1MB chunks
        n_chunks = (self.mmap_size + chunk_size - 1) // chunk_size
        
        # Build address array
        page_size = self.page_size
        n_entries = n_chunks
        buf_size = sizeof(PSAPI_WORKING_SET_EX_INFORMATION) * n_entries
        
        class WorkingSetArray(ctypes.Structure):
            _fields_ = [("entries", PSAPI_WORKING_SET_EX_INFORMATION * n_entries)]
        
        buf = WorkingSetArray()
        
        # Fill in addresses (first page-aligned address in each chunk)
        for i in range(n_entries):
            addr = self.mmap_addr + (i * chunk_size)
            # Align to page boundary
            addr = addr & ~(page_size - 1)
            buf.entries[i].VirtualAddress = ctypes.c_void_p(addr)
        
        # Query working set
        result = self._psapi.QueryWorkingSetEx(
            self._hProcess,
            byref(buf),
            ctypes.c_uint32(buf_size),
        )
        
        if not result:
            error = ctypes.GetLastError()
            logger.warning(f"QueryWorkingSetEx failed: {error}")
            return bytearray(n_entries)
        
        # Build result bitmap
        resident = bytearray(n_entries)
        for i in range(n_entries):
            block = buf.entries[i].VirtualAttributes
            # Bit 0 = Valid (in working set)
            resident[i] = 1 if (block.Flags & 1) else 0
        
        self._cache = resident
        self._last_sample = time.time()
        
        return resident
    
    def get_resident_ratio(self) -> float:
        """Return fraction of file currently in RAM (0.0 to 1.0)."""
        if self._cache is None:
            self.sample_resident_pages()
        if self._cache and len(self._cache) > 0:
            return sum(self._cache) / len(self._cache)
        return 0.0
    
    def get_resident_bytes(self) -> int:
        """Return bytes of the file currently in RAM."""
        if self._cache is None:
            return 0
        chunk_size = 1024 * 1024
        return sum(self._cache) * chunk_size
    
    def is_chunk_resident(self, chunk_idx: int) -> bool:
        """Check if a specific 1MB chunk is in RAM."""
        if self._cache is None or chunk_idx >= len(self._cache):
            return False
        return bool(self._cache[chunk_idx])
    
    def _get_page_size(self) -> int:
        """Get system page size."""
        sys_info = SYSTEM_INFO()
        self._kernel32.GetSystemInfo(byref(sys_info))
        return sys_info.dwPageSize
    
    def __repr__(self) -> str:
        ratio = self.get_resident_ratio()
        bytes_ram = self.get_resident_bytes()
        return (
            f"WindowsPageMonitor({bytes_ram / 1024**3:.1f}GB / "
            f"{self.mmap_size / 1024**3:.1f}GB = {ratio:.1%} in RAM)"
        )
