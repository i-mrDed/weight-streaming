"""Shard Repacker Tool for Weight-Streaming.

Re-orders model weight shards on NVMe storage by popularity rank.
Places Hot Experts in a contiguous zone at the front of the file, transforming random seeks into high-bandwidth sequential reads.
"""

import os
import struct
import time
from typing import List, Dict, Any, Optional

MAGIC_HEADER = b"SWSv1"

class ShardRepacker:
    def __init__(self, input_path: str, output_path: str, shard_size_mb: float = 4.0):
        self.input_path = input_path
        self.output_path = output_path
        self.shard_size = int(shard_size_mb * 1024 * 1024)

    def repack(self, popularity_map: Optional[Dict[int, int]] = None) -> Dict[str, Any]:
        """Repacks input model into contiguous popularity-ordered shard format."""
        if not os.path.exists(self.input_path):
            raise FileNotFoundError(f"Input file not found: {self.input_path}")

        file_size = os.path.getsize(self.input_path)
        total_shards = (file_size + self.shard_size - 1) // self.shard_size

        start_time = time.time()
        print(f"Repacking {self.input_path} ({file_size / (1024**3):.2f} GB) into {total_shards} shards...")

        # Build default popularity mapping if none provided (hot zone = lower shard IDs)
        if popularity_map is None:
            popularity_map = {i: total_shards - i for i in range(total_shards)}

        # Sort shard IDs by popularity descending
        ordered_shard_ids = sorted(range(total_shards), key=lambda x: popularity_map.get(x, 0), reverse=True)

        # Write output file
        with open(self.input_path, "rb") as fin, open(self.output_path, "wb") as fout:
            # 1. Header (64 bytes)
            fout.write(MAGIC_HEADER)
            fout.write(struct.pack("<I", total_shards))
            fout.write(struct.pack("<I", self.shard_size))
            fout.write(b"\x00" * 47)  # padding

            # 2. Write shards in popularity order
            bytes_written = 0
            for rank, shard_id in enumerate(ordered_shard_ids):
                fin.seek(shard_id * self.shard_size)
                chunk = fin.read(self.shard_size)
                fout.write(chunk)
                bytes_written += len(chunk)

                if (rank + 1) % 100 == 0 or rank == total_shards - 1:
                    print(f"Progress: {rank + 1}/{total_shards} shards ({bytes_written / (1024**2):.1f} MB)...")

        duration = time.time() - start_time
        return {
            "input_file": self.input_path,
            "output_file": self.output_path,
            "total_shards": total_shards,
            "shard_size_mb": self.shard_size / (1024 * 1024),
            "bytes_written": bytes_written,
            "duration_sec": round(duration, 2),
            "repack_speed_mbps": round((bytes_written / (1024 * 1024)) / duration, 2)
        }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Repack GGUF model shards for Weight Streaming")
    parser.add_argument("input", help="Path to input model file")
    parser.add_argument("output", help="Path to output repacked model file")
    parser.add_argument("--shard-size-mb", type=float, default=4.0, help="Shard size in MB (default 4.0)")
    args = parser.parse_args()

    repacker = ShardRepacker(args.input, args.output, args.shard_size_mb)
    stats = repacker.repack()
    print("Repack completed:", stats)
