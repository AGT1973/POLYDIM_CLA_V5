use std::slice;
use std::f64;

#[no_mangle]
pub extern "C" fn cayley_step_global_isometry(
    s_in_ptr: *const f64, v_in_ptr: *const f64,
    s_next_in_ptr: *mut f64, v_next_in_ptr: *mut f64,
    w_scratch_ptr: *mut f64,
    dim: usize, dt: f64
) -> i32 {
    if s_in_ptr.is_null() || v_in_ptr.is_null() || s_next_in_ptr.is_null() || v_next_in_ptr.is_null() || w_scratch_ptr.is_null() {
        return 1; // ERR_NULL
    }
    if dim == 0 { return 2; } // ERR_DIM
    if !(dt > 0.0) || !dt.is_finite() { return 4; } // ERR_DT

    let s_in = unsafe { slice::from_raw_parts(s_in_ptr, dim) };
    let v_in = unsafe { slice::from_raw_parts(v_in_ptr, dim) };
    let s_next = unsafe { slice::from_raw_parts_mut(s_next_in_ptr, dim) };
    let v_next = unsafe { slice::from_raw_parts_mut(v_next_in_ptr, dim) };
    let w_scratch = unsafe { slice::from_raw_parts_mut(w_scratch_ptr, dim) };

    // GS 1
    let mut dot_ss_sum = 0.0; let mut dot_ss_c = 0.0;
    let mut dot_sv_sum = 0.0; let mut dot_sv_c = 0.0;
    for i in 0..dim {
        neumaier_add(&mut dot_ss_sum, &mut dot_ss_c, s_in[i] * s_in[i]);
        neumaier_add(&mut dot_sv_sum, &mut dot_sv_c, s_in[i] * v_in[i]);
    }
    let dot_ss = dot_ss_sum + dot_ss_c;
    let dot_sv = dot_sv_sum + dot_sv_c;
    
    if !(dot_ss >= 1e-14) { return 3; } // ERR_SINGULAR
    let proj1 = dot_sv / dot_ss;

    // GS 2
    let mut dot_sw_sum = 0.0; let mut dot_sw_c = 0.0;
    for i in 0..dim {
        let w1 = v_in[i] - proj1 * s_in[i];
        neumaier_add(&mut dot_sw_sum, &mut dot_sw_c, s_in[i] * w1);
    }
    let dot_sw = dot_sw_sum + dot_sw_c;
    let proj2 = dot_sw / dot_ss;

    // V_tangent & Energy
    let mut w_sq_sum = 0.0; let mut w_sq_c = 0.0;
    for i in 0..dim {
        let vt = (v_in[i] - proj1 * s_in[i]) - proj2 * s_in[i];
        let w = vt * dt;
        w_scratch[i] = w;
        neumaier_add(&mut w_sq_sum, &mut w_sq_c, w * w);
    }
    let total_w_sq = w_sq_sum + w_sq_c;

    // Math Fixes
    let u2_global = total_w_sq / 4.0;
    let denom = 1.0 + u2_global;
    
    let scale_s = (1.0 - u2_global) / denom;
    let scale_w = 1.0 / denom;
    let rot_v_scalar = -(total_w_sq / dt) / denom;
    let rot_v_tangent = ((1.0 - u2_global) / denom) / dt;

    for i in 0..dim {
        let s = s_in[i];
        let w = w_scratch[i];
        s_next[i] = scale_s * s + scale_w * w;
        v_next[i] = rot_v_scalar * s + rot_v_tangent * w;
    }
    0
}

#[inline(always)]
fn neumaier_add(sum: &mut f64, c: &mut f64, val: f64) {
    let t = *sum + val;
    if sum.abs() >= val.abs() {
        *c += (*sum - t) + val;
    } else {
        *c += (val - t) + *sum;
    }
    *sum = t;
}
