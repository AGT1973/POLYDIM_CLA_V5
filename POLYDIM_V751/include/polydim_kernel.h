/*
 * POLYDIM V751 INDUSTRIAL CORE - C/C++ ABI & CONTRACT SPECIFICATION
 * 
 * Formal ABI Header for High-Dimensional Geometric Tensor Engine (S^{D-1})
 * All functions use C linkage (extern "C") with explicit error code taxonomy.
 */

#ifndef POLYDIM_KERNEL_H
#define POLYDIM_KERNEL_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* --- Export/Visibility Macros --- */
#if defined(_WIN32) || defined(__CYGWIN__)
  #ifdef POLYDIM_BUILD_DLL
    #define POLYDIM_API __declspec(dllexport)
  #else
    #define POLYDIM_API __declspec(dllimport)
  #endif
#else
  #if defined(__GNUC__) && __GNUC__ >= 4
    #define POLYDIM_API __attribute__((visibility("default")))
  #else
    #define POLYDIM_API
  #endif
#endif

/* --- Formal Status & Error Taxonomy --- */
typedef enum {
    POLYDIM_SUCCESS                     = 0,
    POLYDIM_ERR_NULL_POINTER            = -1,
    POLYDIM_ERR_INVALID_DIMENSION       = -2,
    POLYDIM_ERR_NAN_INF_DETECTED        = -3,
    POLYDIM_ERR_ZERO_VECTOR             = -4,
    POLYDIM_ERR_COLLINEAR_VECTORS       = -5,
    POLYDIM_ERR_MEMORY_OVERLAP          = -6,
    POLYDIM_ERR_YCOMP_BUDGET_EXCEEDED   = -7,
    POLYDIM_ERR_SEQLOCK_RACE            = -8,
    POLYDIM_ERR_PANIC_CAUGHT            = -9,
    POLYDIM_ERR_UNALIGNED_POINTER       = -10
} polydim_status_t;

/* --- Architectural Limits --- */
#define POLYDIM_MAX_DIMENSION ((uint64_t)1 << 32) /* 4,294,967,296 elements */
#define POLYDIM_CACHE_LINE_BYTES 64

/* --- SEQLock Protocol Header (For Shared Memory / IPC) --- */
typedef struct {
    volatile uint64_t sequence; /* odd = write in progress, even = stable snapshot */
    uint64_t dimension;
    uint64_t payload_bytes;
    uint32_t reserved[8];
} polydim_seqlock_header_t;

/* --- Forward Parameters Struct (FlashAttention / Clean API Pattern) --- */
typedef struct {
    double* y;               /* Target tensor in S^{D-1} [D] */
    double* y_comp;          /* Neumaier decimal compensation buffer [D] */
    const double* u;         /* Basis vector U [D] */
    const double* v;         /* Basis vector V [D] */
    double theta;            /* Geodesic rotation angle (radians) */
    uint64_t D;              /* High dimension (D >= 10,000) */
    int num_threads;         /* 0 = auto-detect OpenMP max threads */
} polydim_rodrigues_params_t;

/* --- Core Engine API Functions --- */

/**
 * Returns the semantic version of the native library (e.g. 0x07050100 for 7.51.0).
 */
POLYDIM_API uint32_t polydim_get_version(void);

/**
 * Validates pointer alignment to 64-byte boundary (AVX-512 / Cache-line alignment).
 */
POLYDIM_API polydim_status_t polydim_check_alignment(const void* ptr, size_t alignment);

/**
 * Initializes a tensor buffer to zero using OpenMP multi-threading.
 */
POLYDIM_API polydim_status_t polydim_zero_alloc_f64(double* tensor, uint64_t D);

/**
 * Exact Closed-Form Rodrigues Rank-2 Geodesic Rotation on S^{D-1}.
 * Implements Neumaier compensated accumulation and Versine small-angle formulation.
 */
POLYDIM_API polydim_status_t polydim_apply_rodrigues_geodesic_f64(const polydim_rodrigues_params_t* params);

/**
 * SEQLock Writer: Begin write transaction (transitions sequence to ODD).
 */
POLYDIM_API void polydim_seqlock_write_begin(polydim_seqlock_header_t* lock);

/**
 * SEQLock Writer: End write transaction (transitions sequence to EVEN with release barrier).
 */
POLYDIM_API void polydim_seqlock_write_end(polydim_seqlock_header_t* lock);

/**
 * SEQLock Reader: Begin read transaction (acquires sequence number).
 */
POLYDIM_API uint64_t polydim_seqlock_read_begin(const polydim_seqlock_header_t* lock);

/**
 * SEQLock Reader: Validate read transaction (returns 1 if snapshot is valid, 0 if mid-write collision).
 */
POLYDIM_API int polydim_seqlock_read_validate(const polydim_seqlock_header_t* lock, uint64_t start_seq);

#ifdef __cplusplus
}
#endif

#endif /* POLYDIM_KERNEL_H */
