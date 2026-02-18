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
        title: json['title'] as String? ?? 'Без названия',
        author: json['author'] as String? ?? 'Неизвестный автор',
        progress: json['progress'] as int? ?? 0,
        coverUrl: json['cover_url'] as String? ?? '',
        totalPages: (json['total_pages'] as num?)?.round() ?? 0,
      );

  factory CurrentBook.fromShelfItem(Map<String, dynamic> json) {
    final book = json['book'] as Map<String, dynamic>? ?? const {};
    final authors = (book['authors'] as List<dynamic>? ?? const [])
        .map((entry) => (entry as Map<String, dynamic>)['name'] as String? ?? '')
        .where((name) => name.isNotEmpty)
        .toList();

    return CurrentBook(
      title: book['title'] as String? ?? 'Без названия',
      author: authors.isNotEmpty ? authors.first : 'Неизвестный автор',
      progress: (json['progress_percent'] as num?)?.round() ?? 0,
      coverUrl: book['cover_url'] as String? ?? '',
      totalPages: (json['progress_total_pages'] as num?)?.round() ?? (book['total_pages'] as num?)?.round() ?? 0,
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
        userAvatar: json['user_avatar'] as String? ?? '',
        userName: json['user_name'] as String? ?? 'Пользователь',
        bookTitle: json['book_title'] as String? ?? 'Книга',
        pagesRead: json['pages_read'] as int? ?? 0,
        coverUrl: json['cover_url'] as String? ?? '',
      );

  factory ReadingUpdate.fromClub(Map<String, dynamic> json) {
    final book = json['book'] as Map<String, dynamic>? ?? const {};
    return ReadingUpdate(
      userAvatar: '',
      userName: json['title'] as String? ?? 'Книжный клуб',
      bookTitle: book['title'] as String? ?? 'Книга не указана',
      pagesRead: (json['approved_participant_count'] as num?)?.toInt() ?? 0,
      coverUrl: book['cover_url'] as String? ?? '',
    );
  }
}

class CollaborationOffer {
  const CollaborationOffer({required this.id, required this.title, required this.subtitle});

  final int id;
  final String title;
  final String subtitle;

  factory CollaborationOffer.fromJson(Map<String, dynamic> json) => CollaborationOffer(
        id: json['id'] as int? ?? 0,
        title: json['title'] as String? ?? 'Предложение',
        subtitle: json['subtitle'] as String? ?? '',
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
        id: json['id'] as int? ?? 0,
        name: json['name'] as String? ?? 'Марафон',
        participants: json['participants'] as int? ?? 0,
        status: json['status'] as String? ?? 'active',
        themeCount: json['theme_count'] as int? ?? 0,
      );

  factory MarathonItem.fromApi(Map<String, dynamic> json) => MarathonItem(
        id: json['id'] as int? ?? 0,
        name: json['title'] as String? ?? 'Марафон',
        participants: (json['participant_count'] as num?)?.toInt() ?? 0,
        status: json['status'] as String? ?? 'active',
        themeCount: (json['theme_count'] as num?)?.toInt() ?? 0,
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
}

class BookItem {
  const BookItem({required this.id, required this.title, required this.author, required this.genre, required this.coverUrl});

  final int id;
  final String title;
  final String author;
  final String genre;
  final String coverUrl;

  factory BookItem.fromJson(Map<String, dynamic> json) {
    final authors = (json['authors'] as List<dynamic>? ?? const [])
        .map((entry) => (entry as Map<String, dynamic>)['name'] as String? ?? '')
        .where((name) => name.isNotEmpty)
        .toList();
    final genres = (json['genres'] as List<dynamic>? ?? const [])
        .map((entry) => (entry as Map<String, dynamic>)['name'] as String? ?? '')
        .where((name) => name.isNotEmpty)
        .toList();

    return BookItem(
      id: json['id'] as int? ?? 0,
      title: json['title'] as String? ?? 'Без названия',
      author: authors.isNotEmpty ? authors.first : 'Неизвестный автор',
      genre: genres.isNotEmpty ? genres.first : 'Прочее',
      coverUrl: json['cover_url'] as String? ?? '',
    );
  }
}

class StatsPayload {
  const StatsPayload({required this.booksPerMonth, required this.challengeProgress, required this.readingCalendar});

  final List<int> booksPerMonth;
  final int challengeProgress;
  final List<int> readingCalendar;
}