import '../models/feed_models.dart';
import '../network/api_client.dart';

class ReadTogetherRepository {
  ReadTogetherRepository({ApiClient? apiClient}) : _apiClient = apiClient ?? ApiClient();

  final ApiClient _apiClient;

  Future<HomePayload> fetchHome() async {
    final json = await _apiClient.getJson('/home/');

    final readingItems = (json['reading_items'] as List<dynamic>? ?? const [])
        .map((entry) => entry as Map<String, dynamic>)
        .toList();

    final currentBook = readingItems.isNotEmpty
        ? CurrentBook.fromShelfItem(readingItems.first)
        : const CurrentBook(title: 'Нет активной книги', author: 'Добавьте книгу в полку «Читаю»', progress: 0, coverUrl: '');

    final marathons = (json['active_marathons'] as List<dynamic>? ?? const [])
        .map((entry) => MarathonItem.fromApi(entry as Map<String, dynamic>))
        .toList();

    return HomePayload(
      currentBook: currentBook,
      readingFeed: (json['active_clubs'] as List<dynamic>? ?? const [])
          .map((entry) => ReadingUpdate.fromClub(entry as Map<String, dynamic>))
          .toList(),
      authorOffers: const [],
      bloggerOffers: const [],
      marathons: marathons,
    );
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

  Future<StatsPayload> fetchStats() async {
    final json = await _apiClient.getJson('/stats/');
    return StatsPayload(
      booksPerMonth: (json['books_per_month'] as List<dynamic>? ?? const []).map((e) => (e as num).toInt()).toList(),
      challengeProgress: (json['challenge_progress'] as num?)?.toInt() ?? 0,
      readingCalendar: (json['calendar'] as List<dynamic>? ?? const []).map((e) => (e as num).toInt()).toList(),
    );
  }
}