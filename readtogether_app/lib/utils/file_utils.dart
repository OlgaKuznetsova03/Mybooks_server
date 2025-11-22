String? sanitizeFileName(String? original) {
  final trimmed = original?.trim() ?? '';
  if (trimmed.isEmpty) {
    return null;
  }
  final sanitized = trimmed.replaceAll(RegExp(r'[\\/:*?"<>|]'), '_');
  return sanitized.isEmpty ? null : sanitized;
}

String buildFallbackName({String prefix = 'upload', String? fallbackExtension}) {
  final ext = fallbackExtension?.trim();
  if (ext == null || ext.isEmpty) {
    return prefix;
  }
  final sanitizedExt = ext.replaceAll(RegExp(r'[^A-Za-z0-9]'), '');
  if (sanitizedExt.isEmpty) {
    return prefix;
  }
  return '$prefix.$sanitizedExt';
}