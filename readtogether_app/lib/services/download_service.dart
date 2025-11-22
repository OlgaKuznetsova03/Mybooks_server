import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import '../utils/file_utils.dart';

class DownloadService {
  final HttpClient _httpClient = HttpClient();

  Future<File> downloadPdf(Uri uri, Map<String, String> cookies) async {
    final request = await _httpClient.getUrl(uri);
    if (cookies.isNotEmpty) {
      request.headers.set(
        HttpHeaders.cookieHeader,
        cookies.entries.map((e) => '${e.key}=${e.value}').join('; '),
      );
    }
    final response = await request.close();
    if (response.statusCode != HttpStatus.ok) {
      throw HttpException('Код ответа: ${response.statusCode}');
    }
    final bytes = await consolidateHttpClientResponseBytes(response);
    final targetDir = await _resolveDownloadsDirectory();
    final fileName = _downloadFileName(uri);
    final file = File('${targetDir.path}/$fileName');
    await file.create(recursive: true);
    await file.writeAsBytes(bytes, flush: true);
    return file;
  }

  Future<Directory> _resolveDownloadsDirectory() async {
    if (!kIsWeb && (Platform.isMacOS || Platform.isWindows || Platform.isLinux)) {
      final downloads = await getDownloadsDirectory();
      if (downloads != null) {
        return downloads;
      }
    }
    return getApplicationDocumentsDirectory();
  }

  String _downloadFileName(Uri uri) {
    final rawName =
        uri.pathSegments.isNotEmpty ? uri.pathSegments.last : 'document.pdf';
    final sanitized = sanitizeFileName(rawName) ?? 'document.pdf';
    if (sanitized.toLowerCase().endsWith('.pdf')) {
      return sanitized;
    }
    return '$sanitized.pdf';
  }

  void dispose() {
    _httpClient.close(force: true);
  }
}