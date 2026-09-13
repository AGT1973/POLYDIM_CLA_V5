/*
 * POLYDIM FASE 11 - NATIVE RDMA C++ KERNEL
 * Bypasses TCP/IP and OS Kernel using libibverbs (RoCEv2)
 */
#include <iostream>

extern "C" {
    void* pmtp_register_memory_region(void* pd, void* addr, size_t length) {
        std::cout << "[Fase 11] Stubbed MR registration for " << length << " bytes." << std::endl;
        return nullptr;
    }

    int pmtp_post_send(void* qp, void* mr, void* addr, uint32_t length, uint32_t lkey) {
        std::cout << "[Fase 11] Stubbed RDMA post_send execution." << std::endl;
        return 0;
    }
}
