import 'dart:convert';

import 'package:http/http.dart' as http;

import '../auth/auth_state.dart';

class ApiClient {
  ApiClient({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _baseUrl = baseUrl ??
            const String.fromEnvironment(
              'API_BASE_URL',
              defaultValue: 'https://kalejdoskopknig.ru/api/v1',
            );

  final http.Client _client;
  final String _baseUrl;

  Future<Map<String, dynamic>> getJson(String path) async {
    final response = await _client.get(_buildUri(path), headers: _headers());
    _throwIfNeeded(response);
    return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
  }

  Future<List<dynamic>> getList(String path) async {
    final response = await _client.get(_buildUri(path), headers: _headers());
    _throwIfNeeded(response);
    final decoded = jsonDecode(utf8.decode(response.bodyBytes));
    if (decoded is List<dynamic>) {
      return decoded;
    }
    if (decoded is Map<String, dynamic>) {
      final results = decoded['results'];
      if (results is List<dynamic>) {
        return results;
      }
    }
    throw Exception('Unexpected list response format');
  }

  Future<void> postJson(String path, Map<String, dynamic> body) async {
    final response = await _client.post(
      _buildUri(path),
      headers: _headers(contentTypeJson: true),
      body: jsonEncode(body),
    );
    _throwIfNeeded(response);
  }

  Future<Map<String, dynamic>> postAndReadJson(String path, Map<String, dynamic> body) async {
    final response = await _client.post(
      _buildUri(path),
      headers: _headers(contentTypeJson: true),
      body: jsonEncode(body),
    );
    _throwIfNeeded(response);
    return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
  }

  Uri _buildUri(String path) => Uri.parse('$_baseUrl$path');

  Map<String, String> _headers({bool contentTypeJson = false}) {
    final headers = <String, String>{};
    if (contentTypeJson) {
      headers['Content-Type'] = 'application/json';
    }
    final token = AuthState.instance.token;
    if (token != null && token.isNotEmpty) {
      headers['Authorization'] = 'Token $token';
    }
    return headers;
  }

  void _throwIfNeeded(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return;
    }

    String message = 'Request failed: ${response.statusCode}';
    try {
      final body = jsonDecode(utf8.decode(response.bodyBytes));
      if (body is Map<String, dynamic>) {
        final detail = body['detail'];
        if (detail is String && detail.isNotEmpty) {
          message = detail;
        } else if (body.isNotEmpty) {
          message = body.entries
              .map((entry) => '${entry.key}: ${entry.value}')
              .join('\n');
        }
      }
    } catch (_) {
      // keep fallback message
    }
    throw Exception(message);
  }
}