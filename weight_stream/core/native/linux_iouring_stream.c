/**
 * Linux io_uring async I/O backend for Weight-Streaming.
 *
 * Uses io_uring for zero-copy, kernel-bypassing asynchronous reads
 * of weight shards from NVMe storage. Falls back to pread() if
 * io_uring is unavailable (kernel < 5.1).
 *
 * Compile: gcc -O2 -shared -fPIC -o libws_iouring.so linux_iouring_stream.c -luring
 */

#include "weight_stream_core.h"
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#ifdef __linux__
#include <unistd.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <errno.h>

/* Attempt to use io_uring if header is available */
#if __has_include(<liburing.h>)
#define HAS_IO_URING 1
#include <liburing.h>
#else
#define HAS_IO_URING 0
#endif

/* ── mincore-based residency check ──────────────────────────────── */

bool ws_linux_is_resident(void* addr, size_t length, double* out_ratio) {
    if (!addr || length == 0) {
        if (out_ratio) *out_ratio = 0.0;
        return false;
    }

    long page_size = sysconf(_SC_PAGESIZE);
    if (page_size <= 0) page_size = 4096;

    /* Align addr down to page boundary */
    uintptr_t start = (uintptr_t)addr & ~((uintptr_t)page_size - 1);
    size_t aligned_len = ((uintptr_t)addr + length - start + page_size - 1) / page_size;

    unsigned char* vec = (unsigned char*)calloc(aligned_len, 1);
    if (!vec) {
        if (out_ratio) *out_ratio = 0.0;
        return false;
    }

    int ret = mincore((void*)start, aligned_len * page_size, vec);
    if (ret != 0) {
        free(vec);
        if (out_ratio) *out_ratio = 0.0;
        return false;
    }

    size_t resident = 0;
    for (size_t i = 0; i < aligned_len; i++) {
        if (vec[i] & 1) resident++;
    }
    free(vec);

    double ratio = (double)resident / (double)aligned_len;
    if (out_ratio) *out_ratio = ratio;
    return ratio > 0.5;
}

/* ── Memory pressure detection via /proc/meminfo ─────────────── */

typedef struct {
    uint64_t mem_total_kb;
    uint64_t mem_available_kb;
    double   pressure_ratio;  /* 0.0 = no pressure, 1.0 = critical */
} WSLinuxMemPressure;

bool ws_linux_check_memory_pressure(WSLinuxMemPressure* out) {
    if (!out) return false;

    FILE* f = fopen("/proc/meminfo", "r");
    if (!f) return false;

    char line[256];
    out->mem_total_kb = 0;
    out->mem_available_kb = 0;

    while (fgets(line, sizeof(line), f)) {
        if (strncmp(line, "MemTotal:", 9) == 0) {
            sscanf(line + 9, " %lu", (unsigned long*)&out->mem_total_kb);
        } else if (strncmp(line, "MemAvailable:", 13) == 0) {
            sscanf(line + 13, " %lu", (unsigned long*)&out->mem_available_kb);
        }
    }
    fclose(f);

    if (out->mem_total_kb > 0) {
        double used_ratio = 1.0 - ((double)out->mem_available_kb / (double)out->mem_total_kb);
        out->pressure_ratio = used_ratio;
    } else {
        out->pressure_ratio = 0.0;
    }
    return true;
}

/* ── io_uring async shard reader ─────────────────────────────── */

typedef struct {
    int fd;
#if HAS_IO_URING
    struct io_uring ring;
    bool ring_initialized;
#endif
    bool use_iouring;
} WSIOUringReader;

WSIOUringReader* ws_iouring_open(const char* file_path, int queue_depth) {
    WSIOUringReader* reader = (WSIOUringReader*)calloc(1, sizeof(WSIOUringReader));
    if (!reader) return NULL;

    reader->fd = open(file_path, O_RDONLY | O_DIRECT);
    if (reader->fd < 0) {
        /* Fallback: open without O_DIRECT */
        reader->fd = open(file_path, O_RDONLY);
        if (reader->fd < 0) {
            free(reader);
            return NULL;
        }
    }

    reader->use_iouring = false;

#if HAS_IO_URING
    if (queue_depth <= 0) queue_depth = 64;
    int ret = io_uring_queue_init(queue_depth, &reader->ring, 0);
    if (ret == 0) {
        reader->ring_initialized = true;
        reader->use_iouring = true;
    }
#endif

    return reader;
}

/* Synchronous pread fallback */
static ssize_t ws_pread_shard(int fd, void* buf, size_t count, off_t offset) {
    ssize_t total = 0;
    while ((size_t)total < count) {
        ssize_t n = pread(fd, (char*)buf + total, count - total, offset + total);
        if (n <= 0) break;
        total += n;
    }
    return total;
}

ssize_t ws_iouring_read(WSIOUringReader* reader, void* buf, size_t count, uint64_t offset) {
    if (!reader || reader->fd < 0) return -1;

#if HAS_IO_URING
    if (reader->use_iouring) {
        struct io_uring_sqe* sqe = io_uring_get_sqe(&reader->ring);
        if (!sqe) {
            /* Queue full — fallback to pread */
            return ws_pread_shard(reader->fd, buf, count, (off_t)offset);
        }

        io_uring_prep_read(sqe, reader->fd, buf, count, offset);
        io_uring_sqe_set_data(sqe, buf);
        io_uring_submit(&reader->ring);

        struct io_uring_cqe* cqe;
        int ret = io_uring_wait_cqe(&reader->ring, &cqe);
        if (ret < 0) {
            return ws_pread_shard(reader->fd, buf, count, (off_t)offset);
        }

        ssize_t result = cqe->res;
        io_uring_cqe_seen(&reader->ring, cqe);
        return result;
    }
#endif

    return ws_pread_shard(reader->fd, buf, count, (off_t)offset);
}

void ws_iouring_close(WSIOUringReader* reader) {
    if (!reader) return;

#if HAS_IO_URING
    if (reader->ring_initialized) {
        io_uring_queue_exit(&reader->ring);
    }
#endif

    if (reader->fd >= 0) close(reader->fd);
    free(reader);
}

#endif /* __linux__ */
