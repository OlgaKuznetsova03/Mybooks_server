import 'package:flutter/material.dart';

import '../features/navigation/app_shell.dart';
import 'theme.dart';

class ReadTogetherApp extends StatelessWidget {
  const ReadTogetherApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Калейдоскоп книг',
      theme: appTheme,
      debugShowCheckedModeBanner: false,
      home: const AppShell(),
    );
  }
}