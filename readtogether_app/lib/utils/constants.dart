class AppConstants {
  static const String fallbackSiteUrl = 'https://kalejdoskopknig.ru/';
  static const String defaultSiteUrl = String.fromEnvironment(
    'MYBOOKS_SITE_URL',
    defaultValue: fallbackSiteUrl,
  );
  static const int loadingTimeoutSeconds = 5;
  static const bool isYandexAdEnabled = true;
}

class AppRoutes {
  static const String home = '/';
}

class AppPaths {
  static const String home = '/';
  static const String myBooks = '/books/book_list';
  static const String clubs = '/reading-clubs/';
  static const String marathons = '/marathons/';
  static const String profile = '/accounts/me/';
  static const String collaborations = '/collaborations/';
  static const String communities = '/reading-communities/';
  static const String games = '/games/';
}