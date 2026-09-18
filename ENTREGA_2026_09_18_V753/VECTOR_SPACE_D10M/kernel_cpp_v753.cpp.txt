static inline bool is_aligned(const void* ptr, size_t alignment) {
    return (reinterpret_cast<uintptr_t>(ptr) % alignment) == 0;
}
static inline bool check_overlap(const void* a, uint64_t size_a, const void* b, uint64_t size_b) {
    if (!a || !b || size_a == 0 || size_b == 0) return false;
    uintptr_t start_a = reinterpret_cast<uintptr_t>(a);
    uintptr_t start_b = reinterpret_cast<uintptr_t>(b);
    if (size_a > UINTPTR_MAX - start_a || size_b > UINTPTR_MAX - start_b) return true;
    uintptr_t end_a = start_a + size_a;
    uintptr_t end_b = start_b + size_b;
    return (start_a < end_b) && (start_b < end_a);
}
struct alignas(POLYDIM_CACHE_LINE_BYTES) PaddedAcc {
    double sum;
    double c;
    PaddedAcc() : sum(0.0), c(0.0) {}
};
static inline void neumaier_add(double& sum, double& c, double val) noexcept {
    double t = sum + val;
    if (std::abs(sum) >= std::abs(val)) {
        c += (sum - t) + val;
    } else {
        c += (val - t) + sum;
    }
    sum = t;
}
extern "C" {
POLYDIM_API uint32_t polydim_get_version(void) {
    return 0x07330100; // Version 7.51.0
}
POLYDIM_API polydim_status_t polydim_check_alignment(const void* ptr, size_t alignment) {
    if (!ptr) return POLYDIM_ERR_NULL_POINTER;
    return is_aligned(ptr, alignment) ? POLYDIM_SUCCESS : POLYDIM_ERR_UNALIGNED_POINTER;
}
POLYDIM_API polydim_status_t polydim_zero_alloc_f64(double* tensor, uint64_t D) {
    if (!tensor) return POLYDIM_ERR_NULL_POINTER;
    if (D == 0 || D > POLYDIM_MAX_DIMENSION) return POLYDIM_ERR_INVALID_DIMENSION;
    for (int64_t i = 0; i < static_cast<int64_t>(D); ++i) {
        tensor[i] = 0.0;
    }
    return POLYDIM_SUCCESS;
}
POLYDIM_API polydim_status_t polydim_apply_rodrigues_geodesic_f64(const polydim_rodrigues_params_t* params) {
    if (!params) return POLYDIM_ERR_NULL_POINTER;
    if (!params->y || !params->u || !params->v) return POLYDIM_ERR_NULL_POINTER;
    uint64_t D = params->D;
    if (D == 0 || D > POLYDIM_MAX_DIMENSION) return POLYDIM_ERR_INVALID_DIMENSION;
    double theta = params->theta;
    if (!std::isfinite(theta)) return POLYDIM_ERR_NAN_INF_DETECTED;
    double* y = params->y;
    double* y_comp = params->y_comp;
    const double* u_raw = params->u;
    const double* v_raw = params->v;
    uint64_t bytes = D * sizeof(double);
    if (check_overlap(y, bytes, u_raw, bytes) || check_overlap(y, bytes, v_raw, bytes)) {
        return POLYDIM_ERR_MEMORY_OVERLAP;
    }
    if (y_comp && (check_overlap(y_comp, bytes, u_raw, bytes) || check_overlap(y_comp, bytes, v_raw, bytes))) {
        return POLYDIM_ERR_MEMORY_OVERLAP;
    }
    int max_threads = omp_get_max_threads();
    int num_threads = (params->num_threads > 0 && params->num_threads <= max_threads) ? params->num_threads : max_threads;
    std::vector<PaddedAcc> acc_u(num_threads), acc_v(num_threads), acc_uv(num_threads);
    {
        int tid = omp_get_thread_num();
        for (int64_t i = 0; i < static_cast<int64_t>(D); ++i) {
            neumaier_add(acc_u[tid].sum, acc_u[tid].c, u_raw[i] * u_raw[i]);
            neumaier_add(acc_v[tid].sum, acc_v[tid].c, v_raw[i] * v_raw[i]);
            neumaier_add(acc_uv[tid].sum, acc_uv[tid].c, u_raw[i] * v_raw[i]);
        }
    }
    double norm2_u = 0.0, c_u_norm = 0.0;
    double norm2_v = 0.0, c_v_norm = 0.0;
    double dot_uv  = 0.0, c_uv_dot = 0.0;
    for (int t = 0; t < num_threads; ++t) {
        neumaier_add(norm2_u, c_u_norm, acc_u[t].sum + acc_u[t].c);
        neumaier_add(norm2_v, c_v_norm, acc_v[t].sum + acc_v[t].c);
        neumaier_add(dot_uv,  c_uv_dot, acc_uv[t].sum + acc_uv[t].c);
    }
    norm2_u += c_u_norm;
    norm2_v += c_v_norm;
    dot_uv  += c_uv_dot;
    if (norm2_u <= 1e-30 || norm2_v <= 1e-30) return POLYDIM_ERR_ZERO_VECTOR;
    double inv_norm_u = 1.0 / std::sqrt(norm2_u);
    double proj_uv = dot_uv / norm2_u;
    std::vector<PaddedAcc> acc_yu(num_threads), acc_yv(num_threads);
    {
        int tid = omp_get_thread_num();
        for (int64_t i = 0; i < static_cast<int64_t>(D); ++i) {
            double u_i = u_raw[i] * inv_norm_u;
            double v_ortho_i = v_raw[i] - proj_uv * u_raw[i];
            neumaier_add(acc_yu[tid].sum, acc_yu[tid].c, y[i] * u_i);
            neumaier_add(acc_yv[tid].sum, acc_yv[tid].c, y[i] * v_ortho_i);
        }
    }
    double c_u = 0.0, c_yu_acc = 0.0;
    double c_v_unnorm = 0.0, c_yv_acc = 0.0;
    for (int t = 0; t < num_threads; ++t) {
        neumaier_add(c_u, c_yu_acc, acc_yu[t].sum + acc_yu[t].c);
        neumaier_add(c_v_unnorm, c_yv_acc, acc_yv[t].sum + acc_yv[t].c);
    }
    c_u += c_yu_acc;
    c_v_unnorm += c_yv_acc;
    double norm2_v_ortho = norm2_v - (dot_uv * dot_uv / norm2_u);
    if (norm2_v_ortho <= 1e-30) return POLYDIM_ERR_COLLINEAR_VECTORS;
    double inv_norm_v_ortho = 1.0 / std::sqrt(norm2_v_ortho);
    double c_v = c_v_unnorm * inv_norm_v_ortho;
    double half_theta = theta * 0.5;
    double sin_half = std::sin(half_theta);
    double coeff_p = -2.0 * sin_half * sin_half;
    double coeff_j = std::sin(theta);
    for (int64_t i = 0; i < static_cast<int64_t>(D); ++i) {
        double u_i = u_raw[i] * inv_norm_u;
        double v_i = (v_raw[i] - proj_uv * u_raw[i]) * inv_norm_v_ortho;
        double delta_y = coeff_p * (c_u * u_i + c_v * v_i) + coeff_j * (c_u * v_i - c_v * u_i);
        if (y_comp) {
            neumaier_add(y[i], y_comp[i], delta_y);
        } else {
            y[i] += delta_y;
        }
    }
    return POLYDIM_SUCCESS;
}
POLYDIM_API void polydim_seqlock_write_begin(polydim_seqlock_header_t* lock) {
    if (!lock) return;
    auto* atomic_seq = reinterpret_cast<std::atomic<uint64_t>*>(const_cast<uint64_t*>(&lock->sequence));
    atomic_seq->fetch_add(1, std::memory_order_acq_rel); // Atomic odd increment
}
POLYDIM_API void polydim_seqlock_write_end(polydim_seqlock_header_t* lock) {
    if (!lock) return;
    std::atomic_thread_fence(std::memory_order_release); // Full barrier for data visibility
    auto* atomic_seq = reinterpret_cast<std::atomic<uint64_t>*>(const_cast<uint64_t*>(&lock->sequence));
    atomic_seq->fetch_add(1, std::memory_order_acq_rel); // Atomic even increment
}
POLYDIM_API uint64_t polydim_seqlock_read_begin(const polydim_seqlock_header_t* lock) {
    if (!lock) return 1;
    auto* atomic_seq = reinterpret_cast<const std::atomic<uint64_t>*>(const_cast<const uint64_t*>(&lock->sequence));
    uint64_t seq;
    do {
        seq = atomic_seq->load(std::memory_order_acquire);
        while (seq & 1ULL) {
            POLYDIM_PAUSE(); // Prevent cache starvation and bus contention
            seq = atomic_seq->load(std::memory_order_acquire);
        }
        std::atomic_thread_fence(std::memory_order_acquire);
        return seq;
    } while(false);
}
POLYDIM_API int polydim_seqlock_read_validate(const polydim_seqlock_header_t* lock, uint64_t start_seq) {
    if (!lock) return 0;
    std::atomic_thread_fence(std::memory_order_acquire);
    auto* atomic_seq = reinterpret_cast<const std::atomic<uint64_t>*>(const_cast<const uint64_t*>(&lock->sequence));
    uint64_t current = atomic_seq->load(std::memory_order_acquire);
    return (current == start_seq && !(current & 1ULL)) ? 1 : 0;
}
} // extern "C"
