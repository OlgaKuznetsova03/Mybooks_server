import '../models/feed_models.dart';
import '../network/api_client.dart';

class ReadTogetherRepository {
  ReadTogetherRepository({ApiClient? apiClient}) : _apiClient = apiClient ?? ApiClient();

  final ApiClient _apiClient;

  Future<HomePayload> fetchHome() async {
    final json = await _fetchHomeData();
    final hero = _asMap(json['hero']) ?? const {};

    final readingItems = _parseList<CurrentBook>(
      _pickFirstPopulated(json, const ['reading_items', 'current_reading', 'reading_now']),
      (item) => CurrentBook.fromShelfItem(item),
    );

    final readingFeed = _parseList<ReadingUpdate>(
      _pickFirstPopulated(
        json,
        const ['reading_updates', 'reading_feed', 'active_clubs'],
      ),
      (item) => ReadingUpdate.fromDynamic(item),
    );

    final marathons = _parseList<MarathonItem>(
      _pickFirstPopulated(json, const ['active_marathons', 'marathons']),
      (item) => MarathonItem.fromApi(item),
    );

    final currentReading = readingItems
        .where((book) => book.title.isNotEmpty || book.author.isNotEmpty)
        .toList();

    final currentBook = currentReading.isNotEmpty
        ? currentReading.first
        : const CurrentBook(
            title: 'Нет активной книги',
            author: 'Добавьте книгу в полку «Читаю»',
            progress: 0,
            coverUrl: '',
            totalPages: 0,
          );

    final readingMetricsJson = _pickFirstPopulated(
      json,
      const ['reading_metrics', 'metrics'],
    );

    return HomePayload(
      headline: _asString(hero['headline'], fallback: 'Калейдоскоп книг'),
      subtitle: _asString(hero['subtitle'], fallback: 'Ваши активности и рекомендации'),
      greeting: _asString(hero['greeting'], fallback: _asString(json['greeting'])),
      currentBook: currentBook,
      currentReading: currentReading,
      readingFeed: readingFeed,
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
      final clubs = await _safeGetList('/reading-clubs/');
      final marathons = await _safeGetList('/marathons/');

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

  Future<List<dynamic>> _safeGetList(String path) async {
    try {
      return await _apiClient.getList(path);
    } catch (_) {
      return const <dynamic>[];
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


Object? _pickFirstPopulated(Map<String, dynamic> source, List<String> keys) {
  Object? fallback;

  for (final key in keys) {
    if (!source.containsKey(key)) {
      continue;
    }

    final value = source[key];
    fallback ??= value;

    if (value is List && value.isNotEmpty) {
      return value;
    }
    if (value is Map && value.isNotEmpty) {
      return value;
    }
    if (value is String && value.trim().isNotEmpty) {
      return value;
    }
    if (value != null && value is! List && value is! Map) {
      return value;
    }
  }

  return fallback;
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

List<T> _parseList<T>(
  Object? value,
  T Function(Map<String, dynamic> item) mapper,
) {
  final rawList = value is List ? value : const [];
  final parsed = <T>[];
  for (final entry in rawList) {
    final item = _asMap(entry);
    if (item == null) {
      continue;
    }
    try {
      parsed.add(mapper(item));
    } catch (_) {
      continue;
    }
  }
  return parsed;
}