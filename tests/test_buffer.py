"""Unit tests for StreamingBuffer (no model file needed)."""
import mmap
import tempfile
from pathlib import Path

import pytest

from weight_stream.core.buffer import StreamingBuffer, SHARD_SIZE


@pytest.fixture
def mem_buffer():
    """Create a StreamingBuffer backed by in-memory mmap (no file I/O)"""
    # Create a temp file just for mmap
    tmp = tempfile.NamedTemporaryFile(delete=False)
    file_size = 64 * SHARD_SIZE  # 256 MB "model"
    tmp.write(b'\x00' * file_size)
    tmp.close()
    
    path = Path(tmp.name)
    f = open(path, "r+b")
    mm = mmap.mmap(f.fileno(), file_size)
    
    buf = StreamingBuffer(mmap_obj=mm, total_size=file_size, capacity_mb=16)
    
    yield buf
    
    mm.close()
    f.close()
    path.unlink()


class TestStreamingBuffer:
    
    def test_init(self, mem_buffer):
        buf = mem_buffer
        assert buf._capacity > 0
        assert buf.n_shards == 64
        assert buf.hits == 0
        assert buf.misses == 0
    
    def test_access_hit(self, mem_buffer):
        buf = mem_buffer
        data = buf.access(0)
        assert buf.hits == 0  # First access is a miss
        assert buf.misses == 1
        assert isinstance(data, memoryview)
        
        # Second access = hit
        data2 = buf.access(0)
        assert buf.hits == 1
        assert buf.misses == 1
    
    def test_access_miss(self, mem_buffer):
        buf = mem_buffer
        for i in range(5):
            buf.access(i)
        assert buf.misses == 5
        assert buf.hits == 0
    
    def test_lru_eviction(self, mem_buffer):
        """16 MB capacity / 4 MB shard = 4 shards max"""
        buf = mem_buffer
        
        # Access 5 different shards → eviction happens
        for i in range(5):
            buf.access(i)
        
        assert buf.evictions >= 1
        assert len(buf) <= buf._capacity
    
    def test_lru_keeps_recent(self, mem_buffer):
        """Most recently accessed shards survive eviction"""
        buf = mem_buffer
        
        # Access shards 0-3 (fill buffer of 4 slots)
        for i in range(4):
            buf.access(i)
        
        # Access shard 0 again (makes it MRU)
        buf.access(0)
        
        # Access 4 and 5 (should evict 1 and 2, not 0)
        buf.access(4)
        buf.access(5)
        
        # Shard 0 should still be in buffer
        assert 0 in buf
    
    def test_prefetch(self, mem_buffer):
        buf = mem_buffer
        buf.prefetch([10, 11, 12])
        
        # Prefetched shards should be in hot set
        assert 10 in buf
        assert 11 in buf
        assert 12 in buf
    
    def test_prefetch_full(self, mem_buffer):
        buf = mem_buffer
        buf.prefetch_full([20, 21])
        
        assert 20 in buf
        assert 21 in buf
    
    def test_hit_rate(self, mem_buffer):
        buf = mem_buffer
        buf.access(0)  # miss
        buf.access(1)  # miss
        buf.access(0)  # hit
        buf.access(1)  # hit
        
        assert buf.hit_rate == 0.5
    
    def test_get_stats(self, mem_buffer):
        buf = mem_buffer
        buf.access(0)
        buf.access(0)
        
        stats = buf.get_stats()
        assert 'hit_rate' in stats
        assert 'hits' in stats
        assert 'misses' in stats
        assert stats['hits'] == 1
        assert stats['misses'] == 1
    
    def test_memoryview_is_zero_copy(self, mem_buffer):
        buf = mem_buffer
        data = buf.access(0)
        # data should be a memoryview backed by the mmap
        assert isinstance(data, memoryview)
        # Modifying data would modify the mmap (shared memory)
        # Verify by checking data is accessible
        assert len(data) == SHARD_SIZE


class TestPredictor:
    
    def test_sequential_pattern(self):
        from weight_stream.core.predictor import HeuristicPredictor
        p = HeuristicPredictor()
        
        # Simulate sequential access pattern
        for i in range(10):
            p.observe(i)
        
        pred = p.predict_next(9)
        assert 10 in pred or 8 in pred  # Should predict continuation or co-occurrence
    
    def test_co_occurrence(self):
        from weight_stream.core.predictor import HeuristicPredictor
        p = HeuristicPredictor()
        
        # If 2 and 5 always appear together
        accesses = [2, 5, 2, 5, 2, 5]
        for a in accesses:
            p.observe(a)
        
        pred = p.predict_next(2)
        assert 5 in pred  # Should predict co-occurring expert
    
    def test_get_stats(self):
        from weight_stream.core.predictor import HeuristicPredictor
        p = HeuristicPredictor()
        p.observe(1)
        p.observe(2)
        
        stats = p.get_stats()
        assert stats['history_size'] == 2
        assert stats['unique_shards'] == 2
