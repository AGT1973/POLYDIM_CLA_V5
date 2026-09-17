// ==============================================================================
// POLYDIM V738 SOTA - RUST KERNEL (TOPOLOGICAL VALIDATORS)
// ==============================================================================
// Industrial Fixes Applied:
// 1. Replaced `read_volatile` with `std::hint::black_box` (eradicates LLVM UB).
// 2. Added missing exported validators `check_hamming_weight` and `check_hamming_distance`.
// 3. Strict pointer alignment and bounds checks (`ffi_check_ptr!`).
// 4. Panic unwinding isolation (`catch_unwind`).
// ==============================================================================

use std::panic;
use std::mem::align_of;
use std::hint::black_box;

macro_rules! ffi_check_ptr {
    ($ptr:expr, $len:expr, $ty:ty, $err:expr) => {
        if $ptr.is_null() { return $err; }
        if ($ptr as usize) % align_of::<$ty>() != 0 { return $err; }
        let max_len = (isize::MAX as usize) / std::mem::size_of::<$ty>();
        if $len > max_len { return $err; }
    };
}

#[no_mangle]
pub extern "C" fn check_l2_norm_f32(tensor: *const f32, length: usize) -> f64 {
    let result = panic::catch_unwind(|| {
        ffi_check_ptr!(tensor, length, f32, f64::NAN);
        if length == 0 { return 0.0; }
        let slice = unsafe { std::slice::from_raw_parts(tensor, length) };
        
        let mut sum: f64 = 0.0;
        let mut c: f64 = 0.0;
        
        for &val in slice {
            let v = val as f64;
            if !v.is_finite() { return f64::NAN; }
            
            let y = (v * v) - black_box(c);
            let t = sum + y;
            c = black_box((t - sum) - y);
            sum = t;
        }
        
        if sum < 0.0 { return f64::NAN; }
        sum.sqrt()
    });
    result.unwrap_or(f64::NAN)
}

#[no_mangle]
pub extern "C" fn check_pairwise_inner_products(tensor_a: *const f32, tensor_b: *const f32, length: usize) -> f64 {
    let result = panic::catch_unwind(|| {
        ffi_check_ptr!(tensor_a, length, f32, f64::NAN);
        ffi_check_ptr!(tensor_b, length, f32, f64::NAN);
        if length == 0 { return 0.0; }
        
        let slice_a = unsafe { std::slice::from_raw_parts(tensor_a, length) };
        let slice_b = unsafe { std::slice::from_raw_parts(tensor_b, length) };
        
        let mut sum: f64 = 0.0;
        let mut c: f64 = 0.0;
        
        for i in 0..length {
            let va = slice_a[i] as f64;
            let vb = slice_b[i] as f64;
            if !va.is_finite() || !vb.is_finite() { return f64::NAN; }
            
            let y = (va * vb) - black_box(c);
            let t = sum + y;
            c = black_box((t - sum) - y);
            sum = t;
        }
        sum
    });
    result.unwrap_or(f64::NAN)
}

#[no_mangle]
pub extern "C" fn check_hamming_weight(tensor: *const u64, length: usize) -> i64 {
    let result = panic::catch_unwind(|| {
        ffi_check_ptr!(tensor, length, u64, -1_i64);
        if length == 0 { return 0; }
        let slice = unsafe { std::slice::from_raw_parts(tensor, length) };
        
        let mut total: u64 = 0;
        for &w in slice {
            total += w.count_ones() as u64;
        }
        total as i64
    });
    result.unwrap_or(-1)
}

#[no_mangle]
pub extern "C" fn check_hamming_distance(tensor_a: *const u64, tensor_b: *const u64, length: usize) -> i64 {
    let result = panic::catch_unwind(|| {
        ffi_check_ptr!(tensor_a, length, u64, -1_i64);
        ffi_check_ptr!(tensor_b, length, u64, -1_i64);
        if length == 0 { return 0; }
        let slice_a = unsafe { std::slice::from_raw_parts(tensor_a, length) };
        let slice_b = unsafe { std::slice::from_raw_parts(tensor_b, length) };
        
        let mut total: u64 = 0;
        for i in 0..length {
            total += (slice_a[i] ^ slice_b[i]).count_ones() as u64;
        }
        total as i64
    });
    result.unwrap_or(-1)
}
