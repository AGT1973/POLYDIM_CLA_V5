fn main() {
    cc::Build::new()
        .cpp(true)
        .file("../ENTREGA_DOCENTES_ALUMNOS_V735/kernel_cpp_v735.cpp")
        .flag_if_supported("/O2")
        .flag_if_supported("/openmp")
        .flag_if_supported("-O3")
        .flag_if_supported("-fopenmp")
        .compile("polydim_cpp_kernel");

    println!("cargo:rustc-link-lib=polydim_cpp_kernel");
}
