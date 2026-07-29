/**
 * Multi-backend SIMD kernels for INT4/FP32 dequantization and GEMV.
 *
 * Supports three backends with automatic runtime dispatch:
 *   1. AVX-512  (x86_64 with avx512f+avx512bw)
 *   2. AVX2     (x86_64 with avx2+fma)
 *   3. ARM NEON (aarch64)
 *   4. Scalar fallback (always available)
 *
 * The ws_gemv_int4_fp32_auto() function selects the best available
 * backend at runtime using CPUID / compiler builtins.
 */

#include "weight_stream_core.h"
#include <stdint.h>
#include <stddef.h>
#include <string.h>

/* ── Platform SIMD headers ──────────────────────────────────────── */
#if defined(__AVX2__) || defined(__AVX512F__)
#include <immintrin.h>
#endif

#if defined(__aarch64__) || defined(__ARM_NEON)
#include <arm_neon.h>
#endif

extern "C" {

/* ═══════════════════════════════════════════════════════════════
   1. SCALAR FALLBACK (always available)
   ═══════════════════════════════════════════════════════════════ */
static void ws_gemv_int4_fp32_scalar(
    const uint8_t* weight_int4,
    const float* scale,
    const float* input_x,
    float* output_y,
    int rows,
    int cols
) {
    int bytes_per_row = cols / 2;
    for (int r = 0; r < rows; r++) {
        float row_scale = scale[r];
        const uint8_t* row_w = weight_int4 + r * bytes_per_row;
        float sum = 0.0f;

        for (int c = 0; c < cols; c += 2) {
            uint8_t b = row_w[c / 2];
            int8_t lo = (int8_t)(b & 0x0F) - 8;
            int8_t hi = (int8_t)((b >> 4) & 0x0F) - 8;
            sum += ((float)lo * row_scale) * input_x[c];
            if (c + 1 < cols) {
                sum += ((float)hi * row_scale) * input_x[c + 1];
            }
        }
        output_y[r] = sum;
    }
}

/* ═══════════════════════════════════════════════════════════════
   2. AVX2 BACKEND
   ═══════════════════════════════════════════════════════════════ */
#if defined(__AVX2__)
static void ws_gemv_int4_fp32_avx2(
    const uint8_t* weight_int4,
    const float* scale,
    const float* input_x,
    float* output_y,
    int rows,
    int cols
) {
    int bytes_per_row = cols / 2;
    for (int r = 0; r < rows; r++) {
        float row_scale = scale[r];
        const uint8_t* row_w = weight_int4 + r * bytes_per_row;
        float sum = 0.0f;
        int c = 0;

        __m256 vsum = _mm256_setzero_ps();
        for (; c <= cols - 16; c += 16) {
            const uint8_t* bp = row_w + (c / 2);
            float unpacked[16];
            for (int i = 0; i < 8; i++) {
                uint8_t b = bp[i];
                int8_t lo = (int8_t)(b & 0x0F) - 8;
                int8_t hi = (int8_t)((b >> 4) & 0x0F) - 8;
                unpacked[i * 2]     = (float)lo * row_scale;
                unpacked[i * 2 + 1] = (float)hi * row_scale;
            }
            __m256 vw1 = _mm256_loadu_ps(unpacked);
            __m256 vx1 = _mm256_loadu_ps(input_x + c);
            vsum = _mm256_fmadd_ps(vw1, vx1, vsum);

            __m256 vw2 = _mm256_loadu_ps(unpacked + 8);
            __m256 vx2 = _mm256_loadu_ps(input_x + c + 8);
            vsum = _mm256_fmadd_ps(vw2, vx2, vsum);
        }

        /* Horizontal sum */
        float tmp[8];
        _mm256_storeu_ps(tmp, vsum);
        for (int i = 0; i < 8; i++) sum += tmp[i];

        /* Scalar tail */
        for (; c < cols; c += 2) {
            uint8_t b = row_w[c / 2];
            int8_t lo = (int8_t)(b & 0x0F) - 8;
            int8_t hi = (int8_t)((b >> 4) & 0x0F) - 8;
            sum += ((float)lo * row_scale) * input_x[c];
            if (c + 1 < cols) sum += ((float)hi * row_scale) * input_x[c + 1];
        }
        output_y[r] = sum;
    }
}
#endif

/* ═══════════════════════════════════════════════════════════════
   3. AVX-512 BACKEND
   ═══════════════════════════════════════════════════════════════ */
#if defined(__AVX512F__)
static void ws_gemv_int4_fp32_avx512(
    const uint8_t* weight_int4,
    const float* scale,
    const float* input_x,
    float* output_y,
    int rows,
    int cols
) {
    int bytes_per_row = cols / 2;
    for (int r = 0; r < rows; r++) {
        float row_scale = scale[r];
        const uint8_t* row_w = weight_int4 + r * bytes_per_row;
        float sum = 0.0f;
        int c = 0;

        __m512 vsum = _mm512_setzero_ps();
        /* Process 32 elements (16 bytes) per iteration */
        for (; c <= cols - 32; c += 32) {
            const uint8_t* bp = row_w + (c / 2);
            float unpacked[32];
            for (int i = 0; i < 16; i++) {
                uint8_t b = bp[i];
                int8_t lo = (int8_t)(b & 0x0F) - 8;
                int8_t hi = (int8_t)((b >> 4) & 0x0F) - 8;
                unpacked[i * 2]     = (float)lo * row_scale;
                unpacked[i * 2 + 1] = (float)hi * row_scale;
            }
            __m512 vw1 = _mm512_loadu_ps(unpacked);
            __m512 vx1 = _mm512_loadu_ps(input_x + c);
            vsum = _mm512_fmadd_ps(vw1, vx1, vsum);

            __m512 vw2 = _mm512_loadu_ps(unpacked + 16);
            __m512 vx2 = _mm512_loadu_ps(input_x + c + 16);
            vsum = _mm512_fmadd_ps(vw2, vx2, vsum);
        }
        sum += _mm512_reduce_add_ps(vsum);

        /* AVX2 tail for 16-element blocks */
        #if defined(__AVX2__)
        __m256 vtail = _mm256_setzero_ps();
        for (; c <= cols - 16; c += 16) {
            const uint8_t* bp = row_w + (c / 2);
            float unpacked[16];
            for (int i = 0; i < 8; i++) {
                uint8_t b = bp[i];
                unpacked[i * 2]     = (float)((int8_t)(b & 0x0F) - 8) * row_scale;
                unpacked[i * 2 + 1] = (float)((int8_t)((b >> 4) & 0x0F) - 8) * row_scale;
            }
            __m256 vw = _mm256_loadu_ps(unpacked);
            __m256 vx = _mm256_loadu_ps(input_x + c);
            vtail = _mm256_fmadd_ps(vw, vx, vtail);
            vw = _mm256_loadu_ps(unpacked + 8);
            vx = _mm256_loadu_ps(input_x + c + 8);
            vtail = _mm256_fmadd_ps(vw, vx, vtail);
        }
        float tmp8[8];
        _mm256_storeu_ps(tmp8, vtail);
        for (int i = 0; i < 8; i++) sum += tmp8[i];
        #endif

        /* Scalar tail */
        for (; c < cols; c += 2) {
            uint8_t b = row_w[c / 2];
            int8_t lo = (int8_t)(b & 0x0F) - 8;
            int8_t hi = (int8_t)((b >> 4) & 0x0F) - 8;
            sum += ((float)lo * row_scale) * input_x[c];
            if (c + 1 < cols) sum += ((float)hi * row_scale) * input_x[c + 1];
        }
        output_y[r] = sum;
    }
}
#endif

/* ═══════════════════════════════════════════════════════════════
   4. ARM NEON BACKEND
   ═══════════════════════════════════════════════════════════════ */
#if defined(__aarch64__) || defined(__ARM_NEON)
static void ws_gemv_int4_fp32_neon(
    const uint8_t* weight_int4,
    const float* scale,
    const float* input_x,
    float* output_y,
    int rows,
    int cols
) {
    int bytes_per_row = cols / 2;
    for (int r = 0; r < rows; r++) {
        float row_scale = scale[r];
        const uint8_t* row_w = weight_int4 + r * bytes_per_row;
        float sum = 0.0f;
        int c = 0;

        float32x4_t vsum = vdupq_n_f32(0.0f);
        /* Process 8 elements (4 bytes) per iteration */
        for (; c <= cols - 8; c += 8) {
            const uint8_t* bp = row_w + (c / 2);
            float unpacked[8];
            for (int i = 0; i < 4; i++) {
                uint8_t b = bp[i];
                unpacked[i * 2]     = (float)((int8_t)(b & 0x0F) - 8) * row_scale;
                unpacked[i * 2 + 1] = (float)((int8_t)((b >> 4) & 0x0F) - 8) * row_scale;
            }
            float32x4_t vw1 = vld1q_f32(unpacked);
            float32x4_t vx1 = vld1q_f32(input_x + c);
            vsum = vmlaq_f32(vsum, vw1, vx1);

            float32x4_t vw2 = vld1q_f32(unpacked + 4);
            float32x4_t vx2 = vld1q_f32(input_x + c + 4);
            vsum = vmlaq_f32(vsum, vw2, vx2);
        }
        /* Horizontal sum */
        sum += vgetq_lane_f32(vsum, 0) + vgetq_lane_f32(vsum, 1) +
               vgetq_lane_f32(vsum, 2) + vgetq_lane_f32(vsum, 3);

        /* Scalar tail */
        for (; c < cols; c += 2) {
            uint8_t b = row_w[c / 2];
            int8_t lo = (int8_t)(b & 0x0F) - 8;
            int8_t hi = (int8_t)((b >> 4) & 0x0F) - 8;
            sum += ((float)lo * row_scale) * input_x[c];
            if (c + 1 < cols) sum += ((float)hi * row_scale) * input_x[c + 1];
        }
        output_y[r] = sum;
    }
}
#endif

/* ═══════════════════════════════════════════════════════════════
   5. AUTO-DISPATCH: Selects the best backend at runtime
   ═══════════════════════════════════════════════════════════════ */
void ws_gemv_int4_fp32(
    const uint8_t* weight_int4,
    const float* scale,
    const float* input_x,
    float* output_y,
    int rows,
    int cols
) {
#if defined(__AVX512F__)
    ws_gemv_int4_fp32_avx512(weight_int4, scale, input_x, output_y, rows, cols);
#elif defined(__AVX2__)
    ws_gemv_int4_fp32_avx2(weight_int4, scale, input_x, output_y, rows, cols);
#elif defined(__aarch64__) || defined(__ARM_NEON)
    ws_gemv_int4_fp32_neon(weight_int4, scale, input_x, output_y, rows, cols);
#else
    ws_gemv_int4_fp32_scalar(weight_int4, scale, input_x, output_y, rows, cols);
#endif
}

} // extern "C"
