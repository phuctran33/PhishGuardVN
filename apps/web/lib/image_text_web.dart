import 'dart:js_interop';
import 'dart:typed_data';

@JS('phishGuardReadImage')
external _OcrJob _start(JSUint8Array bytes);

extension type _OcrJob(JSObject value) implements JSObject {
  external JSPromise<JSString> get result;
  external void cancel();
}

Future<String> recognizeImageText(
  Uint8List bytes,
  void Function(void Function()) onCancel,
) async {
  final job = _start(bytes.toJS);
  onCancel(() => job.cancel());
  return (await job.result.toDart).toDart;
}
