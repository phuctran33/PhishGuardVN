import 'dart:convert';
import 'package:flutter/services.dart';
import 'student_adapter.dart';

const _prefix = 'packages/student_android_qa/assets/';

Future<Map<String, dynamic>> bundledStudentReference() async => jsonDecode(
        await rootBundle.loadString('${_prefix}live_python_reference.json'))
    as Map<String, dynamic>;

Future<LoadedStudent> loadBundledStudent({String mode = 'kd_mixed'}) async {
  final lock =
      jsonDecode(await rootBundle.loadString('${_prefix}student_lock.json'))
          as Map<String, dynamic>;
  return loadStudent((name) async {
    final data = await rootBundle.load('$_prefix$name');
    return data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
  }, lock, mode: mode);
}
