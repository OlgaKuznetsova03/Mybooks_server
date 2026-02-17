import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';
import 'package:webview_flutter_wkwebview/webview_flutter_wkwebview.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../services/download_service.dart';
import '../../services/file_service.dart';
import '../../utils/constants.dart';
import '../../utils/url_launcher.dart';
import '../../widgets/dialogs/download_progress_dialog.dart';

class WebViewState {
  final bool isLoading;
  final bool hasError;
  final bool isLoadingTimedOut;

  const WebViewState({
    this.isLoading = false,
    this.hasError = false,
    this.isLoadingTimedOut = false,
  });
}

class WebViewManager {
  WebViewManager({required this.startUrl})
      : siteOrigin = Uri.parse(startUrl);

  final String startUrl;
  final Uri siteOrigin;
  late final WebViewController controller;
  final ValueNotifier<WebViewState> stateNotifier =
      ValueNotifier(const WebViewState());
  final FileService _fileService = FileService();
  final DownloadService _downloadService = DownloadService();
  final UrlLauncher _urlLauncher = UrlLauncher();
  Timer? _loadingTimer;
  bool isOffline = false;
  bool showOfflineBanner = false;

  final List<String> _historyCache = [];
  int _currentHistoryIndex = -1;

  Future<void> initialize({
    required Future<NavigationDecision> Function(NavigationRequest)
        onNavigationRequest,
    required void Function(JavaScriptMessage) onJavaScriptMessage,
    required BuildContext context,
  }) async {
    final PlatformWebViewControllerCreationParams params;
    if (WebViewPlatform.instance is WebKitWebViewPlatform) {
      params = WebKitWebViewControllerCreationParams(
        allowsInlineMediaPlayback: true,
      );
    } else {
      params = const PlatformWebViewControllerCreationParams();
    }

    final controller = WebViewController.fromPlatformCreationParams(params)
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0x00000000))
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageStarted: (url) => _handlePageStarted(url),
          onPageFinished: (_) {
            _handlePageFinished();
            _injectLinkInterceptor();
          },
          onWebResourceError: (error) => _handleWebResourceError(error),
          onNavigationRequest: onNavigationRequest,
        ),
      );

    controller.addJavaScriptChannel(
      'ReadTogetherApp',
      onMessageReceived: onJavaScriptMessage,
    );

    controller.addJavaScriptChannel(
      'LinkInterceptor',
      onMessageReceived: (JavaScriptMessage message) {
        final uri = Uri.tryParse(message.message);
        if (uri != null) {
          unawaited(_urlLauncher.launchExternalUrl(uri, context));
        }
      },
    );

    if (controller.platform is AndroidWebViewController) {
      final android = controller.platform as AndroidWebViewController;
      android
        ..setMediaPlaybackRequiresUserGesture(false)
        ..setOnShowFileSelector(_fileService.onShowFileSelector)
        ..setOnDownloadStart((request) {
          final uri = Uri.tryParse(request.url);
          if (uri != null) {
            unawaited(startDownload(uri, context));
          }
        });
    }

    this.controller = controller;
  }

  void _handlePageStarted(String? url) {
    setState(loading: true, error: false, loadingTimedOut: false);
    _addToHistory(url);
    _loadingTimer?.cancel();
    _loadingTimer = Timer(
      const Duration(seconds: AppConstants.loadingTimeoutSeconds),
      _handleLoadingTimeout,
    );
  }

  void _handlePageFinished() {
    _loadingTimer?.cancel();
    setState(loading: false, error: false, loadingTimedOut: false);
    _injectLinkInterceptor();
  }

  void _handleWebResourceError(WebResourceError error) {
    _loadingTimer?.cancel();
    final isMainFrameError = error.isForMainFrame ?? true;
    stateNotifier.value = WebViewState(
      isLoading: false,
      hasError: isMainFrameError,
      isLoadingTimedOut: false,
    );
  }

  void _handleLoadingTimeout() {
    setState(loading: false, loadingTimedOut: true);
  }

  void setState({bool? loading, bool? error, bool? loadingTimedOut}) {
    final current = stateNotifier.value;
    stateNotifier.value = WebViewState(
      isLoading: loading ?? current.isLoading,
      hasError: error ?? current.hasError,
      isLoadingTimedOut: loadingTimedOut ?? current.isLoadingTimedOut,
    );
  }

  void _addToHistory(String? url) {
    if (url == null || url.isEmpty) {
      return;
    }

    if (_currentHistoryIndex >= 0 &&
        _currentHistoryIndex < _historyCache.length - 1) {
      _historyCache.removeRange(_currentHistoryIndex + 1, _historyCache.length);
    }

    if (_historyCache.isEmpty || _historyCache.last != url) {
      _historyCache.add(url);
      _currentHistoryIndex = _historyCache.length - 1;
    }
  }

  bool get hasOfflineHistory => _currentHistoryIndex > 0;

  Future<void> handleOfflineNavigation() async {
    if (_historyCache.isEmpty) return;

    setState(loading: true, error: false, loadingTimedOut: false);

    try {
      if (_currentHistoryIndex > 0) {
        _currentHistoryIndex--;
        final previousUrl = _historyCache[_currentHistoryIndex];
        await controller.loadRequest(Uri.parse(previousUrl));
      }
    } catch (error) {
      debugPrint('Offline navigation error: $error');
      setState(loading: false, error: true);
    }
  }

  Future<Map<String, String>> collectCookies() async {
    try {
      final rawResult = await controller.runJavaScriptReturningResult('document.cookie');

      String? cookieString;
      if (rawResult is String) {
        cookieString = rawResult;
      } else {
        cookieString = rawResult.toString();
      }

      final trimmed = cookieString.trim();
      if (trimmed.isEmpty || trimmed == 'null') {
        return {};
      }

      final sanitized = trimmed.startsWith('"') && trimmed.endsWith('"')
          ? trimmed.substring(1, trimmed.length - 1)
          : trimmed;

      final Map<String, String> cookies = {};
      for (final entry in sanitized.split(';')) {
        final parts = entry.split('=');
        if (parts.isEmpty) {
          continue;
        }
        final name = parts.first.trim();
        if (name.isEmpty) {
          continue;
        }
        final value = parts.skip(1).join('=').trim();
        cookies[name] = value;
      }
      return cookies;
    } catch (_) {
      return {};
    }
  }

  Future<void> startDownload(Uri uri, BuildContext context) async {
    final navigator = Navigator.of(context, rootNavigator: true);
    final progressDialog = showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => const DownloadProgressDialog(),
    );

    File? downloadedFile;
    Object? downloadError;
    try {
      final cookies = await collectCookies();
      downloadedFile = await _downloadService.downloadFile(uri, cookies);
    } catch (error) {
      downloadError = error;
    } finally {
      if (navigator.canPop()) {
        navigator.pop();
      }
      await progressDialog;
    }

    if (downloadedFile != null) {
      final fileUri = Uri.file(downloadedFile.path).toString();
      if (await canLaunchUrl(Uri.parse(fileUri))) {
        await launchUrl(Uri.parse(fileUri));
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Файл открывается...')),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Файл сохранён в: ${downloadedFile.path}')),
        );
      }
    } else if (downloadError != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Не удалось скачать файл: $downloadError')),
      );
    }
  }

  String prepareStartUrl(String rawUrl) {
    final trimmed = rawUrl.trim();
    if (trimmed.isEmpty) {
      return AppConstants.fallbackSiteUrl;
    }

    try {
      final parsed = Uri.parse(trimmed);
      if (!parsed.hasScheme || parsed.host.isEmpty) {
        return AppConstants.fallbackSiteUrl;
      }

      final normalisedPath = parsed.path.isEmpty
          ? '/'
          : (parsed.path.endsWith('/') ? parsed.path : '${parsed.path}/');

      return parsed
          .replace(
            path: normalisedPath,
            queryParameters: const {},
            fragment: null,
          )
          .toString();
    } catch (_) {
      return AppConstants.fallbackSiteUrl;
    }
  }

  void reload() {
    controller.reload();
    setState(loading: true, error: false, loadingTimedOut: false);
  }

  void updateConnectivity(bool online) {
    isOffline = !online;
    showOfflineBanner = isOffline;
    if (online) {
      showOfflineBanner = false;
    }
  }

  void dispose() {
    _loadingTimer?.cancel();
    stateNotifier.dispose();
    _downloadService.dispose();
  }

  void _injectLinkInterceptor() {
    controller.runJavaScript('''
      document.addEventListener('click', function(e) {
        var target = e.target;
        while (target && target.nodeName !== 'A') {
          target = target.parentElement;
          if (!target) break;
        }

        if (target && target.href) {
          try {
            var url = new URL(target.href);
            if (url.protocol !== 'http:' && url.protocol !== 'https:' &&
                url.protocol !== '${siteOrigin.scheme}:') {
              e.preventDefault();
              e.stopImmediatePropagation();
              e.stopPropagation();
              LinkInterceptor.postMessage(target.href);
              return false;
            }
          } catch (error) {}
        }
      }, true);

      var originalLocationAssign = window.location.assign;
      var originalLocationReplace = window.location.replace;
      var originalLocationHrefSet = Object.getOwnPropertyDescriptor(Window.prototype, 'location').set;

      window.location.assign = function(url) {
        try {
          var parsedUrl = new URL(url, window.location.href);
          if (parsedUrl.protocol !== 'http:' && parsedUrl.protocol !== 'https:' &&
              parsedUrl.protocol !== '${siteOrigin.scheme}:') {
            LinkInterceptor.postMessage(parsedUrl.href);
            return;
          }
        } catch (error) {}
        return originalLocationAssign.call(this, url);
      };

      window.location.replace = function(url) {
        try {
          var parsedUrl = new URL(url, window.location.href);
          if (parsedUrl.protocol !== 'http:' && parsedUrl.protocol !== 'https:' &&
              parsedUrl.protocol !== '${siteOrigin.scheme}:') {
            LinkInterceptor.postMessage(parsedUrl.href);
            return;
          }
        } catch (error) {}
        return originalLocationReplace.call(this, url);
      };

      Object.defineProperty(window.location, 'href', {
        set: function(url) {
          try {
            var parsedUrl = new URL(url, window.location.href);
            if (parsedUrl.protocol !== 'http:' && parsedUrl.protocol !== 'https:' &&
                parsedUrl.protocol !== '${siteOrigin.scheme}:') {
              LinkInterceptor.postMessage(parsedUrl.href);
              return;
            }
          } catch (error) {}
          return originalLocationHrefSet.call(this, url);
        },
        get: originalLocationHrefSet.get
      });

      var originalWindowOpen = window.open;
      window.open = function(url, target, features) {
        if (url) {
          try {
            var parsedUrl = new URL(url, window.location.href);
            if (parsedUrl.protocol !== 'http:' && parsedUrl.protocol !== 'https:' &&
                parsedUrl.protocol !== '${siteOrigin.scheme}:') {
              LinkInterceptor.postMessage(parsedUrl.href);
              return null;
            }
          } catch (error) {}
        }
        return originalWindowOpen.call(this, url, target, features);
      };
    ''');
  }
}