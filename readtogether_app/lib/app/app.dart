import 'package:flutter/material.dart';

import '../core/auth/auth_state.dart';
import '../core/models/auth_session.dart';
import '../core/repositories/auth_repository.dart';
import '../features/auth/presentation/auth_page.dart';
import '../features/shell/main_shell_page.dart';
import 'theme.dart';

class ReadTogetherApp extends StatefulWidget {
  const ReadTogetherApp({super.key});

  @override
  State<ReadTogetherApp> createState() => _ReadTogetherAppState();
}

class _ReadTogetherAppState extends State<ReadTogetherApp> {
  final _authRepository = AuthRepository();
  AuthSession? _session;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _restoreSession();
  }

  Future<void> _restoreSession() async {
    final restored = await _authRepository.restoreSession();
    if (!mounted) {
      return;
    }
    setState(() {
      _session = restored;
      _loading = false;
      AuthState.instance.token = restored?.token;
    });
  }

  Future<void> _logout() async {
    await _authRepository.logout();
    if (!mounted) {
      return;
    }
    setState(() {
      _session = null;
      AuthState.instance.token = null;
    });
  }

  void _onAuthenticated(AuthSession session) {
    setState(() {
      _session = session;
      AuthState.instance.token = session.token;
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ReadTogether',
      theme: appTheme,
      debugShowCheckedModeBanner: false,
      home: _loading
          ? const Scaffold(body: Center(child: CircularProgressIndicator()))
          : _session == null
              ? AuthPage(
                  authRepository: _authRepository,
                  onAuthenticated: _onAuthenticated,
                )
              : MainShellPage(
                  session: _session!,
                  onLogout: _logout,
                ),
    );
  }
}