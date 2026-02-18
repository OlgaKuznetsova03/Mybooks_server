import 'package:flutter/material.dart';

import '../../../core/models/auth_session.dart';
import '../../../core/repositories/auth_repository.dart';

class AuthPage extends StatefulWidget {
  const AuthPage({
    super.key,
    required this.authRepository,
    required this.onAuthenticated,
  });

  final AuthRepository authRepository;
  final ValueChanged<AuthSession> onAuthenticated;

  @override
  State<AuthPage> createState() => _AuthPageState();
}

class _AuthPageState extends State<AuthPage> with SingleTickerProviderStateMixin {
  late final TabController _tabController;

  final _loginFormKey = GlobalKey<FormState>();
  final _signupFormKey = GlobalKey<FormState>();

  final _loginController = TextEditingController();
  final _passwordController = TextEditingController();

  final _signupUsernameController = TextEditingController();
  final _signupEmailController = TextEditingController();
  final _signupPasswordController = TextEditingController();

  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    _loginController.dispose();
    _passwordController.dispose();
    _signupUsernameController.dispose();
    _signupEmailController.dispose();
    _signupPasswordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.menu_book_rounded, size: 64),
                  const SizedBox(height: 12),
                  Text('ReadTogether', style: Theme.of(context).textTheme.headlineMedium),
                  const SizedBox(height: 24),
                  TabBar(
                    controller: _tabController,
                    tabs: const [
                      Tab(text: 'Вход'),
                      Tab(text: 'Регистрация'),
                    ],
                  ),
                  const SizedBox(height: 12),
                  SizedBox(
                    height: 320,
                    child: TabBarView(
                      controller: _tabController,
                      children: [
                        _buildLoginForm(),
                        _buildSignupForm(),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildLoginForm() {
    return Form(
      key: _loginFormKey,
      child: Column(
        children: [
          TextFormField(
            controller: _loginController,
            decoration: const InputDecoration(labelText: 'Логин'),
            validator: (v) => (v == null || v.trim().isEmpty) ? 'Введите логин' : null,
          ),
          const SizedBox(height: 10),
          TextFormField(
            controller: _passwordController,
            decoration: const InputDecoration(labelText: 'Пароль'),
            obscureText: true,
            validator: (v) => (v == null || v.isEmpty) ? 'Введите пароль' : null,
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: _loading ? null : _handleLogin,
              child: Text(_loading ? 'Проверяем...' : 'Войти'),
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'Можно войти тем же логином и паролем, что и на сайте.',
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  Widget _buildSignupForm() {
    return Form(
      key: _signupFormKey,
      child: Column(
        children: [
          TextFormField(
            controller: _signupUsernameController,
            decoration: const InputDecoration(labelText: 'Имя пользователя'),
            validator: (v) => (v == null || v.trim().isEmpty) ? 'Введите имя пользователя' : null,
          ),
          const SizedBox(height: 10),
          TextFormField(
            controller: _signupEmailController,
            decoration: const InputDecoration(labelText: 'Email'),
            keyboardType: TextInputType.emailAddress,
            validator: (v) {
              final value = v?.trim() ?? '';
              if (value.isEmpty) {
                return 'Введите email';
              }
              if (!value.contains('@')) {
                return 'Некорректный email';
              }
              return null;
            },
          ),
          const SizedBox(height: 10),
          TextFormField(
            controller: _signupPasswordController,
            decoration: const InputDecoration(labelText: 'Пароль'),
            obscureText: true,
            validator: (v) {
              final value = v ?? '';
              if (value.length < 8) {
                return 'Минимум 8 символов';
              }
              return null;
            },
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: _loading ? null : _handleSignup,
              child: Text(_loading ? 'Создаём...' : 'Создать аккаунт'),
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'После регистрации эти данные подойдут и для сайта.',
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  Future<void> _handleLogin() async {
    if (!_loginFormKey.currentState!.validate()) {
      return;
    }
    await _runAuth(
      () => widget.authRepository.login(
        login: _loginController.text,
        password: _passwordController.text,
      ),
    );
  }

  Future<void> _handleSignup() async {
    if (!_signupFormKey.currentState!.validate()) {
      return;
    }
    await _runAuth(
      () => widget.authRepository.signup(
        username: _signupUsernameController.text,
        email: _signupEmailController.text,
        password: _signupPasswordController.text,
      ),
    );
  }

  Future<void> _runAuth(Future<AuthSession> Function() action) async {
    setState(() => _loading = true);
    try {
      final session = await action();
      if (!mounted) {
        return;
      }
      widget.onAuthenticated(session);
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Ошибка: $error')),
      );
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }
}