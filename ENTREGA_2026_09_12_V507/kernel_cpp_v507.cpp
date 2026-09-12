#include <cstdint>
#include <immintrin.h>
#include <intrin.h>

extern "C" {

// V507 CRITICAL FIX: Add _xgetbv(0) OS check to prevent #UD on VMs
int os_supports_avx() {
#if defined(_MSC_VER) || defined(__INTEL_COMPILER)
    unsigned long long xcr0 = _xgetbv(0);
#else
    unsigned int xcr0;
    __asm__("xgetbv" : "=a" (xcr0) : "c" (0) : "%edx");
#endif
    return (xcr0 & 6) == 6; // Check if XMM and YMM state are enabled
}

// Fixed C++ hardware query that checks XCR0
__declspec(dllexport) int pmtp_cpp_validate_hardware(void) {
    int cpuInfo[4];
    __cpuid(cpuInfo, 1);
    bool osxsaveSupported = cpuInfo[2] & (1 << 27);
    bool avxSupported = cpuInfo[2] & (1 << 28);
    
    if (avxSupported && osxsaveSupported) {
        if (os_supports_avx()) {
            return 1; // AVX fully supported by CPU and OS
        }
    }
    return 0; // AVX not safely available
}

// V507 FIX: Relax BF16 alignment check (2-byte element size)
__declspec(dllexport) int pmtp_cpp_validate_tensor_alignment(const void* ptr, int element_size) {
    auto addr = reinterpret_cast<uintptr_t>(ptr);
    if (element_size == 2) {
        return (addr % 16 == 0) ? 1 : 0; // Accept 16-byte alignment for BF16 numpy
    }
    return (addr % 64 == 0) ? 1 : 0; // AVX-512 preferred for FP32
}

// [V507 RED TEAM FIX P1-4]: SLERP Antipodal Colapse Fix
__declspec(dllexport) void pmtp_cpp_slerp_safe_nd(const float* v0, const float* v1, float* out, size_t dim, float t) {
    float dot = 0.0f;
    for(size_t i = 0; i < dim; i++) { dot += v0[i] * v1[i]; }
    
    // Clamp floating point errors
    if (dot > 0.9995f) {
        // Fallback lineal + normalización (muy cerca)
        float norm_sq = 0.0f;
        for(size_t i = 0; i < dim; i++) {
            out[i] = v0[i] + t * (v1[i] - v0[i]);
            norm_sq += out[i] * out[i];
        }
        float inv_norm = 1.0f / sqrtf(norm_sq);
        for(size_t i = 0; i < dim; i++) out[i] *= inv_norm;
        return;
    }
    
    if (dot < -0.9995f) {
        // RAMA ANTIPODAL: El riesgo de colapso a 0 es inminente.
        // Aproximación ortogonal por Gram-Schmidt rápida:
        float ortho[10000]; // Asumimos dim = 10000 max para V507
        float v0_dot_v0 = 0.0f, v1_dot_v0 = 0.0f;
        for(size_t i = 0; i < dim; i++) {
            v0_dot_v0 += v0[i] * v0[i];
            v1_dot_v0 += v1[i] * v0[i];
        }
        float proj_scalar = v1_dot_v0 / v0_dot_v0;
        
        float ortho_norm_sq = 0.0f;
        for(size_t i = 0; i < dim; i++) {
            ortho[i] = v1[i] - proj_scalar * v0[i];
            ortho_norm_sq += ortho[i] * ortho[i];
        }
        float ortho_inv_norm = 1.0f / sqrtf(ortho_norm_sq);
        
        // slerp_standard interpolando 90 grados con el vector ortogonal:
        float theta_0 = acosf(dot); 
        float theta = theta_0 * t;
        float sin_theta = sinf(theta);
        float cos_theta = cosf(theta);
        
        for(size_t i = 0; i < dim; i++) {
            out[i] = (v0[i] * cos_theta) + (ortho[i] * ortho_inv_norm * sin_theta);
        }
        return;
    }
    
    // SLERP standard
    float theta_0 = acosf(dot);
    float theta = theta_0 * t;
    float sin_theta_0 = sinf(theta_0);
    float s0 = cosf(theta) - dot * sinf(theta) / sin_theta_0;
    float s1 = sinf(theta) / sin_theta_0;
    
    for(size_t i = 0; i < dim; i++) {
        out[i] = (s0 * v0[i]) + (s1 * v1[i]);
    }
}

}

