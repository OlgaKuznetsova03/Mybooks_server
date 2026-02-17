import 'package:flutter/material.dart';

import '../../core/repositories/read_together_repository.dart';
import '../books/presentation/books_page.dart';
import '../home/presentation/home_page.dart';
import '../stats/presentation/stats_page.dart';

class MainShellPage extends StatefulWidget {
  const MainShellPage({super.key});

  @override
  State<MainShellPage> createState() => _MainShellPageState();
}

class _MainShellPageState extends State<MainShellPage> {
  int _index = 0;
  final _repository = ReadTogetherRepository();

  @override
  Widget build(BuildContext context) {
    final pages = [
      HomePage(repository: _repository),
      BooksPage(repository: _repository),
      StatsPage(repository: _repository),
    ];

    return Scaffold(
      body: pages[_index],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), label: 'Главная'),
          NavigationDestination(icon: Icon(Icons.menu_book_outlined), label: 'Книги'),
          NavigationDestination(icon: Icon(Icons.bar_chart_outlined), label: 'Статистика'),
        ],
        onDestinationSelected: (value) => setState(() => _index = value),
      ),
    );
  }
}