#include "weight_stream_core.h"
#include <unordered_map>
#include <list>
#include <vector>
#include <mutex>
#include <cstdlib>
#include <cstring>
#include <chrono>

// Internal Buffer Implementation
struct BufferSlot {
    uint32_t shard_id;
    void* data;
    size_t size;
    uint8_t priority;
    uint64_t access_count;
    std::chrono::steady_clock::time_point last_access;
};

struct WSBufferWS {
    size_t capacity_bytes;
    size_t current_bytes;
    int eviction_policy; // 0 = LRU, 1 = LFU, 2 = Priority-LRU
    std::mutex mtx;

    std::unordered_map<uint32_t, BufferSlot> slots;
    std::list<uint32_t> lru_order; // front = MRU, back = LRU
    std::unordered_map<uint32_t, std::list<uint32_t>::iterator> lru_iter_map;

    uint64_t total_requests;
    uint64_t cache_hits;
    uint64_t cache_misses;

    WSBufferWS(size_t capacity, int policy)
        : capacity_bytes(capacity), current_bytes(0), eviction_policy(policy),
          total_requests(0), cache_hits(0), cache_misses(0) {}

    ~WSBufferWS() {
        std::lock_guard<std::mutex> lock(mtx);
        for (auto& pair : slots) {
            if (pair.second.data) {
                free(pair.second.data);
            }
        }
        slots.clear();
        lru_order.clear();
        lru_iter_map.clear();
    }
};

extern "C" {

WSBufferHandle* ws_buffer_create(size_t capacity_bytes, int eviction_policy) {
    return new WSBufferWS(capacity_bytes, eviction_policy);
}

void ws_buffer_destroy(WSBufferHandle* handle) {
    if (handle) {
        delete handle;
    }
}

bool ws_buffer_get(WSBufferHandle* handle, uint32_t shard_id, void** out_data_ptr, size_t* out_size) {
    if (!handle) return false;
    std::lock_guard<std::mutex> lock(handle->mtx);
    handle->total_requests++;

    auto it = handle->slots.find(shard_id);
    if (it != handle->slots.end()) {
        handle->cache_hits++;
        it->second.access_count++;
        it->second.last_access = std::chrono::steady_clock::now();

        // Update LRU list
        auto iter_it = handle->lru_iter_map.find(shard_id);
        if (iter_it != handle->lru_iter_map.end()) {
            handle->lru_order.erase(iter_it->second);
        }
        handle->lru_order.push_front(shard_id);
        handle->lru_iter_map[shard_id] = handle->lru_order.begin();

        if (out_data_ptr) *out_data_ptr = it->second.data;
        if (out_size) *out_size = it->second.size;
        return true;
    }

    handle->cache_misses++;
    if (out_data_ptr) *out_data_ptr = nullptr;
    if (out_size) *out_size = 0;
    return false;
}

bool ws_buffer_put(WSBufferHandle* handle, uint32_t shard_id, const void* data, size_t size, uint8_t priority) {
    if (!handle || !data || size == 0) return false;
    std::lock_guard<std::mutex> lock(handle->mtx);

    // If already exists, update
    auto it = handle->slots.find(shard_id);
    if (it != handle->slots.end()) {
        if (it->second.size != size) {
            handle->current_bytes = handle->current_bytes - it->second.size + size;
            it->second.data = realloc(it->second.data, size);
            it->second.size = size;
        }
        memcpy(it->second.data, data, size);
        it->second.priority = priority;
        it->second.last_access = std::chrono::steady_clock::now();
        return true;
    }

    // Evict if necessary
    while (handle->current_bytes + size > handle->capacity_bytes && !handle->lru_order.empty()) {
        uint32_t evict_id = handle->lru_order.back();
        auto evict_it = handle->slots.find(evict_id);
        if (evict_it != handle->slots.end()) {
            handle->current_bytes -= evict_it->second.size;
            if (evict_it->second.data) free(evict_it->second.data);
            handle->slots.erase(evict_it);
        }
        handle->lru_iter_map.erase(evict_id);
        handle->lru_order.pop_back();
    }

    // Allocate new slot
    void* new_data = malloc(size);
    if (!new_data) return false;
    memcpy(new_data, data, size);

    BufferSlot slot;
    slot.shard_id = shard_id;
    slot.data = new_data;
    slot.size = size;
    slot.priority = priority;
    slot.access_count = 1;
    slot.last_access = std::chrono::steady_clock::now();

    handle->slots[shard_id] = slot;
    handle->current_bytes += size;

    handle->lru_order.push_front(shard_id);
    handle->lru_iter_map[shard_id] = handle->lru_order.begin();

    return true;
}

void ws_buffer_touch(WSBufferHandle* handle, uint32_t shard_id) {
    if (!handle) return;
    std::lock_guard<std::mutex> lock(handle->mtx);
    auto it = handle->slots.find(shard_id);
    if (it != handle->slots.end()) {
        it->second.access_count++;
        it->second.last_access = std::chrono::steady_clock::now();

        auto iter_it = handle->lru_iter_map.find(shard_id);
        if (iter_it != handle->lru_iter_map.end()) {
            handle->lru_order.erase(iter_it->second);
        }
        handle->lru_order.push_front(shard_id);
        handle->lru_iter_map[shard_id] = handle->lru_order.begin();
    }
}

void ws_buffer_get_stats(WSBufferHandle* handle, WSBufferStats* out_stats) {
    if (!handle || !out_stats) return;
    std::lock_guard<std::mutex> lock(handle->mtx);
    out_stats->total_requests = handle->total_requests;
    out_stats->cache_hits = handle->cache_hits;
    out_stats->cache_misses = handle->cache_misses;
    out_stats->hit_rate = handle->total_requests > 0 
        ? (double)handle->cache_hits / (double)handle->total_requests 
        : 0.0;
    out_stats->current_memory_bytes = handle->current_bytes;
    out_stats->capacity_bytes = handle->capacity_bytes;
}

// --- OOM Protection: Check system memory pressure ---
bool ws_check_memory_pressure(WSMemoryPressure* out_pressure, double threshold) {
    if (!out_pressure) return false;

#ifdef _WIN32
    MEMORYSTATUSEX ms;
    ms.dwLength = sizeof(ms);
    if (GlobalMemoryStatusEx(&ms)) {
        out_pressure->total_bytes = ms.ullTotalPhys;
        out_pressure->available_bytes = ms.ullAvailPhys;
        out_pressure->memory_pressure = 1.0 - ((double)ms.ullAvailPhys / (double)ms.ullTotalPhys);
        out_pressure->should_evict = (out_pressure->memory_pressure > threshold);
        return true;
    }
#elif defined(__linux__)
    /* Read /proc/meminfo for MemTotal and MemAvailable */
    FILE* f = fopen("/proc/meminfo", "r");
    if (f) {
        char line[256];
        uint64_t mem_total = 0, mem_available = 0;
        while (fgets(line, sizeof(line), f)) {
            if (strncmp(line, "MemTotal:", 9) == 0) {
                sscanf(line + 9, " %lu", (unsigned long*)&mem_total);
            } else if (strncmp(line, "MemAvailable:", 13) == 0) {
                sscanf(line + 13, " %lu", (unsigned long*)&mem_available);
            }
        }
        fclose(f);
        out_pressure->total_bytes = mem_total * 1024;
        out_pressure->available_bytes = mem_available * 1024;
        if (mem_total > 0) {
            out_pressure->memory_pressure = 1.0 - ((double)mem_available / (double)mem_total);
        } else {
            out_pressure->memory_pressure = 0.0;
        }
        out_pressure->should_evict = (out_pressure->memory_pressure > threshold);
        return true;
    }
#endif

    out_pressure->memory_pressure = 0.0;
    out_pressure->should_evict = false;
    return false;
}

// --- Adaptive Eviction: Evict low-priority entries when under pressure ---
int ws_buffer_adaptive_evict(WSBufferHandle* handle, double pressure, int max_evictions) {
    if (!handle || pressure <= 0.0 || max_evictions <= 0) return 0;
    std::lock_guard<std::mutex> lock(handle->mtx);

    /* Scale eviction count by pressure intensity */
    int target = (int)(max_evictions * pressure);
    if (target < 1) target = 1;

    int evicted = 0;
    while (evicted < target && !handle->lru_order.empty()) {
        uint32_t evict_id = handle->lru_order.back();
        auto it = handle->slots.find(evict_id);
        if (it != handle->slots.end()) {
            handle->current_bytes -= it->second.size;
            if (it->second.data) free(it->second.data);
            handle->slots.erase(it);
        }
        handle->lru_iter_map.erase(evict_id);
        handle->lru_order.pop_back();
        evicted++;
    }
    return evicted;
}

// --- SIMD capability auto-detection ---
void ws_detect_simd(WSSIMDCapabilities* out_caps) {
    if (!out_caps) return;
    out_caps->has_avx2 = false;
    out_caps->has_avx512 = false;
    out_caps->has_neon = false;
    out_caps->best_backend = "scalar";

#if defined(__x86_64__) || defined(_M_X64) || defined(__i386__) || defined(_M_IX86)
    #ifdef _MSC_VER
        int cpuinfo[4] = {0};
        __cpuid(cpuinfo, 7);
        out_caps->has_avx2 = (cpuinfo[1] & (1 << 5)) != 0;
        out_caps->has_avx512 = (cpuinfo[1] & (1 << 16)) != 0;
    #elif defined(__GNUC__) || defined(__clang__)
        unsigned int eax, ebx, ecx, edx;
        if (__builtin_cpu_supports("avx512f")) {
            out_caps->has_avx512 = true;
        }
        if (__builtin_cpu_supports("avx2")) {
            out_caps->has_avx2 = true;
        }
    #endif

    if (out_caps->has_avx512) {
        out_caps->best_backend = "avx512";
    } else if (out_caps->has_avx2) {
        out_caps->best_backend = "avx2";
    }
#elif defined(__aarch64__) || defined(__ARM_NEON)
    out_caps->has_neon = true;
    out_caps->best_backend = "neon";
#endif
}

} // extern "C"
