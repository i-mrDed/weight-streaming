"""Build real (small) GGUF files for parser/backend tests.

Uses the installed `gguf` library's GGUFWriter so the files are valid and
parseable by GGUFReader/GGUFParser — no mocking needed.
"""
import numpy as np
from gguf import GGUFWriter


def make_gguf(path: str, n_tensors: int, arch: str = "qwen35") -> str:
    w = GGUFWriter(path, arch)
    # a couple of light metadata keys so _extract_metadata has something
    w.add_name("fake-model")
    w.add_quantization_version(2)
    for i in range(n_tensors):
        arr = np.arange(8, dtype=np.float32)
        w.add_tensor(f"blk.0.t{i}", arr)
    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_tensors_to_file()
    w.close()
    return path