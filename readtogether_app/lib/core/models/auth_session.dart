class AuthSession {
  const AuthSession({
    required this.token,
    required this.userId,
    required this.username,
    required this.email,
  });

  final String token;
  final int userId;
  final String username;
  final String email;

  Map<String, String> toStorageMap() {
    return {
      'token': token,
      'user_id': userId.toString(),
      'username': username,
      'email': email,
    };
  }

  static AuthSession? fromStorageMap(Map<String, String> map) {
    final token = map['token'] ?? '';
    final userIdRaw = map['user_id'] ?? '';
    final username = map['username'] ?? '';
    final email = map['email'] ?? '';
    final userId = int.tryParse(userIdRaw);

    if (token.isEmpty || username.isEmpty || userId == null) {
      return null;
    }

    return AuthSession(
      token: token,
      userId: userId,
      username: username,
      email: email,
    );
  }
}