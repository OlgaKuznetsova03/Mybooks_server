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