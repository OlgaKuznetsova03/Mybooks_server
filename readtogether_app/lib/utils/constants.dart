class AppConstants {
  static const String fallbackSiteUrl = 'https://kalejdoskopknig.ru/';
  static const String defaultSiteUrl = String.fromEnvironment(
    'MYBOOKS_SITE_URL',
    defaultValue: fallbackSiteUrl,
  );
  static const int loadingTimeoutSeconds = 5;
}

class AppRoutes {
  static const String home = '/';
}