import 'package:flutter/material.dart';

import '../features/shell/main_shell_page.dart';
import 'theme.dart';

class ReadTogetherApp extends StatelessWidget {
  const ReadTogetherApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ReadTogether',
      theme: appTheme,
      debugShowCheckedModeBanner: false,
      home: const MainShellPage(),
    );
  }
}