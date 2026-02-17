class CurrentBook {
  const CurrentBook({required this.title, required this.author, required this.progress, required this.coverUrl});

  final String title;
  final String author;
  final int progress;
  final String coverUrl;

  factory CurrentBook.fromJson(Map<String, dynamic> json) => CurrentBook(
        title: json['title'] as String? ?? 'Без названия',
        author: json['author'] as String? ?? 'Неизвестный автор',
        progress: json['progress'] as int? ?? 0,
        coverUrl: json['cover_url'] as String? ?? '',
      );
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
  const MarathonItem({required this.id, required this.name, required this.participants});

  final int id;
  final String name;
  final int participants;

  factory MarathonItem.fromJson(Map<String, dynamic> json) => MarathonItem(
        id: json['id'] as int? ?? 0,
        name: json['name'] as String? ?? 'Марафон',
        participants: json['participants'] as int? ?? 0,
      );
}

class HomePayload {
  const HomePayload({
    required this.currentBook,
    required this.readingFeed,
    required this.authorOffers,
    required this.bloggerOffers,
    required this.marathons,
  });

  final CurrentBook currentBook;
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

  factory BookItem.fromJson(Map<String, dynamic> json) => BookItem(
        id: json['id'] as int? ?? 0,
        title: json['title'] as String? ?? 'Без названия',
        author: json['author'] as String? ?? 'Неизвестный автор',
        genre: json['genre'] as String? ?? 'Прочее',
        coverUrl: json['cover_url'] as String? ?? '',
      );
}

class StatsPayload {
  const StatsPayload({required this.booksPerMonth, required this.challengeProgress, required this.readingCalendar});

  final List<int> booksPerMonth;
  final int challengeProgress;
  final List<int> readingCalendar;
}