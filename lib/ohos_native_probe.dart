import 'dart:ffi';

typedef _NativeProbe = Uint32 Function();
typedef _DartProbe = int Function();

int verifyOhosNativeProbe() {
  final library = DynamicLibrary.open('libqfli_native_probe.so');
  final probe = library.lookupFunction<_NativeProbe, _DartProbe>(
    'qfli_native_probe',
  );
  final value = probe();
  if (value != 0x51464c49) {
    throw StateError('Unexpected native ABI probe value: $value');
  }
  return value;
}
