import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:file_picker/file_picker.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';
import 'package:webview_flutter_wkwebview/webview_flutter_wkwebview.dart';

import 'services/reward_ads_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ReadTogetherApp());
}

class ReadTogetherApp extends StatelessWidget {
  const ReadTogetherApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Калейдоскоп книг',
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF40535c),
        useMaterial3: true,
      ),
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
  final ValueNotifier<bool> _isOnlineNotifier = ValueNotifier(true);
  final Connectivity _connectivity = Connectivity();

  MainWebViewPage? _webViewPage;
  int _currentIndex = 0;
  StreamSubscription<dynamic>? _connectivitySubscription;

  @override
  void initState() {
    super.initState();
    _webViewPage = MainWebViewPage(onlineNotifier: _isOnlineNotifier);
    _initConnectivity();
  }

  Future<void> _initConnectivity() async {
    try {
      final result = await _connectivity.checkConnectivity();
      _handleConnectivityResult(result);
    } catch (_) {}

    _connectivitySubscription =
        _connectivity.onConnectivityChanged.listen(_handleConnectivityResult);
  }

  void _handleConnectivityResult(dynamic result) {
    bool hasConnection = true;
    if (result is ConnectivityResult) {
      hasConnection = result != ConnectivityResult.none;
    } else if (result is List<ConnectivityResult>) {
      hasConnection = result.any((e) => e != ConnectivityResult.none);
    }
    if (_isOnlineNotifier.value != hasConnection) {
      _isOnlineNotifier.value = hasConnection;
    }
  }

  @override
  void dispose() {
    _connectivitySubscription?.cancel();
    _isOnlineNotifier.dispose();
    super.dispose();
  }

  void _setIndex(int index) {
    if (_currentIndex == index) return;
    setState(() => _currentIndex = index);
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<bool>(
      valueListenable: _isOnlineNotifier,
      builder: (context, isOnline, _) {
        final pages = [
          HomeDashboard(
            isOnline: isOnline,
            onOpenMarathons: () => _setIndex(2),
          ),
          LocalLibraryTab(isOnline: isOnline),
          _webViewPage!,
          ProfileTab(
            isOnline: isOnline,
            onOpenWebProfile: () => _setIndex(2),
          ),
        ];

        return Scaffold(
          body: SafeArea(
            child: IndexedStack(
              index: _currentIndex,
              children: pages,
            ),
          ),
          bottomNavigationBar: NavigationBar(
            selectedIndex: _currentIndex,
            onDestinationSelected: _setIndex,
            destinations: const [
              NavigationDestination(
                icon: Icon(Icons.spa_outlined),
                selectedIcon: Icon(Icons.spa),
                label: 'Главная',
              ),
              NavigationDestination(
                icon: Icon(Icons.book_outlined),
                selectedIcon: Icon(Icons.book),
                label: 'Мои книги',
              ),
              NavigationDestination(
                icon: Icon(Icons.emoji_events_outlined),
                selectedIcon: Icon(Icons.emoji_events),
                label: 'Марафоны',
              ),
              NavigationDestination(
                icon: Icon(Icons.person_outline),
                selectedIcon: Icon(Icons.person),
                label: 'Профиль',
              ),
            ],
          ),
        );
      },
    );
  }
}

class HomeDashboard extends StatelessWidget {
  const HomeDashboard({
    super.key,
    required this.isOnline,
    required this.onOpenMarathons,
  });

  final bool isOnline;
  final VoidCallback onOpenMarathons;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _HeroHeader(isOnline: isOnline, onOpenMarathons: onOpenMarathons),
        const SizedBox(height: 16),
        if (!isOnline) const OfflineIllustration(),
        SectionTitle(
          icon: Icons.auto_stories,
          title: 'Рекомендуем прочитать',
          subtitle: 'Сохранено в приложении',
        ),
        const SizedBox(height: 8),
        FutureBuilder<List<RecommendedBook>>(
          future: LocalContentRepository.loadRecommendedBooks(),
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            final books = snapshot.data ?? [];
            if (books.isEmpty) {
              return const Text('Добавляем подборку...');
            }
            return Column(
              children: books
                  .map(
                    (book) => Card(
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: ListTile(
                        contentPadding: const EdgeInsets.all(16),
                        leading: CircleAvatar(
                          backgroundColor: theme.colorScheme.primaryContainer,
                          child: Text(
                            book.title.isNotEmpty
                                ? book.title.substring(0, 1)
                                : '?',
                            style: theme.textTheme.titleMedium,
                          ),
                        ),
                        title: Text(book.title),
                        subtitle: Text('${book.author}\n${book.description}'),
                        isThreeLine: true,
                        trailing: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const Icon(Icons.timer_outlined, size: 18),
                            Text(book.duration),
                          ],
                        ),
                      ),
                    ),
                  )
                  .toList(),
            );
          },
        ),
        const SizedBox(height: 24),
        SectionTitle(
          icon: Icons.emoji_events,
          title: 'Марафоны недели',
          subtitle: 'Задания доступны онлайн и офлайн',
        ),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            gradient: LinearGradient(
              colors: [
                Theme.of(context).colorScheme.primaryContainer,
                Theme.of(context).colorScheme.secondaryContainer,
              ],
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Зимний марафон «Калейдоскоп чувств»',
                style: theme.textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              Text(
                'Получайте задания и отслеживайте прогресс прямо в приложении. '
                'Если интернет пропал — последние шаги сохранены локально.',
                style: theme.textTheme.bodyMedium,
              ),
              const SizedBox(height: 12),
              FilledButton.icon(
                onPressed: onOpenMarathons,
                icon: const Icon(Icons.play_arrow),
                label: const Text('Открыть марафоны'),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _HeroHeader extends StatelessWidget {
  const _HeroHeader({
    required this.isOnline,
    required this.onOpenMarathons,
  });

  final bool isOnline;
  final VoidCallback onOpenMarathons;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(28),
        gradient: LinearGradient(
          colors: [
            theme.colorScheme.primary,
            theme.colorScheme.secondary,
          ],
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const CircleAvatar(
                radius: 28,
                backgroundColor: Colors.white,
                child: Icon(Icons.menu_book, color: Colors.black87, size: 32),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Text(
                  'Калейдоскоп книг',
                  style: theme.textTheme.headlineSmall?.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              Chip(
                label: Text(isOnline ? 'Онлайн' : 'Оффлайн'),
                backgroundColor: Colors.white.withOpacity(0.2),
                labelStyle: const TextStyle(color: Colors.white),
              ),
            ],
          ),
          const SizedBox(height: 24),
          const BookFlipAnimation(),
          const SizedBox(height: 24),
          Text(
            'Участвуйте в марафонах, собирайте любимые книги и читайте новости '
            'проекта в одном приложении.',
            style: theme.textTheme.bodyLarge?.copyWith(color: Colors.white),
          ),
          const SizedBox(height: 16),
          FilledButton.tonalIcon(
            onPressed: onOpenMarathons,
            icon: const Icon(Icons.explore),
            label: const Text('Начать путешествие'),
          ),
        ],
      ),
    );
  }
}

class LocalLibraryTab extends StatefulWidget {
  const LocalLibraryTab({super.key, required this.isOnline});

  final bool isOnline;

  @override
  State<LocalLibraryTab> createState() => _LocalLibraryTabState();
}

class _LocalLibraryTabState extends State<LocalLibraryTab> {
  late Future<List<RecommendedBook>> _booksFuture;
  final Set<String> _favoriteIds = {'artists_way', 'winter_tales'};

  @override
  void initState() {
    super.initState();
    _booksFuture = LocalContentRepository.loadRecommendedBooks();
  }

  void _toggleFavorite(String id) {
    setState(() {
      if (!_favoriteIds.remove(id)) {
        _favoriteIds.add(id);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return FutureBuilder<List<RecommendedBook>>(
      future: _booksFuture,
      builder: (context, snapshot) {
        final books = snapshot.data ?? [];
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            SectionTitle(
              icon: Icons.favorite,
              title: 'Избранное',
              subtitle: 'Доступно офлайн',
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: _favoriteIds
                  .map(
                    (id) => FilterChip(
                      selected: true,
                      label: Text(
                        books.firstWhere(
                          (b) => b.id == id,
                          orElse: () =>
                              RecommendedBook(id: id, title: id, author: '', description: '', duration: ''),
                        ).title,
                      ),
                      onSelected: (_) => _toggleFavorite(id),
                    ),
                  )
                  .toList(),
            ),
            const SizedBox(height: 16),
            SectionTitle(
              icon: Icons.library_books,
              title: 'Последние книги',
              subtitle: widget.isOnline
                  ? 'Синхронизировано с сайтом'
                  : 'Показаны сохранённые подборки',
            ),
            const SizedBox(height: 8),
            if (snapshot.connectionState == ConnectionState.waiting)
              const Center(child: CircularProgressIndicator())
            else ...books.map(
                (book) => Card(
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(18),
                    side: BorderSide(
                      color: theme.colorScheme.outlineVariant,
                    ),
                  ),
                  child: ListTile(
                    title: Text(book.title),
                    subtitle: Text(book.description),
                    trailing: IconButton(
                      icon: Icon(
                        _favoriteIds.contains(book.id)
                            ? Icons.bookmark
                            : Icons.bookmark_outline,
                      ),
                      onPressed: () => _toggleFavorite(book.id),
                    ),
                  ),
                ),
              ),
            const SizedBox(height: 24),
            Card(
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(24),
              ),
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Локальные заметки',
                      style: theme.textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Добавьте короткие заметки о текущем чтении. Записи хранятся '
                      'на устройстве и помогут продолжить чтение без интернета.',
                      style: theme.textTheme.bodyMedium,
                    ),
                    const SizedBox(height: 12),
                    FilledButton.tonalIcon(
                      onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text('Редактор заметок появится в следующем обновлении.'),
                        ),
                      ),
                      icon: const Icon(Icons.edit_note),
                      label: const Text('Написать заметку'),
                    ),
                  ],
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

class ProfileTab extends StatefulWidget {
  const ProfileTab({
    super.key,
    required this.isOnline,
    required this.onOpenWebProfile,
  });

  final bool isOnline;
  final VoidCallback onOpenWebProfile;

  @override
  State<ProfileTab> createState() => _ProfileTabState();
}

class _ProfileTabState extends State<ProfileTab> {
  late Future<String> _aboutFuture;
  late Future<List<ProjectNews>> _newsFuture;

  @override
  void initState() {
    super.initState();
    _aboutFuture = LocalContentRepository.loadAboutProject();
    _newsFuture = LocalContentRepository.loadNews();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        SectionTitle(
          icon: Icons.person,
          title: 'Профиль участника',
          subtitle: widget.isOnline
              ? 'Вы в сети — данные синхронизируются'
              : 'Вы офлайн — показываем сохранённую информацию',
        ),
        const SizedBox(height: 12),
        FutureBuilder<String>(
          future: _aboutFuture,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            return Card(
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(24),
              ),
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('О проекте', style: theme.textTheme.titleMedium),
                    const SizedBox(height: 12),
                    Text(snapshot.data ?? ''),
                  ],
                ),
              ),
            );
          },
        ),
        const SizedBox(height: 16),
        SectionTitle(
          icon: Icons.campaign,
          title: 'Новости проекта',
          subtitle: 'Обновляется при подключении к интернету',
        ),
        const SizedBox(height: 8),
        FutureBuilder<List<ProjectNews>>(
          future: _newsFuture,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            final news = snapshot.data ?? [];
            return Column(
              children: news
                  .map(
                    (item) => Card(
                      child: ListTile(
                        leading: CircleAvatar(
                          child: Text(
                            item.tag.isNotEmpty
                                ? item.tag.substring(0, 1).toUpperCase()
                                : '•',
                          ),
                        ),
                        title: Text(item.title),
                        subtitle: Text('${item.dateLabel}\n${item.summary}'),
                        isThreeLine: true,
                      ),
                    ),
                  )
                  .toList(),
            );
          },
        ),
        const SizedBox(height: 16),
        FilledButton.icon(
          onPressed: widget.onOpenWebProfile,
          icon: const Icon(Icons.open_in_new),
          label: const Text('Открыть профиль в веб-вкладке'),
        ),
      ],
    );
  }
}

class SectionTitle extends StatelessWidget {
  const SectionTitle({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      children: [
        Icon(icon, color: theme.colorScheme.primary),
        const SizedBox(width: 8),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: theme.textTheme.titleMedium),
              Text(
                subtitle,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class OfflineIllustration extends StatelessWidget {
  const OfflineIllustration({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      color: theme.colorScheme.surfaceTint.withOpacity(0.1),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Row(
          children: [
            const Icon(Icons.wifi_off, size: 40),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: const [
                  Text(
                    'Проверьте интернет-соединение. Ваши последние книги сохранены офлайн.',
                  ),
                  SizedBox(height: 8),
                  Text('Мы покажем свежие новости, как только появится связь.'),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class BookFlipAnimation extends StatefulWidget {
  const BookFlipAnimation({super.key});

  @override
  State<BookFlipAnimation> createState() => _BookFlipAnimationState();
}

class _BookFlipAnimationState extends State<BookFlipAnimation>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 4),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        final angle = (_controller.value * math.pi) % (2 * math.pi);
        return Transform(
          alignment: Alignment.center,
          transform: Matrix4.identity()
            ..setEntry(3, 2, 0.001)
            ..rotateY(angle),
          child: child,
        );
      },
      child: Container(
        height: 90,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(20),
          color: Colors.white.withOpacity(0.2),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 24),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: const [
            Text(
              'Перелистываем идеи',
              style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
            ),
            Icon(Icons.menu_book, color: Colors.white, size: 32),
          ],
        ),
      ),
    );
  }
}

class RecommendedBook {
  const RecommendedBook({
    required this.id,
    required this.title,
    required this.author,
    required this.description,
    required this.duration,
  });

  final String id;
  final String title;
  final String author;
  final String description;
  final String duration;

  factory RecommendedBook.fromJson(Map<String, dynamic> json) {
    return RecommendedBook(
      id: json['id'] as String,
      title: json['title'] as String,
      author: json['author'] as String,
      description: json['description'] as String,
      duration: json['duration'] as String,
    );
  }
}

class ProjectNews {
  const ProjectNews({
    required this.title,
    required this.dateLabel,
    required this.summary,
    required this.tag,
  });

  final String title;
  final String dateLabel;
  final String summary;
  final String tag;

  factory ProjectNews.fromJson(Map<String, dynamic> json) {
    return ProjectNews(
      title: json['title'] as String,
      dateLabel: json['date'] as String,
      summary: json['summary'] as String,
      tag: json['tag'] as String,
    );
  }
}

class LocalContentRepository {
  static Future<List<RecommendedBook>> loadRecommendedBooks() async {
    try {
      final raw = await rootBundle.loadString('assets/data/recommended_books.json');
      final List<dynamic> data = jsonDecode(raw) as List<dynamic>;
      return data
          .map((item) => RecommendedBook.fromJson(item as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return const [];
    }
  }

  static Future<List<ProjectNews>> loadNews() async {
    try {
      final raw = await rootBundle.loadString('assets/data/news.json');
      final List<dynamic> data = jsonDecode(raw) as List<dynamic>;
      return data
          .map((item) => ProjectNews.fromJson(item as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return const [];
    }
  }

  static Future<String> loadAboutProject() async {
    try {
      return await rootBundle.loadString('assets/data/about_project.md');
    } catch (_) {
      return 'Мы развиваем культуру чтения и создаём безопасное пространство для общения.';
    }
  }
}

class MainWebViewPage extends StatefulWidget {
  const MainWebViewPage({super.key, this.onlineNotifier});

  final ValueListenable<bool>? onlineNotifier;

  @override
  State<MainWebViewPage> createState() => _MainWebViewPageState();
}

class _MainWebViewPageState extends State<MainWebViewPage> {
  static const String _fallbackSiteUrl = 'https://kalejdoskopknig.ru/';
  static const String _defaultSiteUrl = String.fromEnvironment(
    'MYBOOKS_SITE_URL',
    defaultValue: _fallbackSiteUrl,
  );
  static const String _defaultClientHeader = String.fromEnvironment(
    'MYBOOKS_APP_HEADER',
    defaultValue: 'X-MyBooks-Client',
  );
  static const String _defaultClientId = String.fromEnvironment(
    'MYBOOKS_APP_CLIENT_ID',
    defaultValue: 'mybooks-flutter',
  );

  late final WebViewController _controller;
  late final Uri _siteOrigin;
  late final String _startUrl;
  late final RewardAdsService _rewardAdsService;
  ValueListenable<bool>? _connectivityListenable;

  bool _loading = true;
  bool _rewardLoading = false;
  bool _webViewError = false;
  bool _isOffline = false;

  @override
  void initState() {
    super.initState();

    _startUrl = _prepareStartUrl(_defaultSiteUrl);
    _siteOrigin = Uri.parse(_startUrl);
    _rewardAdsService = RewardAdsService(
      siteOrigin: _siteOrigin,
      clientHeader: _defaultClientHeader,
      clientId: _defaultClientId,
    );
    _attachConnectivity(widget.onlineNotifier);

    final PlatformWebViewControllerCreationParams params;
    if (WebViewPlatform.instance is WebKitWebViewPlatform) {
      params = WebKitWebViewControllerCreationParams(
        allowsInlineMediaPlayback: true,
      );
    } else {
      params = const PlatformWebViewControllerCreationParams();
    }

    final controller = WebViewController.fromPlatformCreationParams(params)
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0x00000000))
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageStarted: (_) => setState(() {
                _loading = true;
                _webViewError = false;
              }),
          onPageFinished: (_) => setState(() {
                _loading = false;
                _webViewError = false;
              }),
          onWebResourceError: (_) => setState(() {
                _loading = false;
                _webViewError = true;
              }),
          onNavigationRequest: _handleNavigationRequest,
        ),
      );

    if (controller.platform is AndroidWebViewController) {
      final android = controller.platform as AndroidWebViewController;
      android
        ..setMediaPlaybackRequiresUserGesture(false)
        ..setOnShowFileSelector(_onShowFileSelector);
    }

    _controller = controller;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _checkTermsAndLoad();
    });
  }

  @override
  void didUpdateWidget(covariant MainWebViewPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.onlineNotifier != widget.onlineNotifier) {
      _attachConnectivity(widget.onlineNotifier);
    }
  }

  @override
  void dispose() {
    _detachConnectivity();
    _rewardAdsService.dispose();
    super.dispose();
  }

  void _attachConnectivity(ValueListenable<bool>? notifier) {
    _detachConnectivity();
    _connectivityListenable = notifier;
    if (notifier != null) {
      _isOffline = !notifier.value;
      notifier.addListener(_handleConnectivityChange);
    }
  }

  void _detachConnectivity() {
    _connectivityListenable?.removeListener(_handleConnectivityChange);
    _connectivityListenable = null;
  }

  void _handleConnectivityChange() {
    final notifier = _connectivityListenable;
    if (notifier == null || !mounted) return;
    final offline = !notifier.value;
    if (offline == _isOffline) return;
    setState(() => _isOffline = offline);
    if (!offline && _webViewError) {
      _controller.reload();
    }
  }

  NavigationDecision _handleNavigationRequest(NavigationRequest request) {
    final uri = Uri.tryParse(request.url);
    if (uri == null) {
      return NavigationDecision.navigate;
    }

    if (_isSameOrigin(uri)) {
      if (_shouldInterceptDownload(uri)) {
        unawaited(_startDownload(uri));
        return NavigationDecision.prevent;
      }
      return NavigationDecision.navigate;
    }

    if (uri.scheme == 'http' || uri.scheme == 'https') {
      return NavigationDecision.prevent;
    }

    return NavigationDecision.navigate;
  }

  bool _isSameOrigin(Uri uri) {
    if (uri.host.isEmpty) {
      return true;
    }

    if (uri.host.toLowerCase() != _siteOrigin.host.toLowerCase()) {
      return false;
    }

    if (_siteOrigin.hasPort && uri.port != _siteOrigin.port) {
      return false;
    }

    return true;
  }

  String _prepareStartUrl(String rawUrl) {
    final trimmed = rawUrl.trim();
    if (trimmed.isEmpty) {
      return _fallbackSiteUrl;
    }

    try {
      final parsed = Uri.parse(trimmed);
      if (!parsed.hasScheme || parsed.host.isEmpty) {
        return _fallbackSiteUrl;
      }

      final normalisedPath = parsed.path.isEmpty
          ? '/'
          : (parsed.path.endsWith('/') ? parsed.path : '${parsed.path}/');

      return parsed
          .replace(path: normalisedPath, queryParameters: const {}, fragment: null)
          .toString();
    } catch (_) {
      return _fallbackSiteUrl;
    }
  }

  Future<List<String>> _onShowFileSelector(FileSelectorParams params) async {
    FileType type = FileType.any;
    List<String>? customExt;

    if (params.acceptTypes.isNotEmpty) {
      final accepts = params.acceptTypes.map((e) => e.toLowerCase()).toList();
      if (accepts.any((e) => e.contains('image'))) {
        type = FileType.image;
      } else if (accepts.any((e) => e.contains('video'))) {
        type = FileType.video;
      } else if (accepts.any((e) => e.contains('audio'))) {
        type = FileType.audio;
      } else if (accepts.any((e) => e.contains('.'))) {
        type = FileType.custom;
        customExt = accepts
            .expand((e) => e.split(','))
            .map((e) => e.replaceAll('.', '').trim())
            .where((e) => e.isNotEmpty)
            .toList();
      }
    }

    final result = await FilePicker.platform.pickFiles(
      allowMultiple: _shouldAllowMultiple(params),
      type: type,
      allowedExtensions: customExt,
      withData: true,
    );

    if (result == null) return <String>[];

    final List<String> paths = [];
    final tempDir = await getTemporaryDirectory();
    for (final f in result.files) {
      if (f.path != null && f.path!.isNotEmpty) {
        paths.add(_normalizeForWebView(f.path!));
        continue;
      }

      final targetFile = await _createTempFile(tempDir.path, f.name, f.extension);

      if (f.bytes != null) {
        await targetFile.writeAsBytes(f.bytes!, flush: true);
        paths.add(_normalizeForWebView(targetFile.path));
        continue;
      }

      final stream = f.readStream;
      if (stream != null) {
        final sink = targetFile.openWrite();
        await stream.pipe(sink);
        await sink.flush();
        await sink.close();
        paths.add(_normalizeForWebView(targetFile.path));
      }
    }
    return paths;
  }

  String _normalizeForWebView(String rawPath) {
    final trimmed = rawPath.trim();
    if (trimmed.isEmpty) {
      return trimmed;
    }

    if (trimmed.contains('://')) {
      return trimmed;
    }

    return Uri.file(trimmed).toString();
  }

  Future<File> _createTempFile(
    String dirPath,
    String? originalName,
    String? fallbackExtension,
  ) async {
    final sanitizedName = _sanitizeFileName(originalName);
    final generatedName =
        sanitizedName ?? _buildFallbackName(fallbackExtension: fallbackExtension);
    final uniqueName = '${DateTime.now().microsecondsSinceEpoch}_${generatedName}';
    final file = File('$dirPath/$uniqueName');
    if (!await file.exists()) {
      await file.create(recursive: true);
    }
    return file;
  }

  String? _sanitizeFileName(String? original) {
    final trimmed = original?.trim() ?? '';
    if (trimmed.isEmpty) {
      return null;
    }
    final sanitized = trimmed.replaceAll(RegExp(r'[\\/:*?"<>|]'), '_');
    return sanitized.isEmpty ? null : sanitized;
  }

  String _buildFallbackName({String prefix = 'upload', String? fallbackExtension}) {
    final ext = fallbackExtension?.trim();
    if (ext == null || ext.isEmpty) {
      return prefix;
    }
    final sanitizedExt = ext.replaceAll(RegExp(r'[^A-Za-z0-9]'), '');
    if (sanitizedExt.isEmpty) {
      return prefix;
    }
    return '$prefix.$sanitizedExt';
  }

  bool _shouldAllowMultiple(FileSelectorParams params) {
    final dynamic dynamicParams = params;

    try {
      final value = dynamicParams.allowMultiple;
      if (value is bool) {
        return value;
      }
    } catch (_) {}

    try {
      final mode = dynamicParams.mode;
      if (mode != null) {
        final modeString = mode.toString().toLowerCase();
        if (modeString.contains('multiple')) {
          return true;
        }
      }
    } catch (_) {}

    return false;
  }

  Future<bool> _handleBack() async {
    if (await _controller.canGoBack()) {
      _controller.goBack();
      return false;
    }
    return true;
  }

  Future<Map<String, String>> _collectCookies() async {
    try {
      final rawResult = await _controller.runJavaScriptReturningResult('document.cookie');
      if (rawResult == null) {
        return {};
      }

      String? cookieString;
      if (rawResult is String) {
        cookieString = rawResult;
      } else {
        cookieString = rawResult.toString();
      }

      if (cookieString == null) {
        return {};
      }

      final trimmed = cookieString.trim();
      if (trimmed.isEmpty || trimmed == 'null') {
        return {};
      }

      final sanitized = trimmed.startsWith('"') && trimmed.endsWith('"')
          ? trimmed.substring(1, trimmed.length - 1)
          : trimmed;

      final Map<String, String> cookies = {};
      for (final entry in sanitized.split(';')) {
        final parts = entry.split('=');
        if (parts.isEmpty) {
          continue;
        }
        final name = parts.first.trim();
        if (name.isEmpty) {
          continue;
        }
        final value = parts.skip(1).join('=').trim();
        cookies[name] = value;
      }
      return cookies;
    } catch (error) {
      debugPrint('Не удалось получить cookies: $error');
      return {};
    }
  }

  Future<void> _checkTermsAndLoad() async {
    final accepted = await _ensureTermsAccepted();
    if (!mounted) return;
    if (accepted) {
      _controller.loadRequest(Uri.parse(_startUrl));
    }
  }

  Future<bool> _ensureTermsAccepted() async {
    try {
      final marker = await _termsAcceptanceMarker();
      if (await marker.exists()) {
        return true;
      }
    } catch (error) {
      debugPrint('Не удалось проверить соглашение с правилами: $error');
      return true;
    }

    while (mounted) {
      final accepted = await showDialog<bool>(
        context: context,
        barrierDismissible: false,
        builder: (context) {
          final theme = Theme.of(context);
          return AlertDialog(
            title: const Text('Согласие с правилами'),
            content: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    'Перед использованием приложения подтвердите, что вы ознакомились '
                    'и согласны с правилами сервиса «Калейдоскоп книг».',
                    style: theme.textTheme.bodyMedium,
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'Полные правила доступны на сайте:',
                    style: theme.textTheme.bodySmall,
                  ),
                  const SizedBox(height: 8),
                  SelectableText(
                    '${_siteOrigin.scheme}://${_siteOrigin.host}/rules/',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.primary,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Нажимая «Принимаю правила», вы подтверждаете, что ознакомились '
                    'с документом и обязуетесь соблюдать требования сервиса.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: const Text('Закрыть приложение'),
              ),
              FilledButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('Принимаю правила'),
              ),
            ],
          );
        },
      );

      if (accepted == true) {
        try {
          final marker = await _termsAcceptanceMarker();
          if (!await marker.exists()) {
            await marker.create(recursive: true);
          }
          await marker.writeAsString(DateTime.now().toIso8601String());
        } catch (error) {
          debugPrint('Не удалось сохранить подтверждение правил: $error');
        }
        return true;
      }

      if (accepted == false) {
        await _closeApplication();
        return false;
      }
    }

    return false;
  }

  Future<File> _termsAcceptanceMarker() async {
    final directory = await getApplicationSupportDirectory();
    return File('${directory.path}/mybooks_terms_v1.txt');
  }

  Future<void> _closeApplication() async {
    if (Platform.isAndroid) {
      await SystemNavigator.pop();
    } else {
      exit(0);
    }
  }

  bool _shouldInterceptDownload(Uri uri) {
    final path = uri.path;
    if (path == '/accounts/me/print/monthly/' || path == '/accounts/me/print/monthly') {
      return true;
    }

    final segments = uri.pathSegments;
    if (segments.length >= 3 && segments.first == 'books' && segments.last == 'print-review') {
      return true;
    }

    return false;
  }

  Future<void> _startDownload(Uri uri) async {
    if (!mounted) return;
    
    await showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Row(
            children: [
              Icon(Icons.download, color: Colors.deepPurple),
              SizedBox(width: 8),
              Text('Скачивание файлов'),
            ],
          ),
          content: const Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Скачивание файлов доступно только в веб-версии сайта.',
                style: TextStyle(fontSize: 16),
              ),
              SizedBox(height: 16),
              Text(
                'Чтобы скачать файлы:',
                style: TextStyle(fontWeight: FontWeight.w500),
              ),
              SizedBox(height: 8),
              Text('1. Откройте браузер на вашем устройстве'),
              Text('2. Перейдите на сайт kalejdoskopknig.ru'),
              Text('3. Войдите в свой аккаунт'),
              Text('4. Скачайте нужные файлы'),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Закрыть'),
            ),
            FilledButton(
              onPressed: () {
                Navigator.of(context).pop();
                _openInBrowser();
              },
              child: const Text('Открыть в браузере'),
            ),
          ],
        );
      },
    );
  }

  Future<void> _openInBrowser() async {
    try {
      final url = _startUrl;
      if (await canLaunchUrl(Uri.parse(url))) {
        await launchUrl(
          Uri.parse(url),
          mode: LaunchMode.externalApplication,
        );
      } else {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Не удалось открыть браузер')),
        );
      }
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Ошибка при открытии браузера: $error')),
      );
    }
  }

  void _reloadWebView() {
    if (!mounted) return;
    setState(() => _webViewError = false);
    _controller.reload();
  }

  Widget _buildStatusOverlay({
    required IconData icon,
    required String title,
    required String description,
    VoidCallback? onPressed,
    String actionLabel = 'Повторить',
  }) {
    final theme = Theme.of(context);
    return Container(
      color: theme.colorScheme.surface.withOpacity(0.98),
      padding: const EdgeInsets.all(24),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 360),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 48, color: theme.colorScheme.primary),
              const SizedBox(height: 16),
              Text(
                title,
                style: theme.textTheme.titleLarge,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              Text(
                description,
                style: theme.textTheme.bodyMedium,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: onPressed,
                child: Text(actionLabel),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _openRewardPanel() async {
    if (_rewardLoading) return;

    setState(() => _rewardLoading = true);
    try {
      final cookies = await _collectCookies();
      final config = await _rewardAdsService.fetchConfig(cookies: cookies);

      if (!config.isReady) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Рекламный модуль временно отключён.'),
          ),
        );
        return;
      }

      if (!mounted) return;
      final result = await showModalBottomSheet<RewardAdClaimResult>(
        context: context,
        isScrollControlled: true,
        builder: (context) => RewardAdSheet(
          config: config,
          service: _rewardAdsService,
          cookieProvider: _collectCookies,
        ),
      );

      if (result != null && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Начислено ${result.coinsAwarded} монет.',
            ),
          ),
        );
      }
    } on RewardAdsException catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.message)),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Не удалось открыть панель рекламы: $error')),
      );
    } finally {
      if (mounted) {
        setState(() => _rewardLoading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvoked: (bool didPop) async {
        if (!didPop) {
          final shouldPop = await _handleBack();
          if (shouldPop && mounted) {
            Navigator.of(context).pop();
          }
        }
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Мир в книгах'),
          backgroundColor: Colors.white,
          foregroundColor: const Color.fromARGB(255,174,181,184),
          elevation: 4,
          actions: [
            _rewardLoading
                ? const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 16.0),
                    child: SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    ),
                  )
                : Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8.0),
                    child: TextButton.icon(
                      onPressed: _openRewardPanel,
                      style: TextButton.styleFrom(
                        foregroundColor: Colors.white,
                        backgroundColor: const Color.fromARGB(255, 140, 143, 144),
                      ),
                      icon: const Icon(Icons.play_circle_outline, size: 18),
                      label: const Text('20 монет'),
                    ),
                  ),
          ],
        ),
        body: Stack(
          children: [
            WebViewWidget(controller: _controller),
            if (_loading) const Center(child: CircularProgressIndicator()),
            if (_webViewError && !_isOffline)
              Positioned.fill(
                child: _buildStatusOverlay(
                  icon: Icons.cloud_off,
                  title: 'Не удалось загрузить сайт',
                  description:
                      'Сервис временно недоступен. Попробуйте обновить страницу или вернитесь позже.',
                  onPressed: _reloadWebView,
                  actionLabel: 'Перезагрузить вкладку',
                ),
              ),
            if (_isOffline)
              Positioned.fill(
                child: _buildStatusOverlay(
                  icon: Icons.wifi_off,
                  title: 'Вы офлайн',
                  description:
                      'Проверьте интернет-соединение. Ваши последние книги и подборки уже сохранены в приложении.',
                  onPressed: _reloadWebView,
                  actionLabel: 'Проверить снова',
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class RewardAdSheet extends StatefulWidget {
  const RewardAdSheet({
    super.key,
    required this.config,
    required this.service,
    required this.cookieProvider,
  });

  final RewardAdConfig config;
  final RewardAdsService service;
  final Future<Map<String, String>> Function() cookieProvider;

  @override
  State<RewardAdSheet> createState() => _RewardAdSheetState();
}

class _RewardAdSheetState extends State<RewardAdSheet> {
  bool _claiming = false;
  RewardAdsException? _error;

  Future<void> _claimReward() async {
    setState(() {
      _claiming = true;
      _error = null;
    });

    try {
      final cookies = await widget.cookieProvider();
      final result = await widget.service.claimReward(
        config: widget.config,
        cookies: cookies,
      );
      if (!mounted) return;
      Navigator.of(context).pop(result);
    } on RewardAdsException catch (error) {
      if (!mounted) return;
      setState(() => _error = error);
    } catch (error) {
      if (!mounted) return;
      setState(
        () => _error = RewardAdsException(
          'Не удалось начислить монеты: $error',
          code: RewardAdsError.network,
        ),
      );
    } finally {
      if (mounted) {
        setState(() => _claiming = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: 24,
          right: 24,
          top: 24,
          bottom: MediaQuery.of(context).viewInsets.bottom + 24,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Рекламная награда', style: theme.textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(
              'Яндекс · ${widget.config.rewardAmount} ${widget.config.currency}',
              style: theme.textTheme.bodyMedium,
            ),
            const SizedBox(height: 8),
            Text(
              'Просмотрите рекламный ролик и подтвердите получение награды, '
              'чтобы монеты были начислены на счёт.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(
                _error!.message,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.error,
                ),
              ),
            ],
            const SizedBox(height: 16),
            if (kDebugMode)
              FilledButton.icon(
                onPressed: _claiming ? null : _claimReward,
                icon: _claiming
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Icon(Icons.play_circle_fill),
                label: const Text('Симулировать получение награды'),
              )
            else
              Text(
                'В релизной сборке интегрируйте SDK рекламы и вызывайте '
                'RewardAdsService.claimReward(...) после события rewarded. '
                'Эта панель служит для проверки конфигурации.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            const SizedBox(height: 16),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: _claiming ? null : () => Navigator.of(context).maybePop(),
                child: const Text('Закрыть'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}