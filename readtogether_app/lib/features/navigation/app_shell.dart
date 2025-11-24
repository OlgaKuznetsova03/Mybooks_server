import 'package:flutter/material.dart';

import '../../services/connectivity_service.dart';
import '../web_view/web_view_page.dart';
import 'modern_pages.dart';

class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  final ConnectivityService _connectivityService = ConnectivityService();
  final List<_AppDestination> _destinations = const [
    _AppDestination(
      title: 'Главная',
      icon: Icons.auto_awesome,
      accent: Color(0xFF8CFFEC),
      page: HomeExperiencePage(),
    ),
    _AppDestination(
      title: 'Книги',
      icon: Icons.menu_book_rounded,
      accent: Color(0xFF7DA2FF),
      page: BooksExperiencePage(),
    ),
    _AppDestination(
      title: 'Читаю сейчас',
      icon: Icons.bolt,
      accent: Color(0xFFFFD166),
      page: ReadingNowPage(),
    ),
    _AppDestination(
      title: 'Домашняя библиотека',
      icon: Icons.home_rounded,
      accent: Color(0xFF6EE7B7),
      page: HomeLibraryPage(),
    ),
    _AppDestination(
      title: 'Совместные чтения',
      icon: Icons.handshake,
      accent: Color(0xFFFF9BC1),
      page: CoReadingPage(),
    ),
    _AppDestination(
      title: 'Марафоны',
      icon: Icons.flag_rounded,
      accent: Color(0xFFB28DFF),
      page: MarathonsPage(),
    ),
    _AppDestination(
      title: 'Игры',
      icon: Icons.videogame_asset,
      accent: Color(0xFF96E8FF),
      page: GamesPage(),
    ),
    _AppDestination(
      title: 'Отзывы и рейтинг',
      icon: Icons.star_rounded,
      accent: Color(0xFFFFD080),
      page: ReviewsPage(),
    ),
    _AppDestination(
      title: 'Сотрудничество',
      icon: Icons.groups_rounded,
      accent: Color(0xFF7CFFB2),
      page: CollaborationPage(),
    ),
    _AppDestination(
      title: 'Блогерский хаб',
      icon: Icons.mic_external_on,
      accent: Color(0xFF9AE6FF),
      page: BloggerHubPage(),
    ),
    _AppDestination(
      title: 'Уведомления',
      icon: Icons.notifications_active_rounded,
      accent: Color(0xFFFF9F80),
      page: NotificationsPage(),
    ),
    _AppDestination(
      title: 'Премиум',
      icon: Icons.workspace_premium_rounded,
      accent: Color(0xFFF6C2FF),
      page: PremiumPage(),
    ),
  ];

  int _selectedIndex = 0;

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
    final destination = _destinations[_selectedIndex];

    return AnimatedContainer(
      duration: const Duration(milliseconds: 450),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            const Color(0xFF0D1117),
            const Color(0xFF0D1117).withOpacity(0.4),
            destination.accent.withOpacity(0.1),
          ],
        ),
      ),
      child: Scaffold(
        backgroundColor: Colors.transparent,
        appBar: AppBar(
          titleSpacing: 24,
          title: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(destination.title),
              ValueListenableBuilder<bool>(
                valueListenable: _connectivityService.isOnlineNotifier,
                builder: (_, isOnline, __) => AnimatedSwitcher(
                  duration: const Duration(milliseconds: 300),
                  child: Text(
                    isOnline ? 'Онлайн' : 'Офлайн — доступен автономный режим',
                    key: ValueKey(isOnline),
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: isOnline ? Colors.white70 : Colors.orangeAccent,
                        ),
                  ),
                ),
              ),
            ],
          ),
          actions: [
            IconButton(
              tooltip: 'Полный функционал',
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => MainWebViewPage(
                    onlineNotifier: _connectivityService.isOnlineNotifier,
                  ),
                ),
              ),
              icon: const Icon(Icons.open_in_new),
            ),
            const SizedBox(width: 12),
          ],
        ),
        body: SafeArea(
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 400),
            switchInCurve: Curves.easeOutCubic,
            switchOutCurve: Curves.easeInCubic,
            child: IndexedStack(
              key: ValueKey(destination.title),
              index: _selectedIndex,
              children: _destinations.map((dest) {
                return DecoratedBox(
                  decoration: const BoxDecoration(),
                  child: dest.page,
                );
              }).toList(),
            ),
          ),
        ),
        bottomNavigationBar: NavigationBar(
          selectedIndex: _selectedIndex,
          onDestinationSelected: (value) {
            setState(() => _selectedIndex = value);
          },
          destinations: _destinations
              .map(
                (dest) => NavigationDestination(
                  icon: Icon(dest.icon),
                  label: dest.title,
                ),
              )
              .toList(),
        ),
        floatingActionButton: FloatingActionButton.extended(
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => MainWebViewPage(
                onlineNotifier: _connectivityService.isOnlineNotifier,
              ),
            ),
          ),
          backgroundColor: destination.accent,
          icon: const Icon(Icons.explore),
          label: const Text('Открыть расширенный режим'),
        ),
      ),
    );
  }
}

class _AppDestination {
  const _AppDestination({
    required this.title,
    required this.icon,
    required this.accent,
    required this.page,
  });

  final String title;
  final IconData icon;
  final Color accent;
  final Widget page;
}