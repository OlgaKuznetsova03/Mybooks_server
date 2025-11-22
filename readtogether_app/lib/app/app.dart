import 'package:flutter/material.dart';

import '../features/web_view/web_view_page.dart';
import '../services/connectivity_service.dart';
import 'theme.dart';

class ReadTogetherApp extends StatelessWidget {
  const ReadTogetherApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Калейдоскоп книг',
      theme: appTheme,
      debugShowCheckedModeBanner: false,
      home: const KaleidoscopeHome(),
    );
  }
}

class KaleidoscopeHome extends StatefulWidget {
  const KaleidoscopeHome({super.key});

  @override
  State<KaleidoscopeHome> createState() => _KaleidoscopeHomeState();
}

class _KaleidoscopeHomeState extends State<KaleidoscopeHome> {
  final ConnectivityService _connectivityService = ConnectivityService();

  @override
  void initState() {
    super.initState();
    _connectivityService.init();
  }

  @override
  void dispose() {
    _connectivityService.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<bool>(
      valueListenable: _connectivityService.isOnlineNotifier,
      builder: (context, isOnline, child) {
        return MainWebViewPage(onlineNotifier: _connectivityService.isOnlineNotifier);
      },
    );
  }
}