"""I/O abstraction for platform-native async prefetch.

Windows: PrefetchVirtualMemory, IOCP, overlapped I/O
Linux: io_uring, madvise(MADV_WILLNEED)
"""
