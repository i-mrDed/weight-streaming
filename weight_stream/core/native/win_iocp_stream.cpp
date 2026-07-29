#include "weight_stream_core.h"

#ifdef _WIN32
#include <windows.h>
#include <psapi.h>

extern "C" {

bool ws_get_memory_stats(WSMemoryStats* out_stats) {
    if (!out_stats) return false;

    PROCESS_MEMORY_COUNTERS_EX pmc;
    if (GetProcessMemoryInfo(GetCurrentProcess(), (PROCESS_MEMORY_COUNTERS*)&pmc, sizeof(pmc))) {
        out_stats->working_set_bytes = pmc.WorkingSetSize;
        out_stats->pagefile_usage_bytes = pmc.PrivateUsage;
    } else {
        out_stats->working_set_bytes = 0;
        out_stats->pagefile_usage_bytes = 0;
    }

    MEMORYSTATUSEX memStatus;
    memStatus.dwLength = sizeof(MEMORYSTATUSEX);
    if (GlobalMemoryStatusEx(&memStatus)) {
        out_stats->total_physical_ram = memStatus.ullTotalPhys;
        out_stats->resident_ratio = (double)out_stats->working_set_bytes / (double)memStatus.ullTotalPhys;
    } else {
        out_stats->total_physical_ram = 0;
        out_stats->resident_ratio = 0.0;
    }

    return true;
}

bool ws_is_address_resident(void* addr, size_t size, double* out_resident_ratio) {
    if (!addr || size == 0 || !out_resident_ratio) return false;

    SYSTEM_INFO sysInfo;
    GetSystemInfo(&sysInfo);
    size_t pageSize = sysInfo.dwPageSize;

    uintptr_t startAddr = (uintptr_t)addr;
    uintptr_t endAddr = startAddr + size;
    uintptr_t startPage = startAddr & ~(pageSize - 1);
    uintptr_t endPage = (endAddr + pageSize - 1) & ~(pageSize - 1);

    size_t numPages = (endPage - startPage) / pageSize;
    if (numPages == 0) {
        *out_resident_ratio = 1.0;
        return true;
    }

    // Allocate memory for QueryWorkingSetEx
    size_t infoArraySize = numPages * sizeof(PSAPI_WORKING_SET_EX_INFORMATION);
    PSAPI_WORKING_SET_EX_INFORMATION* infoArray = (PSAPI_WORKING_SET_EX_INFORMATION*)malloc(infoArraySize);
    if (!infoArray) return false;

    for (size_t i = 0; i < numPages; i++) {
        infoArray[i].VirtualAddress = (void*)(startPage + i * pageSize);
    }

    size_t residentPages = 0;
    if (QueryWorkingSetEx(GetCurrentProcess(), infoArray, (DWORD)infoArraySize)) {
        for (size_t i = 0; i < numPages; i++) {
            if (infoArray[i].VirtualAttributes.Valid) {
                residentPages++;
            }
        }
        *out_resident_ratio = (double)residentPages / (double)numPages;
        free(infoArray);
        return true;
    }

    free(infoArray);
    *out_resident_ratio = 0.0;
    return false;
}

} // extern "C"

#else

// POSIX Stub implementation for Non-Windows platforms
extern "C" {
bool ws_get_memory_stats(WSMemoryStats* out_stats) {
    if (!out_stats) return false;
    out_stats->working_set_bytes = 0;
    out_stats->pagefile_usage_bytes = 0;
    out_stats->total_physical_ram = 0;
    out_stats->resident_ratio = 0.0;
    return true;
}

bool ws_is_address_resident(void* addr, size_t size, double* out_resident_ratio) {
    if (!out_resident_ratio) return false;
    *out_resident_ratio = 1.0; // Assume resident on non-windows
    return true;
}
}
#endif
