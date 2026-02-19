import '../models/feed_models.dart';
import '../network/api_client.dart';

class ReadTogetherRepository {
  ReadTogetherRepository({ApiClient? apiClient}) : _apiClient = apiClient ?? ApiClient();

  final ApiClient _apiClient;

  Future<HomePayload> fetchHome() async {
    final json = await _fetchHomeData();
    final hero = json['hero'] as Map<String, dynamic>? ?? const {};

    final readingItems = (json['reading_items'] as List<dynamic>? ?? const [])
        .map(_asMap)
        .whereType<Map<String, dynamic>>()
        .map(CurrentBook.fromShelfItem)
        .toList();

    final currentBook = readingItems.isNotEmpty
        ? readingItems.first
        : const CurrentBook(
            title: 'Нет активной книги',
            author: 'Добавьте книгу в полку «Читаю»',
            progress: 0,
            coverUrl: '',
            totalPages: 0,
          );

    final marathons = (json['active_marathons'] as List<dynamic>? ?? const [])
        .map(_asMap)
        .whereType<Map<String, dynamic>>()
        .map(MarathonItem.fromApi)
        .toList();

    final readingMetricsJson = json['reading_metrics'];

    return HomePayload(
      headline: _asString(hero['headline'], fallback: 'Калейдоскоп книг'),
      subtitle: _asString(hero['subtitle'], fallback: 'Ваши активности и рекомендации'),
      greeting: _asString(hero['greeting']),
      currentBook: currentBook,
      currentReading: readingItems,
      readingFeed: (json['active_clubs'] as List<dynamic>? ?? const [])
          .map(_asMap)
          .whereType<Map<String, dynamic>>()
          .map(ReadingUpdate.fromClub)
          .toList(),
      authorOffers: const [],
      bloggerOffers: const [],
      marathons: marathons,
      readingMetrics: readingMetricsJson is Map<String, dynamic> ? ReadingMetrics.fromJson(readingMetricsJson) : null,
    );
  }

  Future<Map<String, dynamic>> _fetchHomeData() async {
    try {
      return await _apiClient.getJson('/home/');
    } catch (_) {
      final clubs = await _apiClient.getList('/reading-clubs/');
      final marathons = await _apiClient.getList('/marathons/');

      return {
        'hero': {
          'headline': 'Калейдоскоп книг',
          'subtitle': 'Сообщества, марафоны и личные подборки в одном экране.',
          'greeting': null,
        },
        'active_clubs': clubs,
        'active_marathons': marathons,
        'reading_items': const <dynamic>[],
        'reading_metrics': null,
      };
    }
  }

  Future<List<BookItem>> fetchBooks({String query = ''}) async {
    final encodedQuery = Uri.encodeQueryComponent(query.trim());
    final path = encodedQuery.isEmpty ? '/books/' : '/books/?search=$encodedQuery';
    final data = await _apiClient.getList(path);
    return data.map((e) => BookItem.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<void> addBook({required String title, required String author, required String genre}) {
    return _apiClient.postJson(
      '/books/',
      {
        'title': title,
        'author_names': [author],
        'genre_names': [genre],
      },
    );
  }

  Future<void> submitBookSuggestion({required String title, required String author, required String genre}) {
    return addBook(title: title, author: author, genre: genre);
  }

  Future<StatsPayload> fetchStats() async {
    final json = await _apiClient.getJson('/stats/');
    return StatsPayload(
      booksPerMonth: (json['books_per_month'] as List<dynamic>? ?? const []).map((e) => (e as num).toInt()).toList(),
      challengeProgress: (json['challenge_progress'] as num?)?.toInt() ?? 0,
      readingCalendar: (json['calendar'] as List<dynamic>? ?? const []).map((e) => (e as num).toInt()).toList(),
    );
  }
}

String _asString(Object? value, {String fallback = ''}) {
  if (value is String && value.isNotEmpty) {
    return value;
  }
  return fallback;
}

Map<String, dynamic>? _asMap(Object? value) {
  if (value is Map<String, dynamic>) {
    return value;
  }
  if (value is Map) {
    return value.map((key, val) => MapEntry('$key', val));
  }
  return null;
}