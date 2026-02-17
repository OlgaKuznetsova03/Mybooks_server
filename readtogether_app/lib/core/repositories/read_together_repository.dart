import '../models/feed_models.dart';
import '../network/api_client.dart';

class ReadTogetherRepository {
  ReadTogetherRepository({ApiClient? apiClient}) : _apiClient = apiClient ?? ApiClient();

  final ApiClient _apiClient;

  Future<HomePayload> fetchHome() async {
    try {
      final json = await _apiClient.getJson('/mobile/home/');
      return HomePayload(
        currentBook: CurrentBook.fromJson(json['current_book'] as Map<String, dynamic>? ?? {}),
        readingFeed: (json['reading_feed'] as List<dynamic>? ?? const []).map((e) => ReadingUpdate.fromJson(e as Map<String, dynamic>)).toList(),
        authorOffers: (json['author_offers'] as List<dynamic>? ?? const []).map((e) => CollaborationOffer.fromJson(e as Map<String, dynamic>)).toList(),
        bloggerOffers: (json['blogger_offers'] as List<dynamic>? ?? const []).map((e) => CollaborationOffer.fromJson(e as Map<String, dynamic>)).toList(),
        marathons: (json['marathons'] as List<dynamic>? ?? const []).map((e) => MarathonItem.fromJson(e as Map<String, dynamic>)).toList(),
      );
    } catch (_) {
      return const HomePayload(
        currentBook: CurrentBook(title: '1984', author: 'Джордж Оруэлл', progress: 63, coverUrl: ''),
        readingFeed: [
          ReadingUpdate(userAvatar: '', userName: 'Анна', bookTitle: 'Мастер и Маргарита', pagesRead: 42, coverUrl: ''),
          ReadingUpdate(userAvatar: '', userName: 'Илья', bookTitle: 'Сияние', pagesRead: 19, coverUrl: ''),
        ],
        authorOffers: [CollaborationOffer(id: 1, title: 'Авторский эфир', subtitle: 'Интервью и чтение главы')],
        bloggerOffers: [CollaborationOffer(id: 2, title: 'Совместный обзор', subtitle: 'Книжный блог + автор')],
        marathons: [MarathonItem(id: 1, name: '7 дней фантастики', participants: 128)],
      );
    }
  }

  Future<List<BookItem>> fetchBooks({String query = ''}) async {
    try {
      final data = await _apiClient.getList('/mobile/books/?search=$query');
      return data.map((e) => BookItem.fromJson(e as Map<String, dynamic>)).toList();
    } catch (_) {
      return const [
        BookItem(id: 1, title: 'Три товарища', author: 'Эрих Мария Ремарк', genre: 'Классика', coverUrl: ''),
        BookItem(id: 2, title: 'Дюна', author: 'Фрэнк Герберт', genre: 'Фантастика', coverUrl: ''),
      ];
    }
  }

  Future<void> addBook({required String title, required String author, required String genre}) {
    return _apiClient.postJson('/mobile/books/', {'title': title, 'author': author, 'genre': genre});
  }

  Future<StatsPayload> fetchStats() async {
    try {
      final json = await _apiClient.getJson('/mobile/stats/');
      return StatsPayload(
        booksPerMonth: (json['books_per_month'] as List<dynamic>? ?? const []).map((e) => e as int).toList(),
        challengeProgress: json['challenge_progress'] as int? ?? 0,
        readingCalendar: (json['calendar'] as List<dynamic>? ?? const []).map((e) => e as int).toList(),
      );
    } catch (_) {
      return const StatsPayload(
        booksPerMonth: [1, 2, 1, 3, 2, 4, 3, 2, 4, 5, 2, 3],
        challengeProgress: 68,
        readingCalendar: [1, 0, 1, 1, 0, 1, 1],
      );
    }
  }
}