#ifndef WEIGHT_STREAM_CORE_H
#define WEIGHT_STREAM_CORE_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef _WIN32
  #ifdef WEIGHT_STREAM_EXPORTS
    #define WS_API __declspec(dllexport)
  #else
    #define WS_API __declspec(dllimport)
  #endif
#else
  #define WS_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

// Opaque handles
typedef struct WSBufferWS WSBufferHandle;
typedef struct WSPrefetchEngineWS WSPrefetchEngineHandle;

// Metadata for a weight shard
typedef struct {
    uint32_t shard_id;
    uint64_t file_offset;
    uint32_t shard_size;
    uint16_t layer_id;
    uint16_t expert_id;
    uint8_t  shard_type; // 0=attention, 1=shared_mlp, 2=routed_expert, 3=embedding
    uint8_t  popularity_score;
} WSShardMeta;

// Buffer Stats
typedef struct {
    uint64_t total_requests;
    uint64_t cache_hits;
    uint64_t cache_misses;
    double   hit_rate;
    size_t   current_memory_bytes;
    size_t   capacity_bytes;
} WSBufferStats;

// --- Buffer Functions ---
WS_API WSBufferHandle* ws_buffer_create(size_t capacity_bytes, int eviction_policy);
WS_API void ws_buffer_destroy(WSBufferHandle* handle);
WS_API bool ws_buffer_get(WSBufferHandle* handle, uint32_t shard_id, void** out_data_ptr, size_t* out_size);
WS_API bool ws_buffer_put(WSBufferHandle* handle, uint32_t shard_id, const void* data, size_t size, uint8_t priority);
WS_API void ws_buffer_touch(WSBufferHandle* handle, uint32_t shard_id);
WS_API void ws_buffer_get_stats(WSBufferHandle* handle, WSBufferStats* out_stats);

// --- Native Memory & Page Tracking (Windows / POSIX) ---
typedef struct {
    uint64_t working_set_bytes;
    uint64_t pagefile_usage_bytes;
    uint64_t total_physical_ram;
    double   resident_ratio;
} WSMemoryStats;

WS_API bool ws_get_memory_stats(WSMemoryStats* out_stats);
WS_API bool ws_is_address_resident(void* addr, size_t size, double* out_resident_ratio);

// --- OOM Protection & Adaptive Eviction ---
typedef struct {
    double   memory_pressure;     // 0.0 = idle, 1.0 = critical OOM
    uint64_t available_bytes;
    uint64_t total_bytes;
    bool     should_evict;        // true when pressure > threshold
} WSMemoryPressure;

WS_API bool ws_check_memory_pressure(WSMemoryPressure* out_pressure, double threshold);
WS_API int  ws_buffer_adaptive_evict(WSBufferHandle* handle, double pressure, int max_evictions);

// --- SIMD Kernel Capabilities ---
typedef struct {
    bool has_avx2;
    bool has_avx512;
    bool has_neon;
    const char* best_backend;     // "avx512", "avx2", "neon", or "scalar"
} WSSIMDCapabilities;

WS_API void ws_detect_simd(WSSIMDCapabilities* out_caps);

#ifdef __cplusplus
}
#endif

#endif // WEIGHT_STREAM_CORE_H
