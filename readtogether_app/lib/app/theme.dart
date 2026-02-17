import 'package:flutter/material.dart';

ThemeData get appTheme {
  const seed = Color(0xFF3E5B7D);
  return ThemeData(
    colorSchemeSeed: seed,
    useMaterial3: true,
    scaffoldBackgroundColor: const Color(0xFFF6F7FB),
    appBarTheme: const AppBarTheme(centerTitle: false),
    cardTheme: CardThemeData(
      elevation: 0,
      color: Colors.white,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: seed, width: 1.5),
      ),
    ),
  );
}