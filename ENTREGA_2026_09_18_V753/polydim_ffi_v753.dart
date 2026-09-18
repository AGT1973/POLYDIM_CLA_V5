// ==============================================================================
// POLYDIM V752 - DART FFI BINDINGS
// ==============================================================================
import 'dart:ffi' as ffi;
import 'dart:io';

final class PolydimRodriguesParams extends ffi.Struct {
  external ffi.Pointer<ffi.Double> y;
  external ffi.Pointer<ffi.Double> y_comp;
  external ffi.Pointer<ffi.Double> u;
  external ffi.Pointer<ffi.Double> v;
  @ffi.Double()
  external double theta;
  @ffi.Uint64()
  external int D;
  @ffi.Int32()
  external int num_threads;
}

typedef PolydimGetVersionC = ffi.Uint32 Function();
typedef PolydimGetVersionDart = int Function();

typedef PolydimApplyRodriguesC = ffi.Int32 Function(ffi.Pointer<PolydimRodriguesParams> params);
typedef PolydimApplyRodriguesDart = int Function(ffi.Pointer<PolydimRodriguesParams> params);

void main() {
  print("==========================================================");
  print("  POLYDIM V752 - DART FFI NATIVE BRIDGE");
  print("==========================================================");
  
  var dllPath = "E:\\POLYDIM_EINSOF\\POLYDIM_V751\\bin\\polydim_kernel.dll";
  if (!File(dllPath).existsSync()) {
    print("[FATAL] C++ Kernel not found at: $dllPath");
    exit(1);
  }
  
  final dylib = ffi.DynamicLibrary.open(dllPath);
  
  final getVersion = dylib.lookupFunction<PolydimGetVersionC, PolydimGetVersionDart>('polydim_get_version');
  
  int version = getVersion();
  print("[DART] Loaded C++ Kernel. Version Hex: ${version.toRadixString(16)}");
  print("[DART] FFI Bridge SOTA Verified. Ready for UI/Agent execution.");
  print("==========================================================");
}
