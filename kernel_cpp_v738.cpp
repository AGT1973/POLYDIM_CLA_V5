// ==============================================================================
// POLYDIM V738 SOTA - C++ KERNEL (SILICON ARMORED EDITION)
// ==============================================================================
// Industrial Fixes Applied:
// 1. Strict C++17 headers (<cstdint>, <algorithm>, <vector>, <cmath>, <omp.h>).
// 2. Exact uint64_t / double ABI matching FFI python ctypes definitions.
// 3. High-quality splitmix64 PRNG + Box-Muller for true S^(D-1) unit vectors.
// 4. Mathematically exact rank-2 Sherman-Morrison-Woodbury Cayley retraction
//    with Cauchy-Schwarz det >= 1e-12 topological singularity guard.
// 5. Zero-heap-allocation BSC isometry using pre-allocated scratchpad.
// 6. Parallel KBN dot product & popcount.
// ==============================================================================

#include <cstdint>
#include <cstring>
#include <vector>
#include <cmath>
#include <algorithm>
#include <omp.h>

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

static inline uint64_t mix64(uint64_t x) {
    x += 0x9E3779B97F4A7C15ULL;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
    return x ^ (x >> 31);
}

extern "C" {

EXPORT void bsc_xor_single_step(uint64_t* tensor, uint64_t d_blocks, uint64_t seed) {
    if (!tensor || d_blocks == 0) return;
    #pragma omp parallel for
    for (int64_t i = 0; i < (int64_t)d_blocks; ++i) {
        uint64_t rnd = mix64(seed ^ mix64((uint64_t)i));
        tensor[i] ^= rnd;
    }
}

EXPORT void bsc_isometry_single_step(uint64_t* tensor, const uint64_t* permutation_lut, 
                                     const uint64_t* fixed_mask, uint64_t* scratchpad, uint64_t d_blocks) {
    if (!tensor || !permutation_lut || !fixed_mask || !scratchpad || d_blocks == 0) return;

    #pragma omp parallel for
    for (int64_t i = 0; i < (int64_t)d_blocks; ++i) {
        uint64_t p_idx = permutation_lut[i];
        if (p_idx < d_blocks) {
            scratchpad[i] = tensor[p_idx] ^ fixed_mask[i];
        } else {
            scratchpad[i] = 0;
        }
    }
    std::memcpy(tensor, scratchpad, d_blocks * sizeof(uint64_t));
}

EXPORT void precompute_isometry_composition(const uint64_t* perm_in, const uint64_t* mask_in,
                                             uint64_t* perm_out, uint64_t* mask_out,
                                             uint64_t d_blocks, uint64_t iterations) {
    if (!perm_in || !mask_in || !perm_out || !mask_out || d_blocks == 0) return;
    
    std::memcpy(perm_out, perm_in, d_blocks * sizeof(uint64_t));
    std::memcpy(mask_out, mask_in, d_blocks * sizeof(uint64_t));

    if (iterations <= 1) return;

    std::vector<uint64_t> p_cur(perm_in, perm_in + d_blocks);
    std::vector<uint64_t> m_cur(mask_in, mask_in + d_blocks);
    std::vector<uint64_t> p_next(d_blocks);
    std::vector<uint64_t> m_next(d_blocks);

    for (uint64_t it = 1; it < iterations; ++it) {
        for (uint64_t i = 0; i < d_blocks; ++i) {
            uint64_t pi = p_cur[i];
            if (pi < d_blocks) {
                p_next[i] = perm_in[pi];
                m_next[i] = m_cur[pi] ^ mask_in[i];
            } else {
                p_next[i] = i;
                m_next[i] = m_cur[i];
            }
        }
        p_cur = p_next;
        m_cur = m_next;
    }

    std::memcpy(perm_out, p_cur.data(), d_blocks * sizeof(uint64_t));
    std::memcpy(mask_out, m_cur.data(), d_blocks * sizeof(uint64_t));
}

struct alignas(64) KBNState { double sum; double comp; };

double compute_dot_product_kbn(const float* A, const float* B, uint64_t D) {
    const uint64_t CHUNK_SIZE = 4096;
    uint64_t num_chunks = (D + CHUNK_SIZE - 1) / CHUNK_SIZE;
    std::vector<KBNState> chunks(num_chunks, {0.0, 0.0});

    #pragma omp parallel for
    for (int64_t c = 0; c < (int64_t)num_chunks; ++c) {
        uint64_t start = c * CHUNK_SIZE;
        uint64_t end = std::min(start + CHUNK_SIZE, D);
        double sum = 0.0, comp = 0.0;
        for (uint64_t i = start; i < end; ++i) {
            double val = (double)A[i] * (double)B[i];
            double y = val - comp;
            double t = sum + y;
            comp = (t - sum) - y;
            sum = t;
        }
        chunks[c].sum = sum;
        chunks[c].comp = comp;
    }

    double final_sum = 0.0, final_comp = 0.0;
    for (uint64_t c = 0; c < num_chunks; ++c) {
        double y = chunks[c].sum - final_comp;
        double t = final_sum + y;
        final_comp = (t - final_sum) - y;
        final_sum = t;
    }
    return final_sum;
}

EXPORT double compute_l2_norm_f64_accum(const float* tensor, uint64_t D) {
    if (!tensor || D == 0) return 0.0;
    return std::sqrt(compute_dot_product_kbn(tensor, tensor, D));
}

EXPORT uint64_t compute_hamming_weight(const uint64_t* tensor, uint64_t d_blocks) {
    if (!tensor || d_blocks == 0) return 0;
    uint64_t total = 0;
    #pragma omp parallel for reduction(+:total)
    for (int64_t i = 0; i < (int64_t)d_blocks; ++i) {
#ifdef _MSC_VER
        total += (uint64_t)__popcnt64(tensor[i]);
#else
        total += (uint64_t)__builtin_popcountll(tensor[i]);
#endif
    }
    return total;
}

EXPORT void generate_random_unit_vector_f32(float* v, uint64_t D, uint64_t seed) {
    if (!v || D == 0) return;
    
    #pragma omp parallel for
    for (int64_t i = 0; i < (int64_t)D; i += 2) {
        uint64_t s1 = mix64(seed ^ mix64((uint64_t)i));
        uint64_t s2 = mix64(s1 ^ 0xBF58476D1CE4E5B9ULL);
        
        double u1 = ((double)(s1 >> 11) + 1.0) / 9007199254740993.0;
        double u2 = ((double)(s2 >> 11) + 1.0) / 9007199254740993.0;
        
        double radius = std::sqrt(-2.0 * std::log(u1));
        double theta = 6.28318530717958647692 * u2;
        
        v[i] = (float)(radius * std::cos(theta));
        if (i + 1 < (int64_t)D) {
            v[i + 1] = (float)(radius * std::sin(theta));
        }
    }
    
    double norm = compute_l2_norm_f64_accum(v, D);
    if (norm < 1e-12) norm = 1.0;
    double inv_norm = 1.0 / norm;
    
    #pragma omp parallel for
    for (int64_t i = 0; i < (int64_t)D; ++i) {
        v[i] = (float)((double)v[i] * inv_norm);
    }
}

EXPORT void householder_single_step_f32(float* tensor, const float* v, uint64_t D) {
    if (!tensor || !v || D == 0) return;
    double dot_product = compute_dot_product_kbn(tensor, v, D);
    double scale = -2.0 * dot_product;

    #pragma omp parallel for
    for (int64_t i = 0; i < (int64_t)D; ++i) {
        tensor[i] = (float)((double)tensor[i] + scale * (double)v[i]);
    }
}

EXPORT void apply_cayley_smw_retraction_f32(float* Y, const float* U, const float* V, double alpha, uint64_t D) {
    if (!Y || !U || !V || D == 0) return;
    if (std::abs(alpha) < 1e-15) return;
    
    double uu = compute_dot_product_kbn(U, U, D);
    double vv = compute_dot_product_kbn(V, V, D);
    double uv = compute_dot_product_kbn(U, V, D);
    double uy = compute_dot_product_kbn(U, Y, D);
    double vy = compute_dot_product_kbn(V, Y, D);

    double beta = alpha * 0.5;
    double gram_det = uu * vv - uv * uv;
    double det = 1.0 + beta * beta * gram_det;
    
    if (std::abs(det) < 1e-12) return; // Topological singularity guard

    double a = 2.0 * beta * ((1.0 + beta * uv) * vy - beta * vv * uy) / det;
    double b = -2.0 * beta * (beta * uu * vy + (1.0 - beta * uv) * uy) / det;

    #pragma omp parallel for
    for (int64_t i = 0; i < (int64_t)D; ++i) {
        double yi = (double)Y[i];
        yi += a * (double)U[i] + b * (double)V[i];
        Y[i] = (float)yi;
    }
}

} // extern "C"
