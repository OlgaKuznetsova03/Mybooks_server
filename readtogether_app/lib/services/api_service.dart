import 'dart:convert';
import 'dart:io';

import '../utils/constants.dart';

class MobileApiException implements Exception {
  MobileApiException(this.message, [this.statusCode]);

  final String message;
  final int? statusCode;

  @override
  String toString() => 'MobileApiException($statusCode): $message';
}

class MobileApiService {
  MobileApiService({HttpClient? client}) : _client = client ?? HttpClient();

  final HttpClient _client;

  static const String _apiPrefix = '/api/v1/';

  Uri _buildUri(String path, {Map<String, String>? query}) {
    final base = Uri.parse(AppConstants.defaultSiteUrl);
    final normalizedBasePath = base.path.endsWith('/') ? base.path : '${base.path}/';

    // Поддерживаем две конфигурации:
    // 1. BASE_URL указывает на корень сайта (https://host/) — тогда добавляем
    //    префикс /api/v1/ сами.
    // 2. BASE_URL уже содержит префикс (https://host/api/v1/ или
    //    https://host/mobile/api/v1/) — тогда используем его как есть.
    final apiBasePath = normalizedBasePath.endsWith(_apiPrefix)
        ? normalizedBasePath
        : '$normalizedBasePath${_apiPrefix.substring(1)}';

    final endpoint = path.startsWith('/') ? path.substring(1) : path;
    final fullPath = '$apiBasePath$endpoint';
    final normalizedFullPath = fullPath.startsWith('/') ? fullPath : '/$fullPath';

    return base.replace(path: normalizedFullPath, queryParameters: query);
  }

  Future<Map<String, dynamic>> _getJson(Uri uri) async {
    final request = await _client.getUrl(uri);
    final response = await request.close();
    final body = await response.transform(utf8.decoder).join();

    if (response.statusCode >= 200 && response.statusCode < 300) {
      final decoded = json.decode(body);
      if (decoded is Map<String, dynamic>) {
        return decoded;
      }
      throw MobileApiException('Unexpected response shape', response.statusCode);
    }

    throw MobileApiException('Request failed: ${response.reasonPhrase}', response.statusCode);
  }

  Future<List<BookSummary>> fetchBooks({int pageSize = 8}) async {
    final uri = _buildUri('/api/v1/books/', query: {'page_size': '$pageSize'});
    final data = await _getJson(uri);
    final results = (data['results'] as List<dynamic>? ?? <dynamic>[]);
    return results
        .whereType<Map<String, dynamic>>()
        .map(BookSummary.fromJson)
        .toList();
  }

  Future<BookSummary?> fetchBookDetail(int id) async {
    final uri = _buildUri('/api/v1/books/$id/');
    final data = await _getJson(uri);
    return BookSummary.fromJson(data);
  }

  Future<List<ReadingClubSummary>> fetchReadingClubs({int pageSize = 8}) async {
    final uri = _buildUri('/api/v1/reading-clubs/', query: {'page_size': '$pageSize'});
    final data = await _getJson(uri);
    final results = (data['results'] as List<dynamic>? ?? <dynamic>[]);
    return results
        .whereType<Map<String, dynamic>>()
        .map(ReadingClubSummary.fromJson)
        .toList();
  }

  Future<List<ReadingMarathonSummary>> fetchMarathons({int pageSize = 8}) async {
    final uri = _buildUri('/api/v1/marathons/', query: {'page_size': '$pageSize'});
    final data = await _getJson(uri);
    final results = (data['results'] as List<dynamic>? ?? <dynamic>[]);
    return results
        .whereType<Map<String, dynamic>>()
        .map(ReadingMarathonSummary.fromJson)
        .toList();
  }

  Future<FeatureMap> fetchFeatureMap() async {
    final uri = _buildUri('/api/v1/feature-map/');
    final data = await _getJson(uri);
    return FeatureMap.fromJson(data);
  }

  Future<HomeFeed> fetchHomeFeed() async {
    final uri = _buildUri('/api/v1/home/');
    final data = await _getJson(uri);
    return HomeFeed.fromJson(data);
  }
}

class BookSummary {
  const BookSummary({
    required this.id,
    required this.title,
    required this.synopsis,
    required this.series,
    required this.seriesOrder,
    required this.language,
    required this.coverUrl,
    required this.totalPages,
    required this.averageRating,
    required this.authors,
    required this.genres,
  });

  factory BookSummary.fromJson(Map<String, dynamic> json) {
    return BookSummary(
      id: json['id'] as int? ?? 0,
      title: json['title'] as String? ?? 'Без названия',
      synopsis: json['synopsis'] as String? ?? '',
      series: json['series'] as String?,
      seriesOrder: json['series_order'] as int?,
      language: json['language'] as String? ?? '',
      coverUrl: json['cover_url'] as String?,
      totalPages: json['total_pages'] as int?,
      averageRating: (json['average_rating'] as num?)?.toDouble(),
      authors: (json['authors'] as List<dynamic>? ?? <dynamic>[])
          .whereType<Map<String, dynamic>>()
          .map(SimpleEntity.fromJson)
          .toList(),
      genres: (json['genres'] as List<dynamic>? ?? <dynamic>[])
          .whereType<Map<String, dynamic>>()
          .map(SimpleEntity.fromJson)
          .toList(),
    );
  }

  final int id;
  final String title;
  final String synopsis;
  final String? series;
  final int? seriesOrder;
  final String language;
  final String? coverUrl;
  final int? totalPages;
  final double? averageRating;
  final List<SimpleEntity> authors;
  final List<SimpleEntity> genres;

  String get primaryTag {
    if (genres.isNotEmpty) return genres.first.name;
    if (language.isNotEmpty) return language.toUpperCase();
    if (series != null && series!.isNotEmpty) return series!;
    return 'Книга';
  }

  String get subtitle {
    if (synopsis.isNotEmpty) return synopsis;
    if (authors.isNotEmpty) return authors.map((a) => a.name).join(', ');
    return 'Описание появится позже';
  }
}

class SimpleEntity {
  const SimpleEntity({required this.id, required this.name, this.slug});

  factory SimpleEntity.fromJson(Map<String, dynamic> json) {
    return SimpleEntity(
      id: json['id'] as int? ?? 0,
      name: json['name'] as String? ?? '',
      slug: json['slug'] as String?,
    );
  }

  final int id;
  final String name;
  final String? slug;
}

class ReadingClubSummary {
  ReadingClubSummary({
    required this.id,
    required this.title,
    required this.description,
    required this.startDate,
    required this.endDate,
    required this.joinPolicy,
    required this.slug,
    required this.status,
    required this.messageCount,
    required this.approvedParticipantCount,
    required this.book,
  });

  factory ReadingClubSummary.fromJson(Map<String, dynamic> json) {
    final bookJson = json['book'] as Map<String, dynamic>?;
    return ReadingClubSummary(
      id: json['id'] as int? ?? 0,
      title: json['title'] as String? ?? 'Клуб',
      description: json['description'] as String? ?? '',
      startDate: _parseDate(json['start_date'] as String?),
      endDate: _parseDate(json['end_date'] as String?),
      joinPolicy: json['join_policy'] as String? ?? '',
      slug: json['slug'] as String? ?? '',
      status: json['status'] as String? ?? '',
      messageCount: json['message_count'] as int? ?? 0,
      approvedParticipantCount: json['approved_participant_count'] as int? ?? 0,
      book: bookJson != null ? BookSummary.fromJson(bookJson) : null,
    );
  }

  final int id;
  final String title;
  final String description;
  final DateTime? startDate;
  final DateTime? endDate;
  final String joinPolicy;
  final String slug;
  final String status;
  final int messageCount;
  final int approvedParticipantCount;
  final BookSummary? book;
}

class ReadingMarathonSummary {
  ReadingMarathonSummary({
    required this.id,
    required this.title,
    required this.description,
    required this.startDate,
    required this.endDate,
    required this.joinPolicy,
    required this.slug,
    required this.status,
    required this.participantCount,
  });

  factory ReadingMarathonSummary.fromJson(Map<String, dynamic> json) {
    return ReadingMarathonSummary(
      id: json['id'] as int? ?? 0,
      title: json['title'] as String? ?? 'Марафон',
      description: json['description'] as String? ?? '',
      startDate: _parseDate(json['start_date'] as String?),
      endDate: _parseDate(json['end_date'] as String?),
      joinPolicy: json['join_policy'] as String? ?? '',
      slug: json['slug'] as String? ?? '',
      status: json['status'] as String? ?? '',
      participantCount: json['participant_count'] as int? ?? 0,
    );
  }

  final int id;
  final String title;
  final String description;
  final DateTime? startDate;
  final DateTime? endDate;
  final String joinPolicy;
  final String slug;
  final String status;
  final int participantCount;
}

class FeatureMap {
  FeatureMap(this.groups);

  factory FeatureMap.fromJson(Map<String, dynamic> json) {
    final entries = <FeatureGroup>[];
    json.forEach((key, value) {
      if (value is Map<String, dynamic>) {
        entries.add(FeatureGroup.fromJson(key, value));
      }
    });
    return FeatureMap(entries);
  }

  final List<FeatureGroup> groups;
}

class FeatureGroup {
  FeatureGroup({required this.key, required this.description, required this.endpoints});

  factory FeatureGroup.fromJson(String key, Map<String, dynamic> json) {
    final endpoints = (json['endpoints'] as List<dynamic>? ?? <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(EndpointStatus.fromJson)
        .toList();
    return FeatureGroup(
      key: key,
      description: json['description'] as String? ?? '',
      endpoints: endpoints,
    );
  }

  final String key;
  final String description;
  final List<EndpointStatus> endpoints;
}

class EndpointStatus {
  EndpointStatus({required this.path, required this.status});

  factory EndpointStatus.fromJson(Map<String, dynamic> json) {
    return EndpointStatus(
      path: json['path'] as String? ?? '',
      status: json['status'] as String? ?? '',
    );
  }

  final String path;
  final String status;
}

class HomeFeed {
  HomeFeed({required this.hero, required this.activeClubs, required this.activeMarathons, required this.readingItems});

  factory HomeFeed.fromJson(Map<String, dynamic> json) {
    final clubs = (json['active_clubs'] as List<dynamic>? ?? <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(ReadingClubSummary.fromJson)
        .toList();
    final marathons = (json['active_marathons'] as List<dynamic>? ?? <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(ReadingMarathonSummary.fromJson)
        .toList();
    final readingItems = (json['reading_items'] as List<dynamic>? ?? <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(ReadingShelfItem.fromJson)
        .toList();

    return HomeFeed(
      hero: HomeHero.fromJson(json['hero'] as Map<String, dynamic>? ?? const {}),
      activeClubs: clubs,
      activeMarathons: marathons,
      readingItems: readingItems,
    );
  }

  final HomeHero hero;
  final List<ReadingClubSummary> activeClubs;
  final List<ReadingMarathonSummary> activeMarathons;
  final List<ReadingShelfItem> readingItems;
}

class HomeHero {
  HomeHero({required this.headline, required this.subtitle, required this.timestamp});

  factory HomeHero.fromJson(Map<String, dynamic> json) {
    return HomeHero(
      headline: json['headline'] as String? ?? 'Калейдоскоп книг',
      subtitle: json['subtitle'] as String? ?? 'Сообщества, марафоны и полка "Читаю" в одном экране.',
      timestamp: _parseDate(json['timestamp'] as String?),
    );
  }

  final String headline;
  final String subtitle;
  final DateTime? timestamp;
}

class ReadingShelfItem {
  ReadingShelfItem({
    required this.id,
    required this.addedAt,
    required this.book,
    required this.progressPercent,
    required this.progressLabel,
    required this.progressCurrentPage,
    required this.progressTotalPages,
    required this.progressUpdatedAt,
  });

  factory ReadingShelfItem.fromJson(Map<String, dynamic> json) {
    final bookJson = json['book'] as Map<String, dynamic>?;
    return ReadingShelfItem(
      id: json['id'] as int? ?? 0,
      addedAt: _parseDate(json['added_at'] as String?),
      book: bookJson != null ? BookSummary.fromJson(bookJson) : const BookSummary(
          id: 0,
          title: 'Книга',
          synopsis: '',
          series: null,
          seriesOrder: null,
          language: '',
          coverUrl: null,
          totalPages: null,
          averageRating: null,
          authors: <SimpleEntity>[],
          genres: <SimpleEntity>[],
        ),
      progressPercent: (json['progress_percent'] as num?)?.toDouble(),
      progressLabel: json['progress_label'] as String?,
      progressCurrentPage: json['progress_current_page'] as int?,
      progressTotalPages: json['progress_total_pages'] as int?,
      progressUpdatedAt: _parseDate(json['progress_updated_at'] as String?),
    );
  }

  final int id;
  final DateTime? addedAt;
  final BookSummary book;
  final double? progressPercent;
  final String? progressLabel;
  final int? progressCurrentPage;
  final int? progressTotalPages;
  final DateTime? progressUpdatedAt;
}

DateTime? _parseDate(String? value) {
  if (value == null || value.isEmpty) return null;
  return DateTime.tryParse(value)?.toLocal();
}