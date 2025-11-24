import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../../utils/url_launcher.dart';
import '../../widgets/dialogs/url_choice_dialog.dart';
import 'web_view_controller.dart';

class WebViewNavigation {
  WebViewNavigation({required this.webViewManager, required this.context});

  final WebViewManager webViewManager;
  final BuildContext context;
  final UrlLauncher _urlLauncher = UrlLauncher();
  bool _isOfflineBackNavigation = false;

  Future<NavigationDecision> handleNavigationRequest(NavigationRequest request) async {
    final uri = Uri.tryParse(request.url);
    if (uri == null) return NavigationDecision.navigate;

    // Пропускаем загрузку ресурсов (картинки, CSS, JS) - это позволяет показывать баннеры
    if (_isResourceRequest(uri)) {
      return NavigationDecision.navigate;
    }

    // Проверяем, является ли переход рекламным кликом
    if (_isAdClick(uri)) {
      await _handleAdClick(uri);
      return NavigationDecision.prevent;
    }

    if (!_isStandardWebScheme(uri.scheme)) {
      await _urlLauncher.launchExternalUrl(uri, context);
      return NavigationDecision.prevent;
    }

    if (uri.scheme == 'http' || uri.scheme == 'https') {
      if (!_isSameOrigin(uri)) {
        final decision = await showUrlChoiceDialog(context, uri);
        if (decision == null) return NavigationDecision.navigate;
        if (decision == UrlDecision.openInBrowser) {
          await _urlLauncher.launchExternalUrl(uri, context);
          return NavigationDecision.prevent;
        }
        return mapDecisionToNavigation(decision);
      }
    }

    if (_shouldInterceptDownload(uri)) {
      await webViewManager.startDownload(uri, context);
      return NavigationDecision.prevent;
    }

    return NavigationDecision.navigate;
  }

  // Разрешаем загрузку ресурсов (баннеры, картинки, стили, скрипты)
  bool _isResourceRequest(Uri uri) {
    final path = uri.path.toLowerCase();
    
    // Разрешаем все ресурсы для отображения страницы
    final resourceExtensions = [
      '.png', '.jpg', '.jpeg', '.gif', '.webp', // изображения
      '.css', '.js', '.woff', '.woff2', '.ttf', // стили и шрифты
      '.ico', '.svg', '.mp4', '.webm' // другие ресурсы
    ];
    
    final isResource = resourceExtensions.any((ext) => path.endsWith(ext));
    
    // Разрешаем запросы к CDN и доменам ресурсов
    final host = uri.host.toLowerCase();
    final isCdn = host.contains('cdn.') || 
                  host.contains('static.') || 
                  host.contains('assets.');
    
    return isResource || isCdn;
  }

  // Определяем именно клики по рекламе, а не загрузку баннеров
  bool _isAdClick(Uri uri) {
    final path = uri.path.toLowerCase();
    final host = uri.host.toLowerCase();
    final query = uri.query.toLowerCase();

    // Признаки именно кликов по рекламе
    final adClickPatterns = [
      'click', 'redirect', 'goto', 'jump', 'target',
      'out.php', 'exit.php', 'link.php', 'go.php',
      'clk', 'rdr', 'url=', 'redirect_url=',
      'adclick', 'bannerclick'
    ];

    final isClick = adClickPatterns.any((pattern) => 
      path.contains(pattern) || query.contains(pattern)
    );

    // Известные домены редиректов рекламы
    final adRedirectDomains = [
      'click.', 'redirect.', 'go.', 'link.', 'out.',
      'an.yandex.ru', 'ads.', 'adclick.', 'doubleclick.net'
    ];

    final isRedirectDomain = adRedirectDomains.any((domain) => 
      host.contains(domain)
    );

    return isClick || isRedirectDomain;
  }

  Future<void> _handleAdClick(Uri uri) async {
    // Показываем диалог для рекламных кликов
    if (context.mounted) {
      final decision = await showDialog<UrlDecision>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Рекламная ссылка'),
          content: Text('Перейти по рекламной ссылке?\n${uri.host}'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, UrlDecision.openInBrowser),
              child: const Text('Открыть в браузере'),
            ),
            TextButton(
              onPressed: () => Navigator.pop(context, UrlDecision.openInApp),
              child: const Text('Открыть здесь'),
            ),
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Отмена'),
            ),
          ],
        ),
      );

      if (decision == UrlDecision.openInBrowser) {
        await _urlLauncher.launchExternalUrl(uri, context);
      } else if (decision == UrlDecision.openInApp) {
        // Разрешаем навигацию в вебвью
        webViewManager.controller.loadRequest(uri);
      }
    }
  }

  Future<bool> handleBack() async {
    if (_isOfflineBackNavigation) {
      return true;
    }

    if (await webViewManager.controller.canGoBack()) {
      if (webViewManager.isOffline) {
        return _handleOfflineBack();
      }

      webViewManager.controller.goBack();
      return false;
    }
    return true;
  }

  Future<bool> _handleOfflineBack() async {
    try {
      _isOfflineBackNavigation = true;
      webViewManager.setState(loading: true, error: false, loadingTimedOut: false);

      if (webViewManager.hasOfflineHistory) {
        await webViewManager.handleOfflineNavigation().timeout(
          const Duration(seconds: 3),
          onTimeout: () => webViewManager.setState(loading: false, error: false),
        );
      } else {
        await webViewManager.controller.goBack().timeout(
          const Duration(seconds: 3),
          onTimeout: () => webViewManager.setState(loading: false, error: false),
        );
      }

      await Future.delayed(const Duration(milliseconds: 500));
      return false;
    } catch (error) {
      debugPrint('Offline back navigation error: $error');
      await _showCachedVersion();
      return false;
    } finally {
      _isOfflineBackNavigation = false;
      webViewManager.setState(loading: false, error: false, loadingTimedOut: false);
    }
  }

  Future<void> _showCachedVersion() async {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Показываем сохраненную версию страницы'),
          duration: Duration(seconds: 2),
        ),
      );
    }

    webViewManager.showOfflineBanner = true;
    webViewManager.setState(loading: false, error: false, loadingTimedOut: false);
  }

  bool _isStandardWebScheme(String scheme) {
    return scheme == 'http' || scheme == 'https';
  }

  bool _shouldInterceptDownload(Uri uri) {
    final path = uri.path;
    if (path.toLowerCase().endsWith('.pdf')) {
      return true;
    }
    if (path == '/accounts/me/print/monthly/' || path == '/accounts/me/print/monthly') {
      return true;
    }

    final segments = uri.pathSegments;
    if (segments.length >= 3 && segments.first == 'books' && segments.last == 'print-review') {
      return true;
    }

    return false;
  }

  bool _isSameOrigin(Uri uri) {
    final origin = webViewManager.siteOrigin;
    if (uri.host.isEmpty) {
      return true;
    }

    final currentHost = origin.host.toLowerCase();
    final targetHost = uri.host.toLowerCase();

    if (targetHost != currentHost && !targetHost.endsWith('.$currentHost')) {
      return false;
    }

    if (origin.hasPort && uri.port != origin.port) {
      return false;
    }

    return true;
  }

  NavigationDecision mapDecisionToNavigation(UrlDecision decision) {
    switch (decision) {
      case UrlDecision.openInApp:
        return NavigationDecision.navigate;
      case UrlDecision.openInBrowser:
        return NavigationDecision.prevent;
      default:
        return NavigationDecision.navigate;
    }
  }
}