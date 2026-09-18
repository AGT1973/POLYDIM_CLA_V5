use std::panic::catch_unwind;
use std::slice;
pub const EPSILON_MACH_F64: f64 = f64::EPSILON; // 2.220446049250313e-16
pub const YCOMP_BUDGET_SAFETY_FACTOR: f64 = 50.0;
pub const DYNAMIC_TOL_SAFETY_FACTOR: f64 = 50.0;
pub enum PolydimStatus {
    Success = 0,
    ErrNullPointer = -1,
    ErrInvalidDimension = -2,
    ErrNanInfDetected = -3,
    ErrNormInvariantViolated = -4,
    ErrYcompBudgetExceeded = -7,
    ErrPanicCaught = -9,
}
pub fn compute_dynamic_tolerance(len: u64) -> f64 {
    DYNAMIC_TOL_SAFETY_FACTOR * (len as f64).sqrt() * EPSILON_MACH_F64
}
pub fn compute_ycomp_budget(len: u64) -> f64 {
    YCOMP_BUDGET_SAFETY_FACTOR * (len as f64) * EPSILON_MACH_F64
}
pub extern "C" fn polydim_rust_verify_unit_norm_invariant_f64(
    tensor_ptr: *const f64,
    len: u64,
    user_tolerance: f64,
) -> i32 {
    let result = catch_unwind(|| {
        if tensor_ptr.is_null() {
            return PolydimStatus::ErrNullPointer as i32;
        }
        if len == 0 || len > ((1u64 << 32)) {
            return PolydimStatus::ErrInvalidDimension as i32;
        }
        let slice = unsafe { slice::from_raw_parts(tensor_ptr, len as usize) };
        let mut sum = 0.0f64;
        let mut c = 0.0f64;
        for &val in slice {
            if !val.is_finite() {
                return PolydimStatus::ErrNanInfDetected as i32;
            }
            let sq = val * val;
            let t = sum + sq;
            if sum.abs() >= sq.abs() {
                c += (sum - t) + sq;
            } else {
                c += (sq - t) + sum;
            }
            sum = t;
        }
        let final_norm_sq = sum + c;
        let tolerance = if user_tolerance > 0.0 {
            user_tolerance
        } else {
            compute_dynamic_tolerance(len)
        };
        if (final_norm_sq - 1.0).abs() <= tolerance {
            PolydimStatus::Success as i32
        } else {
            PolydimStatus::ErrNormInvariantViolated as i32
        }
    });
    match result {
        Ok(code) => code,
        Err(_) => PolydimStatus::ErrPanicCaught as i32,
    }
}
pub extern "C" fn polydim_rust_verify_ycomp_budget_f64(
    y_comp_ptr: *const f64,
    len: u64,
) -> i32 {
    let result = catch_unwind(|| {
        if y_comp_ptr.is_null() {
            return PolydimStatus::ErrNullPointer as i32;
        }
        if len == 0 || len > ((1u64 << 32)) {
            return PolydimStatus::ErrInvalidDimension as i32;
        }
        let slice = unsafe { slice::from_raw_parts(y_comp_ptr, len as usize) };
        let budget = compute_ycomp_budget(len);
        for &val in slice {
            if !val.is_finite() {
                return PolydimStatus::ErrNanInfDetected as i32;
            }
            if val.abs() > budget {
                return PolydimStatus::ErrYcompBudgetExceeded as i32;
            }
        }
        PolydimStatus::Success as i32
    });
    match result {
        Ok(code) => code,
        Err(_) => PolydimStatus::ErrPanicCaught as i32,
    }
}
