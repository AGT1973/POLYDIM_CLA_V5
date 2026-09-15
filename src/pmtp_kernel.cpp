// ============================================================================
// POLYDIM V727 - CAYLEY ISOMÉTRICO (FIX KDK, ALIGNED_ALLOC, RUST PARITY)
// ============================================================================
#include <cmath>
#include <cstdint>
#include <cstring>
#include <omp.h>
#include <cstdlib>

#if defined(_MSC_VER)
#define PMTP_EXPORT extern "C" __declspec(dllexport)
#else
#define PMTP_EXPORT extern "C" __attribute__((visibility("default")))
#endif

// Error Codes
#define PMTP_OK 0
#define PMTP_ERR_NULL 1
#define PMTP_ERR_DIM 2
#define PMTP_ERR_SINGULAR 3
#define PMTP_ERR_DT 4
#define PMTP_ERR_ALLOC 5
#define PMTP_ERR_ALIAS 6

constexpr double EPSILON_FP64 = 1e-14;

struct alignas(64) ThreadAccumulator {
    double sum[4] = {0};
    double c[4] = {0};
};

inline void neumaier_add(double& sum, double& c, double val) {
    double t = sum + val;
    if (std::abs(sum) >= std::abs(val)) {
        c += (sum - t) + val;
    } else {
        c += (val - t) + sum;
    }
    sum = t;
}

inline bool ranges_overlap(const double* a, const double* b, size_t n) {
    return a < b + n && b < a + n;
}

PMTP_EXPORT int cayley_step_global_isometry(
    const double* S_in, const double* V_in, 
    double* S_next_in, double* V_next_in, 
    double* W_scratch, 
    size_t dim, double dt
) {
    if (!S_in || !V_in || !S_next_in || !V_next_in || !W_scratch) return PMTP_ERR_NULL;
    if (dim == 0) return PMTP_ERR_DIM;
    if (!(dt > 0.0) || !std::isfinite(dt)) return PMTP_ERR_DT;
    
    if (ranges_overlap(S_in, W_scratch, dim) || ranges_overlap(V_in, W_scratch, dim) ||
        ranges_overlap(S_in, S_next_in, dim) || ranges_overlap(V_in, V_next_in, dim) ||
        ranges_overlap(S_next_in, V_next_in, dim)) return PMTP_ERR_ALIAS;

    int max_threads = omp_get_max_threads();
    
#if defined(_MSC_VER)
    ThreadAccumulator* local_acc = (ThreadAccumulator*)_aligned_malloc(max_threads * sizeof(ThreadAccumulator), 64);
#else
    ThreadAccumulator* local_acc = (ThreadAccumulator*)aligned_alloc(64, max_threads * sizeof(ThreadAccumulator));
#endif
    if (!local_acc) return PMTP_ERR_ALLOC;
    
    std::memset(local_acc, 0, max_threads * sizeof(ThreadAccumulator));

    #pragma omp parallel
    {
        int tid = omp_get_thread_num();
        #pragma omp for
        for (size_t i = 0; i < dim; ++i) {
            double s = S_in[i];
            double v = V_in[i];
            neumaier_add(local_acc[tid].sum[0], local_acc[tid].c[0], s * s);
            neumaier_add(local_acc[tid].sum[1], local_acc[tid].c[1], s * v);
        }
    }
    
    double dot_ss = 0.0, dot_sv = 0.0;
    for(int t = 0; t < max_threads; ++t) { 
        dot_ss += local_acc[t].sum[0] + local_acc[t].c[0]; 
        dot_sv += local_acc[t].sum[1] + local_acc[t].c[1]; 
    }
    
    if (!(dot_ss >= EPSILON_FP64)) {
#if defined(_MSC_VER)
        _aligned_free(local_acc);
#else
        free(local_acc);
#endif
        return PMTP_ERR_SINGULAR;
    }
    double proj1 = dot_sv / dot_ss;

    #pragma omp parallel
    {
        int tid = omp_get_thread_num();
        #pragma omp for
        for (size_t i = 0; i < dim; ++i) {
            double w1 = V_in[i] - proj1 * S_in[i];
            neumaier_add(local_acc[tid].sum[2], local_acc[tid].c[2], S_in[i] * w1);
        }
    }
    double dot_sw = 0.0;
    for(int t = 0; t < max_threads; ++t) { dot_sw += local_acc[t].sum[2] + local_acc[t].c[2]; }
    double proj2 = dot_sw / dot_ss;

    #pragma omp parallel
    {
        int tid = omp_get_thread_num();
        #pragma omp for
        for (size_t i = 0; i < dim; ++i) {
            double vt = (V_in[i] - proj1 * S_in[i]) - proj2 * S_in[i];
            double w = vt * dt;
            W_scratch[i] = w;
            neumaier_add(local_acc[tid].sum[3], local_acc[tid].c[3], w * w);
        }
    }
    
    double total_w_sq = 0.0;
    for(int t = 0; t < max_threads; ++t) { total_w_sq += local_acc[t].sum[3] + local_acc[t].c[3]; }

    double u2_global = total_w_sq / 4.0;
    double denom = 1.0 + u2_global;
    
    double scale_s = (1.0 - u2_global) / denom;
    double scale_w = 1.0 / denom;
    // FIX MATEMÁTICO: Evitar dt*dt underflow y remover el /4 arrastrado.
    double rot_v_scalar = -(total_w_sq / dt) / denom; 
    double rot_v_tangent = ((1.0 - u2_global) / denom) / dt;

    #pragma omp parallel for
    for (size_t i = 0; i < dim; ++i) {
        S_next_in[i] = scale_s * S_in[i] + scale_w * W_scratch[i];
        V_next_in[i] = rot_v_scalar * S_in[i] + rot_v_tangent * W_scratch[i];
    }
    
#if defined(_MSC_VER)
    _aligned_free(local_acc);
#else
    free(local_acc);
#endif
    return PMTP_OK;
}
