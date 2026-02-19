import 'package:shared_preferences/shared_preferences.dart';

import '../models/auth_session.dart';
import '../network/api_client.dart';

class AuthRepository {
  AuthRepository({ApiClient? apiClient}) : _apiClient = apiClient ?? ApiClient();

  static const _tokenKey = 'auth_token';
  static const _userIdKey = 'auth_user_id';
  static const _usernameKey = 'auth_username';
  static const _emailKey = 'auth_email';

  final ApiClient _apiClient;

  Future<AuthSession?> restoreSession() async {
    final prefs = await SharedPreferences.getInstance();
    final map = <String, String>{
      'token': prefs.getString(_tokenKey) ?? '',
      'user_id': prefs.getString(_userIdKey) ?? '',
      'username': prefs.getString(_usernameKey) ?? '',
      'email': prefs.getString(_emailKey) ?? '',
    };
    return AuthSession.fromStorageMap(map);
  }

  Future<AuthSession> login({required String login, required String password}) async {
    final json = await _apiClient.postAndReadJson(
      '/auth/login/',
      {
        'login': login.trim(),
        'password': password,
      },
    );
    final session = _sessionFromResponse(json);
    await _persistSession(session);
    return session;
  }

  Future<AuthSession> signup({
    required String username,
    required String email,
    required String password,
  }) async {
    final json = await _apiClient.postAndReadJson(
      '/auth/signup/',
      {
        'username': username.trim(),
        'email': email.trim().toLowerCase(),
        'password': password,
      },
    );
    final session = _sessionFromResponse(json);
    await _persistSession(session);
    return session;
  }

  Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
    await prefs.remove(_userIdKey);
    await prefs.remove(_usernameKey);
    await prefs.remove(_emailKey);
  }

  AuthSession _sessionFromResponse(Map<String, dynamic> json) {
    final token = (json['token'] as String?) ?? '';
    final user = json['user'] as Map<String, dynamic>? ?? const {};
    final userId = (user['id'] as num?)?.toInt() ?? -1;
    final username = (user['username'] as String?) ?? '';
    final email = (user['email'] as String?) ?? '';

    if (token.isEmpty || userId <= 0 || username.isEmpty) {
      throw Exception('Некорректный ответ сервера авторизации');
    }

    return AuthSession(token: token, userId: userId, username: username, email: email);
  }

  Future<void> _persistSession(AuthSession session) async {
    final prefs = await SharedPreferences.getInstance();
    final values = session.toStorageMap();
    await prefs.setString(_tokenKey, values['token']!);
    await prefs.setString(_userIdKey, values['user_id']!);
    await prefs.setString(_usernameKey, values['username']!);
    await prefs.setString(_emailKey, values['email']!);
  }
}