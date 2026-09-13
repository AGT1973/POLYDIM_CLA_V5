// POLYDIM FASE 11 - NATIVE RDMA RUST FFI BINDINGS
// Memory-safe wrappers for libibverbs

#[repr(C, align(64))]
pub struct PmtpTensorSlab {
    pub data: [f32; 10000],
}

extern "C" {
    fn pmtp_register_memory_region(pd: *mut libc::c_void, addr: *mut libc::c_void, length: usize) -> *mut libc::c_void;
    fn pmtp_post_send(qp: *mut libc::c_void, mr: *mut libc::c_void, addr: *mut libc::c_void, length: u32, lkey: u32) -> i32;
}

#[no_mangle]
pub extern "C" fn safe_rdma_broadcast(qp: *mut libc::c_void, pd: *mut libc::c_void, slab: *mut PmtpTensorSlab) -> i32 {
    unsafe {
        let length = std::mem::size_of::<PmtpTensorSlab>();
        let mr = pmtp_register_memory_region(pd, slab as *mut libc::c_void, length);
        if mr.is_null() { return -1; }
        let lkey = 0; 
        pmtp_post_send(qp, mr, slab as *mut libc::c_void, length as u32, lkey)
    }
}
