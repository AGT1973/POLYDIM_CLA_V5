@echo off
echo =======================================================
echo POLYDIM V707 - LATENT OS COMPILER SCRIPT
echo Compilando FFI C++ y Rust (Zero-Copy PMTP)
echo =======================================================

echo [1/3] Configurando Entorno MSVC...
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"

echo [2/3] Compilando Kernel C++ (Memristor / Isometric Rotors)...
copy pmtp_kernel.cpp.txt pmtp_kernel.cpp
cl.exe /O2 /LD pmtp_kernel.cpp /link /OUT:pmtp_kernel_cpp.dll

echo [3/3] Compilando Kernel Rust (Betti-1 / GKP Snap)...
copy pmtp_kernel.rs.txt pmtp_kernel.rs
rustc --crate-type cdylib -O pmtp_kernel.rs -o pmtp_kernel_rs.dll

echo =======================================================
echo Compilacion Finalizada. DLLs generadas.
echo =======================================================
pause
