import 'package:flutter/material.dart';

import '../../services/api_service.dart';
import 'widgets.dart';

final _palette = <Color>[
  const Color(0xFF7DA2FF),
  const Color(0xFFFFD166),
  const Color(0xFF6EE7B7),
  const Color(0xFFFF9BC1),
  const Color(0xFFB28DFF),
  const Color(0xFF96E8FF),
  const Color(0xFFFFD080),
  const Color(0xFFF6C2FF),
];

String _formatDate(DateTime? value) {
  if (value == null) return '';
  final day = value.day.toString().padLeft(2, '0');
  final month = value.month.toString().padLeft(2, '0');
  return '$day.$month.${value.year}';
}

double _timelineProgress(DateTime? start, DateTime? end) {
  if (start == null || end == null || end.isBefore(start)) return 0;
  final now = DateTime.now();
  if (now.isBefore(start)) return 0;
  if (now.isAfter(end)) return 1;
  final total = end.difference(start).inSeconds;
  if (total <= 0) return 0;
  final passed = now.difference(start).inSeconds;
  return (passed / total).clamp(0, 1).toDouble();
}

class HomeExperiencePage extends StatefulWidget {
  const HomeExperiencePage({super.key});

  @override
  State<HomeExperiencePage> createState() => _HomeExperiencePageState();
}

class _HomeExperiencePageState extends State<HomeExperiencePage> {
  final MobileApiService _api = MobileApiService();
  late final Future<_HomePayload> _future = _load();

  Future<_HomePayload> _load() async {
    final books = await _api.fetchBooks(pageSize: 8);
    final clubs = await _api.fetchReadingClubs(pageSize: 6);
    final marathons = await _api.fetchMarathons(pageSize: 4);
    final featureMap = await _api.fetchFeatureMap();
    return _HomePayload(books: books, clubs: clubs, marathons: marathons, featureMap: featureMap);
  }

  @override
  Widget build(BuildContext context) {
    return _AsyncExperience(
      future: _future,
      builder: (data) => ExperienceLayout(
        title: 'Новый взгляд на чтение',
        subtitle: 'Актуальные подборки из API: книги, клубы, марафоны',
        hero: GlassCard(
          gradient: const [Color(0xFF4F46E5), Color(0xFF7C3AED)],
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Добро пожаловать!'),
              const SizedBox(height: 8),
              Text(
                'Мы показываем живые данные: свежие релизы, активные клубы и статус сервиса.',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.white70),
              ),
              const SizedBox(height: 18),
              Wrap(
                spacing: 12,
                runSpacing: 8,
                children: const [
                  QuickBadge(label: 'Свежие книги'),
                  QuickBadge(label: 'Читательские клубы'),
                  QuickBadge(label: 'Марафоны'),
                ],
              ),
            ],
          ),
        ),
        sections: [
          ExperienceSection(
            title: 'Свежие книги',
            description: 'Показываем последние книги из каталога API.',
            cards: _bookCards(data.books),
          ),
          ExperienceSection(
            title: 'Активные клубы',
            description: 'Клубы с датами и статистикой сообщений.',
            cards: _clubTiles(data.clubs),
          ),
          ExperienceSection(
            title: 'Марафоны',
            description: 'Статус и прогресс по времени проведения.',
            cards: _marathonCards(data.marathons),
          ),
          ExperienceSection(
            title: 'Карта возможностей',
            description: 'Статусы API по картам функций.',
            cards: _featureMapCards(data.featureMap),
          ),
        ],
      ),
    );
  }
}

class BooksExperiencePage extends StatefulWidget {
  const BooksExperiencePage({super.key});

  @override
  State<BooksExperiencePage> createState() => _BooksExperiencePageState();
}

class _BooksExperiencePageState extends State<BooksExperiencePage> {
  final MobileApiService _api = MobileApiService();
  late final Future<List<BookSummary>> _future = _api.fetchBooks(pageSize: 12);
  late final Future<List<ReadingClubSummary>> _clubFuture = _api.fetchReadingClubs(pageSize: 4);

  @override
  Widget build(BuildContext context) {
    return _AsyncExperience(
      future: Future.wait([
        _future,
        _clubFuture,
      ]),
      builder: (payload) {
        final books = payload[0] as List<BookSummary>;
        final clubs = payload[1] as List<ReadingClubSummary>;
        final spotlight = books.take(6).toList();
        final more = books.skip(6).take(6).toList();

        return ExperienceLayout(
          title: 'Книги',
          subtitle: 'Каталог на реальных данных: жанры, авторы, языки',
          hero: GlassCard(
            gradient: const [Color(0xFF2563EB), Color(0xFF38BDF8)],
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Каталог переизобретён'),
                const SizedBox(height: 8),
                Text(
                  'Карточки строятся из API: жанры, аннотации, языки, средний рейтинг.',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.white70),
                ),
                const SizedBox(height: 16),
                Wrap(
                  spacing: 12,
                  runSpacing: 8,
                  children: const [
                    QuickBadge(label: 'Аннотация'),
                    QuickBadge(label: 'Жанры'),
                    QuickBadge(label: 'Авторы'),
                  ],
                ),
              ],
            ),
          ),
          sections: [
            ExperienceSection(
              title: 'Подборки недели',
              description: 'Свежие книги с жанрами и описанием.',
              cards: _bookCards(spotlight),
            ),
            ExperienceSection(
              title: 'Ещё книги',
              description: 'Расширенный список по ответу API.',
              cards: _bookCards(more),
            ),
            ExperienceSection(
              title: 'Клубы вокруг этих книг',
              description: 'Связанные книги и статус клубов.',
              cards: _clubTiles(clubs),
            ),
          ],
        );
      },
    );
  }
}

class ReadingNowPage extends StatefulWidget {
  const ReadingNowPage({super.key});

  @override
  State<ReadingNowPage> createState() => _ReadingNowPageState();
}

class _ReadingNowPageState extends State<ReadingNowPage> {
  final MobileApiService _api = MobileApiService();
  late final Future<List<ReadingClubSummary>> _clubs = _api.fetchReadingClubs(pageSize: 6);
  late final Future<List<ReadingMarathonSummary>> _marathons = _api.fetchMarathons(pageSize: 6);

  @override
  Widget build(BuildContext context) {
    return _AsyncExperience(
      future: Future.wait([
        _clubs,
        _marathons,
      ]),
      builder: (payload) {
        final clubs = payload[0] as List<ReadingClubSummary>;
        final marathons = payload[1] as List<ReadingMarathonSummary>;

        return ExperienceLayout(
          title: 'Читаю сейчас',
          subtitle: 'Фокус на активных клубах и марафонах в реальном времени',
          hero: GlassCard(
            gradient: const [Color(0xFFFB923C), Color(0xFFF97316)],
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Режим концентрации'),
                const SizedBox(height: 10),
                Text(
                  'Используем даты и статус клубов/марафонов вместо заглушек.',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.white70),
                ),
                const SizedBox(height: 14),
                const QuickBadge(label: 'Реальные даты стартов'),
              ],
            ),
          ),
          sections: [
            ExperienceSection(
              title: 'Клубные сессии',
              description: 'Даты, статус и количество сообщений.',
              cards: _clubTiles(clubs),
            ),
            ExperienceSection(
              title: 'Марафоны в работе',
              description: 'Прогресс рассчитывается по времени проведения.',
              cards: _marathonCards(marathons),
            ),
          ],
        );
      },
    );
  }
}

class HomeLibraryPage extends StatefulWidget {
  const HomeLibraryPage({super.key});

  @override
  State<HomeLibraryPage> createState() => _HomeLibraryPageState();
}

class _HomeLibraryPageState extends State<HomeLibraryPage> {
  final MobileApiService _api = MobileApiService();
  late final Future<FeatureMap> _featureMap = _api.fetchFeatureMap();
  late final Future<List<BookSummary>> _books = _api.fetchBooks(pageSize: 6);

  @override
  Widget build(BuildContext context) {
    return _AsyncExperience(
      future: Future.wait([
        _featureMap,
        _books,
      ]),
      builder: (payload) {
        final feature = payload[0] as FeatureMap;
        final books = payload[1] as List<BookSummary>;

        return ExperienceLayout(
          title: 'Домашняя библиотека',
          subtitle: 'Показываем, что доступно через API, и быстрые ссылки на книги',
          hero: GlassCard(
            gradient: const [Color(0xFF22C55E), Color(0xFF14B8A6)],
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Полный контроль'),
                const SizedBox(height: 10),
                Text(
                  'Отображаем реальные эндпоинты и книги, чтобы библиотека была прозрачной.',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.white70),
                ),
                const SizedBox(height: 12),
                const QuickBadge(label: 'API-first'),
              ],
            ),
          ),
          sections: [
            ExperienceSection(
              title: 'Эндпоинты библиотеки',
              description: 'Статусы доступности функций по карте API.',
              cards: _featureMapCards(feature),
            ),
            ExperienceSection(
              title: 'Недавно добавленные книги',
              description: 'Используем свежие книги из каталога.',
              cards: _bookCards(books),
            ),
          ],
        );
      },
    );
  }
}

class CoReadingPage extends StatefulWidget {
  const CoReadingPage({super.key});

  @override
  State<CoReadingPage> createState() => _CoReadingPageState();
}

class _CoReadingPageState extends State<CoReadingPage> {
  final MobileApiService _api = MobileApiService();
  late final Future<List<ReadingClubSummary>> _future = _api.fetchReadingClubs(pageSize: 10);

  @override
  Widget build(BuildContext context) {
    return _AsyncExperience(
      future: _future,
      builder: (clubs) => ExperienceLayout(
        title: 'Совместные чтения',
        subtitle: 'Данные о клубах приходят напрямую из API',
        hero: GlassCard(
          gradient: const [Color(0xFFFF9BC1), Color(0xFFE879F9)],
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Общайтесь и читайте вместе'),
              const SizedBox(height: 8),
              Text(
                'Показываем статус, политику вступления и книгу клуба.',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.white70),
              ),
            ],
          ),
        ),
        sections: [
          ExperienceSection(
            title: 'Клубы',
            description: 'Вся метаинформация доступна без заглушек.',
            cards: _clubTiles(clubs),
          ),
        ],
      ),
    );
  }
}

class MarathonsPage extends StatefulWidget {
  const MarathonsPage({super.key});

  @override
  State<MarathonsPage> createState() => _MarathonsPageState();
}

class _MarathonsPageState extends State<MarathonsPage> {
  final MobileApiService _api = MobileApiService();
  late final Future<List<ReadingMarathonSummary>> _future = _api.fetchMarathons(pageSize: 10);

  @override
  Widget build(BuildContext context) {
    return _AsyncExperience(
      future: _future,
      builder: (marathons) => ExperienceLayout(
        title: 'Марафоны',
        subtitle: 'Живые данные о марафонах: даты, статус, участники',
        hero: GlassCard(
          gradient: const [Color(0xFFB28DFF), Color(0xFF6366F1)],
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Держим темп'),
              const SizedBox(height: 8),
              Text(
                'Прогресс считаем по времени проведения марафона.',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.white70),
              ),
            ],
          ),
        ),
        sections: [
          ExperienceSection(
            title: 'Активные марафоны',
            description: 'Из API без выдуманных данных.',
            cards: _marathonCards(marathons),
          ),
        ],
      ),
    );
  }
}

class GamesPage extends StatefulWidget {
  const GamesPage({super.key});

  @override
  State<GamesPage> createState() => _GamesPageState();
}

class _GamesPageState extends State<GamesPage> {
  final MobileApiService _api = MobileApiService();
  late final Future<FeatureMap> _future = _api.fetchFeatureMap();

  @override
  Widget build(BuildContext context) {
    return _AsyncExperience(
      future: _future,
      builder: (featureMap) => ExperienceLayout(
        title: 'Игры',
        subtitle: 'Показываем статус игровых эндпоинтов',
        hero: GlassCard(
          gradient: const [Color(0xFF96E8FF), Color(0xFF22D3EE)],
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Геймификация'),
              const SizedBox(height: 8),
              Text(
                'Выводим статусы будущих игровых API, без фиктивных карточек.',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.white70),
              ),
            ],
          ),
        ),
        sections: [
          ExperienceSection(
            title: 'Эндпоинты игр',
            description: 'Используем карту возможностей сервиса.',
            cards: _featureGroupCards(featureMap, 'games'),
          ),
        ],
      ),
    );
  }
}

class ReviewsPage extends StatefulWidget {
  const ReviewsPage({super.key});

  @override
  State<ReviewsPage> createState() => _ReviewsPageState();
}

class _ReviewsPageState extends State<ReviewsPage> {
  final MobileApiService _api = MobileApiService();
  late final Future<List<BookSummary>> _future = _api.fetchBooks(pageSize: 10);

  @override
  Widget build(BuildContext context) {
    return _AsyncExperience(
      future: _future,
      builder: (books) {
        final sorted = [...books]..sort((a, b) => (b.averageRating ?? 0).compareTo(a.averageRating ?? 0));
        return ExperienceLayout(
          title: 'Отзывы и рейтинг',
          subtitle: 'Используем реальные рейтинги и данные книг',
          hero: GlassCard(
            gradient: const [Color(0xFFFFD080), Color(0xFFFFA94D)],
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Честные рейтинги'),
                const SizedBox(height: 8),
                Text(
                  'Сортируем книги по среднему рейтингу из API.',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.white70),
                ),
              ],
            ),
          ),
          sections: [
            ExperienceSection(
              title: 'Лидеры рейтинга',
              description: 'Без заглушек: реальные книги и оценки.',
              cards: _ratingCards(sorted),
            ),
          ],
        );
      },
    );
  }
}

class CollaborationPage extends StatefulWidget {
  const CollaborationPage({super.key});

  @override
  State<CollaborationPage> createState() => _CollaborationPageState();
}

class _CollaborationPageState extends State<CollaborationPage> {
  final MobileApiService _api = MobileApiService();
  late final Future<FeatureMap> _future = _api.fetchFeatureMap();

  @override
  Widget build(BuildContext context) {
    return _AsyncExperience(
      future: _future,
      builder: (featureMap) => ExperienceLayout(
        title: 'Сотрудничество',
        subtitle: 'Статусы API для коллабораций и сообществ',
        hero: GlassCard(
          gradient: const [Color(0xFF7CFFB2), Color(0xFF34D399)],
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Работа с партнёрами'),
              const SizedBox(height: 8),
              Text(
                'Отображаем карту возможностей для сообществ.',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.white70),
              ),
            ],
          ),
        ),
        sections: [
          ExperienceSection(
            title: 'Комьюнити',
            description: 'Готовые и планируемые эндпоинты.',
            cards: _featureGroupCards(featureMap, 'communities'),
          ),
        ],
      ),
    );
  }
}

class BloggerHubPage extends StatefulWidget {
  const BloggerHubPage({super.key});

  @override
  State<BloggerHubPage> createState() => _BloggerHubPageState();
}

class _BloggerHubPageState extends State<BloggerHubPage> {
  final MobileApiService _api = MobileApiService();
  late final Future<FeatureMap> _future = _api.fetchFeatureMap();

  @override
  Widget build(BuildContext context) {
    return _AsyncExperience(
      future: _future,
      builder: (featureMap) => ExperienceLayout(
        title: 'Блогерский хаб',
        subtitle: 'Никаких заглушек — только карта возможностей',
        hero: GlassCard(
          gradient: const [Color(0xFF9AE6FF), Color(0xFF38BDF8)],
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Все потоки контента'),
              const SizedBox(height: 8),
              Text(
                'Показываем, что уже доступно и что в планах.',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.white70),
              ),
            ],
          ),
        ),
        sections: [
          ExperienceSection(
            title: 'Возможности',
            description: 'Статусы API для блогеров и аудиторий.',
            cards: _featureMapCards(featureMap),
          ),
        ],
      ),
    );
  }
}

class NotificationsPage extends StatefulWidget {
  const NotificationsPage({super.key});

  @override
  State<NotificationsPage> createState() => _NotificationsPageState();
}

class _NotificationsPageState extends State<NotificationsPage> {
  final MobileApiService _api = MobileApiService();
  late final Future<FeatureMap> _future = _api.fetchFeatureMap();

  @override
  Widget build(BuildContext context) {
    return _AsyncExperience(
      future: _future,
      builder: (featureMap) => ExperienceLayout(
        title: 'Уведомления',
        subtitle: 'Следим за статусом эндпоинтов профиля',
        hero: GlassCard(
          gradient: const [Color(0xFFFF9F80), Color(0xFFF97316)],
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Сигналы и события'),
              const SizedBox(height: 8),
              Text(
                'Используем карту возможностей профиля вместо фиктивных уведомлений.',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.white70),
              ),
            ],
          ),
        ),
        sections: [
          ExperienceSection(
            title: 'Профиль и подписки',
            description: 'Текущее состояние API, чтобы понимать, что доступно.',
            cards: _featureGroupCards(featureMap, 'profile'),
          ),
        ],
      ),
    );
  }
}

class PremiumPage extends StatefulWidget {
  const PremiumPage({super.key});

  @override
  State<PremiumPage> createState() => _PremiumPageState();
}

class _PremiumPageState extends State<PremiumPage> {
  final MobileApiService _api = MobileApiService();
  late final Future<FeatureMap> _future = _api.fetchFeatureMap();
  late final Future<List<BookSummary>> _books = _api.fetchBooks(pageSize: 4);

  @override
  Widget build(BuildContext context) {
    return _AsyncExperience(
      future: Future.wait([
        _future,
        _books,
      ]),
      builder: (payload) {
        final feature = payload[0] as FeatureMap;
        final books = payload[1] as List<BookSummary>;
        return ExperienceLayout(
          title: 'Премиум',
          subtitle: 'Прозрачные статусы подписки и отобранные книги',
          hero: GlassCard(
            gradient: const [Color(0xFFF6C2FF), Color(0xFF7C3AED)],
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Лучшее из каталога'),
                const SizedBox(height: 8),
                Text(
                  'Подсвечиваем доступность подписки и рекомендуем книги из API.',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.white70),
                ),
              ],
            ),
          ),
          sections: [
            ExperienceSection(
              title: 'Статус подписки',
              description: 'Берём информацию из профиля/подписок в feature-map.',
              cards: _featureGroupCards(feature, 'profile'),
            ),
            ExperienceSection(
              title: 'Выбор редакции',
              description: 'Книги без вымышленных данных.',
              cards: _bookCards(books),
            ),
          ],
        );
      },
    );
  }
}

class _HomePayload {
  const _HomePayload({
    required this.books,
    required this.clubs,
    required this.marathons,
    required this.featureMap,
  });

  final List<BookSummary> books;
  final List<ReadingClubSummary> clubs;
  final List<ReadingMarathonSummary> marathons;
  final FeatureMap featureMap;
}

class _AsyncExperience<T> extends StatelessWidget {
  const _AsyncExperience({required this.future, required this.builder});

  final Future<T> future;
  final Widget Function(T data) builder;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<T>(
      future: future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return Center(
            child: InfoCard(
              icon: Icons.error_outline,
              message: 'Не удалось загрузить данные: ${snapshot.error}',
            ),
          );
        }
        final data = snapshot.data;
        if (data == null) {
          return const Center(
            child: InfoCard(
              icon: Icons.hourglass_empty,
              message: 'Данные не найдены',
            ),
          );
        }
        return builder(data);
      },
    );
  }
}

List<Widget> _bookCards(List<BookSummary> books) {
  if (books.isEmpty) {
    return const [
      InfoCard(icon: Icons.menu_book_outlined, message: 'Книги пока не найдены'),
    ];
  }
  final cards = <Widget>[];
  for (var i = 0; i < books.length; i++) {
    final book = books[i];
    final accent = _palette[i % _palette.length];
    cards.add(
      BookCard(
        title: book.title,
        subtitle: book.subtitle,
        tag: book.primaryTag,
        accent: accent,
      ),
    );
  }
  return cards;
}

List<Widget> _clubTiles(List<ReadingClubSummary> clubs) {
  if (clubs.isEmpty) {
    return const [InfoCard(icon: Icons.group_outlined, message: 'Нет активных клубов')];
  }
  return clubs
      .map(
        (club) => CompactListTile(
          icon: Icons.groups,
          title: club.title,
          subtitle: _clubSubtitle(club),
          trailing: Text(club.status, style: const TextStyle(color: Colors.white70)),
        ),
      )
      .toList();
}

String _clubSubtitle(ReadingClubSummary club) {
  final bookTitle = club.book?.title;
  final dateRange = [club.startDate, club.endDate].whereType<DateTime>().toList();
  final dateText = dateRange.isEmpty
      ? ''
      : dateRange.length == 1
          ? _formatDate(dateRange.first)
          : '${_formatDate(dateRange.first)} — ${_formatDate(dateRange.last)}';
  final details = [bookTitle, dateText].where((value) => value != null && value.isNotEmpty).join(' · ');
  if (details.isNotEmpty) return details;
  return club.description.isNotEmpty ? club.description : 'Детали клуба будут позже';
}

List<Widget> _marathonCards(List<ReadingMarathonSummary> marathons) {
  if (marathons.isEmpty) {
    return const [InfoCard(icon: Icons.flag_outlined, message: 'Марафоны пока не найдены')];
  }
  final cards = <Widget>[];
  for (var i = 0; i < marathons.length; i++) {
    final marathon = marathons[i];
    final progress = _timelineProgress(marathon.startDate, marathon.endDate);
    final accent = _palette[(i + 3) % _palette.length];
    final subtitleParts = [
      if (marathon.startDate != null) 'Старт: ${_formatDate(marathon.startDate)}',
      if (marathon.endDate != null) 'Финиш: ${_formatDate(marathon.endDate)}',
      if (marathon.participantCount > 0) 'Участников: ${marathon.participantCount}',
    ];
    cards.add(
      ProgressCard(
        title: marathon.title,
        subtitle: subtitleParts.join(' · '),
        progress: progress,
        accent: accent,
      ),
    );
  }
  return cards;
}

List<Widget> _featureMapCards(FeatureMap featureMap) {
  if (featureMap.groups.isEmpty) {
    return const [InfoCard(icon: Icons.public, message: 'Карта возможностей пустая')];
  }
  return featureMap.groups.expand((group) => _featureGroupCards(featureMap, group.key)).toList();
}

List<Widget> _featureGroupCards(FeatureMap featureMap, String groupKey) {
  final group = featureMap.groups.firstWhere(
    (item) => item.key == groupKey,
    orElse: () => FeatureGroup(key: groupKey, description: 'Нет описания', endpoints: const []),
  );
  if (group.endpoints.isEmpty) {
    return [
      InfoCard(
        icon: Icons.info_outline,
        message: 'Для "$groupKey" пока нет доступных эндпоинтов',
      ),
    ];
  }
  return group.endpoints
      .map(
        (endpoint) => CompactListTile(
          icon: Icons.api,
          title: endpoint.path,
          subtitle: group.description,
          trailing: StatusPill(status: endpoint.status),
        ),
      )
      .toList();
}

List<Widget> _ratingCards(List<BookSummary> books) {
  if (books.isEmpty) {
    return const [InfoCard(icon: Icons.star_border, message: 'Рейтинги появятся позже')];
  }
  final cards = <Widget>[];
  for (var i = 0; i < books.length; i++) {
    final book = books[i];
    final accent = _palette[i % _palette.length];
    final rating = book.averageRating?.toStringAsFixed(1) ?? '—';
    cards.add(
      HighlightCard(
        title: book.title,
        subtitle: book.subtitle,
        accent: accent,
        progress: (book.averageRating ?? 0) / 5,
      ),
    );
    cards.add(
      CompactListTile(
        icon: Icons.star,
        title: 'Оценка: $rating',
        subtitle: book.primaryTag,
      ),
    );
  }
  return cards;
}