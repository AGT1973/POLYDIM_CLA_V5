cmake_minimum_required(VERSION 3.16)
project(polydim_kernel LANGUAGES C CXX VERSION 7.51.0)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Include directories
include_directories(include)

# Find OpenMP
find_package(OpenMP REQUIRED)

# Source files
set(SOURCES
    src/polydim_kernel.cpp
)

# Build shared library (DLL / .so / .dylib)
add_library(polydim_kernel SHARED ${SOURCES})

target_compile_definitions(polydim_kernel PRIVATE POLYDIM_BUILD_DLL)

# Compiler-specific strict IEEE-754 adherence flags
if(MSVC)
    target_compile_options(polydim_kernel PRIVATE
        /O2
        /fp:precise
        /EHsc
        /W4
    )
else()
    target_compile_options(polydim_kernel PRIVATE
        -O3
        -ffp-contract=off
        -fno-fast-math
        -Wall
        -Wextra
    )
endif()

# Link OpenMP
target_link_libraries(polydim_kernel PRIVATE OpenMP::OpenMP_CXX)

# Set library output directory
set_target_properties(polydim_kernel PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin
    VERSION ${PROJECT_VERSION}
    SOVERSION 7
)
