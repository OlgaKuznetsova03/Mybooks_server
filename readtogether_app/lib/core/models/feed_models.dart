class CurrentBook {
  const CurrentBook({
    required this.title,
    required this.author,
    required this.progress,
    required this.coverUrl,
    required this.totalPages,
  });

  final String title;
  final String author;
  final int progress;
  final String coverUrl;
  final int totalPages;

  factory CurrentBook.fromJson(Map<String, dynamic> json) => CurrentBook(
        title: _asString(json['title'], fallback: 'Без названия'),
        author: _asString(json['author'], fallback: 'Неизвестный автор'),
        progress: _asInt(json['progress']),
        coverUrl: _asString(json['cover_url']),
        totalPages: _asInt(json['total_pages']),
      );

  factory CurrentBook.fromShelfItem(Map<String, dynamic> json) {
    final book = _asMap(json['book']) ?? json;
    final authors = (book['authors'] as List<dynamic>? ?? const [])
        .map((entry) => entry is Map<String, dynamic> ? _asString(entry['name']) : '')
        .where((name) => name.isNotEmpty)
        .toList();

    return CurrentBook(
      title: _asString(book['title'], fallback: 'Без названия'),
      author: authors.isNotEmpty ? authors.first : 'Неизвестный автор',
      progress: _asInt(json['progress_percent'], fallback: _asInt(json['progress'])),
      coverUrl: _asString(book['cover_url']),
      totalPages: _asInt(
        json['progress_total_pages'],
        fallback: _asInt(json['total_pages'], fallback: _asInt(book['total_pages'])),
      ),
    );
  }
}

class ReadingUpdate {
  const ReadingUpdate({required this.userAvatar, required this.userName, required this.bookTitle, required this.pagesRead, required this.coverUrl});

  final String userAvatar;
  final String userName;
  final String bookTitle;
  final int pagesRead;
  final String coverUrl;

  factory ReadingUpdate.fromJson(Map<String, dynamic> json) => ReadingUpdate(
        userAvatar: _asString(json['user_avatar']),
        userName: _asString(json['user_name'], fallback: 'Пользователь'),
        bookTitle: _asString(json['book_title'], fallback: 'Книга'),
        pagesRead: _asInt(json['pages_read']),
        coverUrl: _asString(json['cover_url']),
      );

  factory ReadingUpdate.fromClub(Map<String, dynamic> json) {
    final book = _asMap(json['book']) ?? const <String, dynamic>{};
    return ReadingUpdate(
      userAvatar: '',
      userName: _asString(json['title'], fallback: 'Книжный клуб'),
      bookTitle: _asString(book['title'], fallback: 'Книга не указана'),
      pagesRead: _asInt(json['approved_participant_count']),
      coverUrl: _asString(book['cover_url']),
    );
  }

  factory ReadingUpdate.fromDynamic(Map<String, dynamic> json) {
    if (json.containsKey('user_name') || json.containsKey('book_title')) {
      return ReadingUpdate.fromJson(json);
    }
    return ReadingUpdate.fromClub(json);
  }
}

class CollaborationOffer {
  const CollaborationOffer({required this.id, required this.title, required this.subtitle});

  final int id;
  final String title;
  final String subtitle;

  factory CollaborationOffer.fromJson(Map<String, dynamic> json) => CollaborationOffer(
        id: _asInt(json['id']),
        title: _asString(json['title'], fallback: 'Предложение'),
        subtitle: _asString(json['subtitle']),
      );
}

class MarathonItem {
  const MarathonItem({required this.id, required this.name, required this.participants, required this.status, required this.themeCount});

  final int id;
  final String name;
  final int participants;
  final String status;
  final int themeCount;

  factory MarathonItem.fromJson(Map<String, dynamic> json) => MarathonItem(
        id: _asInt(json['id']),
        name: _asString(json['name'], fallback: 'Марафон'),
        participants: _asInt(json['participants']),
        status: _asString(json['status'], fallback: 'active'),
        themeCount: _asInt(json['theme_count']),
      );

  factory MarathonItem.fromApi(Map<String, dynamic> json) => MarathonItem(
        id: _asInt(json['id']),
        name: _asString(json['title'], fallback: _asString(json['name'], fallback: 'Марафон')),
        participants: _asInt(json['participant_count'], fallback: _asInt(json['participants'])),
        status: _asString(json['status'], fallback: 'active'),
        themeCount: _asInt(json['theme_count']),
      );
}

class ReadingMetrics {
  const ReadingMetrics({required this.totalPages, required this.averagePagesPerDay});

  final int totalPages;
  final int averagePagesPerDay;

  factory ReadingMetrics.fromJson(Map<String, dynamic> json) => ReadingMetrics(
        totalPages: _asInt(json['total_pages']),
        averagePagesPerDay: _asInt(json['average_pages_per_day']),
      );
}

class HomePayload {
  const HomePayload({
    required this.headline,
    required this.subtitle,
    required this.greeting,
    required this.currentBook,
    required this.currentReading,
    required this.readingFeed,
    required this.authorOffers,
    required this.bloggerOffers,
    required this.marathons,
    required this.readingMetrics,
  });

  final String headline;
  final String subtitle;
  final String? greeting;
  final CurrentBook currentBook;
  final List<CurrentBook> currentReading;
  final List<ReadingUpdate> readingFeed;
  final List<CollaborationOffer> authorOffers;
  final List<CollaborationOffer> bloggerOffers;
  final List<MarathonItem> marathons;
  final ReadingMetrics? readingMetrics;
}

String _asString(Object? value, {String fallback = ''}) {
  if (value is String && value.isNotEmpty) {
    return value;
  }
  return fallback;
}

int _asInt(Object? value, {int fallback = 0}) {
  if (value is int) {
    return value;
  }
  if (value is num) {
    return value.round();
  }
  if (value is String) {
    return int.tryParse(value) ?? double.tryParse(value)?.round() ?? fallback;
  }
  return fallback;
}

double _asDouble(Object? value, {double fallback = 0}) {
  if (value is double) {
    return value;
  }
  if (value is num) {
    return value.toDouble();
  }
  if (value is String) {
    return double.tryParse(value) ?? fallback;
  }
  return fallback;
}

class BookItem {
  const BookItem({
    required this.id,
    required this.title,
    required this.author,
    required this.genre,
    required this.coverUrl,
    required this.averageRating,
    required this.totalPages,
    required this.synopsis,
    required this.language,
    required this.authors,
    required this.genres,
  });

  final int id;
  final String title;
  final String author;
  final String genre;
  final String coverUrl;
  final double averageRating;
  final int totalPages;
  final String synopsis;
  final String language;
  final List<String> authors;
  final List<String> genres;

  factory BookItem.fromJson(Map<String, dynamic> json) {
    final authors = (json['authors'] as List<dynamic>? ?? const [])
        .map((entry) => entry is Map<String, dynamic> ? _asString(entry['name']) : '')
        .where((name) => name.isNotEmpty)
        .toList();
    final genres = (json['genres'] as List<dynamic>? ?? const [])
        .map((entry) => entry is Map<String, dynamic> ? _asString(entry['name']) : '')
        .where((name) => name.isNotEmpty)
        .toList();

    return BookItem(
      id: json['id'] as int? ?? 0,
      title: json['title'] as String? ?? 'Без названия',
      author: authors.isNotEmpty ? authors.first : 'Неизвестный автор',
      genre: genres.isNotEmpty ? genres.first : 'Прочее',
      coverUrl: json['cover_url'] as String? ?? '',
      averageRating: _asDouble(json['average_rating']),
      totalPages: _asInt(json['total_pages']),
      synopsis: _asString(json['synopsis']),
      language: _asString(json['language']),
      authors: authors,
      genres: genres,
    );
  }
}

class BookIsbn {
  const BookIsbn({required this.id, required this.isbn, required this.isbn13});

  final int id;
  final String isbn;
  final String isbn13;

  factory BookIsbn.fromJson(Map<String, dynamic> json) => BookIsbn(
        id: _asInt(json['id']),
        isbn: _asString(json['isbn']),
        isbn13: _asString(json['isbn13']),
      );
}

class BookDetailItem {
  const BookDetailItem({required this.book, required this.isbn});

  final BookItem book;
  final List<BookIsbn> isbn;

  factory BookDetailItem.fromJson(Map<String, dynamic> json) {
    final isbnRaw = json['isbn'] as List<dynamic>? ?? const [];
    return BookDetailItem(
      book: BookItem.fromJson(json),
      isbn: isbnRaw
          .map((entry) => entry is Map<String, dynamic> ? BookIsbn.fromJson(entry) : null)
          .whereType<BookIsbn>()
          .toList(),
    );
  }
}

class StatsPayload {
  const StatsPayload({required this.booksPerMonth, required this.challengeProgress, required this.readingCalendar});

  final List<int> booksPerMonth;
  final int challengeProgress;
  final List<int> readingCalendar;
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