import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

final _baseScheme = ColorScheme.fromSeed(seedColor: const Color(0xFF5C6DF4));

ThemeData get appTheme => ThemeData(
      colorScheme: _baseScheme.copyWith(
        surface: Colors.white.withOpacity(0.05), // Для карточек
      ),
      useMaterial3: true,
      textTheme: GoogleFonts.rubikTextTheme(),
      scaffoldBackgroundColor: const Color(0xFF0D1117),
      appBarTheme: AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        surfaceTintColor: Colors.transparent,
        titleTextStyle: GoogleFonts.rubik(
          fontSize: 20,
          fontWeight: FontWeight.w700,
          color: Colors.white,
        ),
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: Colors.white.withOpacity(0.08),
        indicatorColor: Colors.white.withOpacity(0.14),
        elevation: 0,
        labelBehavior: NavigationDestinationLabelBehavior.onlyShowSelected,
      ),
      // CardThemeData теперь необязателен, т.к. используется surface из colorScheme
      cardTheme: CardThemeData(
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      ),
    );