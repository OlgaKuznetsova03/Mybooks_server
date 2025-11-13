import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';
import 'package:webview_flutter_wkwebview/webview_flutter_wkwebview.dart';

import 'services/reward_ads_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ReadTogetherApp());
}

class ReadTogetherApp extends StatelessWidget {
  const ReadTogetherApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Калейдоскоп книг',
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF40535c),
        useMaterial3: true,
      ),
      debugShowCheckedModeBanner: false,
      home: const MainWebViewPage(),
    );
  }
}

class MainWebViewPage extends StatefulWidget {
  const MainWebViewPage({super.key});

  @override
  State<MainWebViewPage> createState() => _MainWebViewPageState();
}

class _MainWebViewPageState extends State<MainWebViewPage> {
  static const String _fallbackSiteUrl = 'https://kalejdoskopknig.ru/';
  static const String _defaultSiteUrl = String.fromEnvironment(
    'MYBOOKS_SITE_URL',
    defaultValue: _fallbackSiteUrl,
  );
  static const String _defaultClientHeader = String.fromEnvironment(
    'MYBOOKS_APP_HEADER',
    defaultValue: 'X-MyBooks-Client',
  );
  static const String _defaultClientId = String.fromEnvironment(
    'MYBOOKS_APP_CLIENT_ID',
    defaultValue: 'mybooks-flutter',
  );

  late final WebViewController _controller;
  late final Uri _siteOrigin;
  late final String _startUrl;
  late final RewardAdsService _rewardAdsService;

  bool _loading = true;
  bool _rewardLoading = false;

  @override
  void initState() {
    super.initState();

    _startUrl = _prepareStartUrl(_defaultSiteUrl);
    _siteOrigin = Uri.parse(_startUrl);
    _rewardAdsService = RewardAdsService(
      siteOrigin: _siteOrigin,
      clientHeader: _defaultClientHeader,
      clientId: _defaultClientId,
    );

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
          onPageStarted: (_) => setState(() => _loading = true),
          onPageFinished: (_) => setState(() => _loading = false),
          onWebResourceError: (_) => setState(() => _loading = false),
          onNavigationRequest: _handleNavigationRequest,
        ),
      );

    if (controller.platform is AndroidWebViewController) {
      final android = controller.platform as AndroidWebViewController;
      android
        ..setMediaPlaybackRequiresUserGesture(false)
        ..setOnShowFileSelector(_onShowFileSelector);
    }

    _controller = controller;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _checkTermsAndLoad();
    });
  }

  @override
  void dispose() {
    _rewardAdsService.dispose();
    super.dispose();
  }

  NavigationDecision _handleNavigationRequest(NavigationRequest request) {
    final uri = Uri.tryParse(request.url);
    if (uri == null) {
      return NavigationDecision.navigate;
    }

    if (_isSameOrigin(uri)) {
      if (_shouldInterceptDownload(uri)) {
        unawaited(_startDownload(uri));
        return NavigationDecision.prevent;
      }
      return NavigationDecision.navigate;
    }

    if (uri.scheme == 'http' || uri.scheme == 'https') {
      return NavigationDecision.prevent;
    }

    return NavigationDecision.navigate;
  }

  bool _isSameOrigin(Uri uri) {
    if (uri.host.isEmpty) {
      return true;
    }

    if (uri.host.toLowerCase() != _siteOrigin.host.toLowerCase()) {
      return false;
    }

    if (_siteOrigin.hasPort && uri.port != _siteOrigin.port) {
      return false;
    }

    return true;
  }

  String _prepareStartUrl(String rawUrl) {
    final trimmed = rawUrl.trim();
    if (trimmed.isEmpty) {
      return _fallbackSiteUrl;
    }

    try {
      final parsed = Uri.parse(trimmed);
      if (!parsed.hasScheme || parsed.host.isEmpty) {
        return _fallbackSiteUrl;
      }

      final normalisedPath = parsed.path.isEmpty
          ? '/'
          : (parsed.path.endsWith('/') ? parsed.path : '${parsed.path}/');

      return parsed
          .replace(path: normalisedPath, queryParameters: const {}, fragment: null)
          .toString();
    } catch (_) {
      return _fallbackSiteUrl;
    }
  }

  Future<List<String>> _onShowFileSelector(FileSelectorParams params) async {
    FileType type = FileType.any;
    List<String>? customExt;

    if (params.acceptTypes.isNotEmpty) {
      final accepts = params.acceptTypes.map((e) => e.toLowerCase()).toList();
      if (accepts.any((e) => e.contains('image'))) {
        type = FileType.image;
      } else if (accepts.any((e) => e.contains('video'))) {
        type = FileType.video;
      } else if (accepts.any((e) => e.contains('audio'))) {
        type = FileType.audio;
      } else if (accepts.any((e) => e.contains('.'))) {
        type = FileType.custom;
        customExt = accepts
            .expand((e) => e.split(','))
            .map((e) => e.replaceAll('.', '').trim())
            .where((e) => e.isNotEmpty)
            .toList();
      }
    }

    final result = await FilePicker.platform.pickFiles(
      allowMultiple: _shouldAllowMultiple(params),
      type: type,
      allowedExtensions: customExt,
      withData: true,
    );

    if (result == null) return <String>[];

    final List<String> paths = [];
    final tempDir = await getTemporaryDirectory();
    for (final f in result.files) {
      if (f.path != null && f.path!.isNotEmpty) {
        paths.add(_normalizeForWebView(f.path!));
        continue;
      }

      final targetFile = await _createTempFile(tempDir.path, f.name, f.extension);

      if (f.bytes != null) {
        await targetFile.writeAsBytes(f.bytes!, flush: true);
        paths.add(_normalizeForWebView(targetFile.path));
        continue;
      }

      final stream = f.readStream;
      if (stream != null) {
        final sink = targetFile.openWrite();
        await stream.pipe(sink);
        await sink.flush();
        await sink.close();
        paths.add(_normalizeForWebView(targetFile.path));
      }
    }
    return paths;
  }

  String _normalizeForWebView(String rawPath) {
    final trimmed = rawPath.trim();
    if (trimmed.isEmpty) {
      return trimmed;
    }

    if (trimmed.contains('://')) {
      return trimmed;
    }

    return Uri.file(trimmed).toString();
  }

  Future<File> _createTempFile(
    String dirPath,
    String? originalName,
    String? fallbackExtension,
  ) async {
    final sanitizedName = _sanitizeFileName(originalName);
    final generatedName =
        sanitizedName ?? _buildFallbackName(fallbackExtension: fallbackExtension);
    final uniqueName = '${DateTime.now().microsecondsSinceEpoch}_${generatedName}';
    final file = File('$dirPath/$uniqueName');
    if (!await file.exists()) {
      await file.create(recursive: true);
    }
    return file;
  }

  String? _sanitizeFileName(String? original) {
    final trimmed = original?.trim() ?? '';
    if (trimmed.isEmpty) {
      return null;
    }
    final sanitized = trimmed.replaceAll(RegExp(r'[\\/:*?"<>|]'), '_');
    return sanitized.isEmpty ? null : sanitized;
  }

  String _buildFallbackName({String prefix = 'upload', String? fallbackExtension}) {
    final ext = fallbackExtension?.trim();
    if (ext == null || ext.isEmpty) {
      return prefix;
    }
    final sanitizedExt = ext.replaceAll(RegExp(r'[^A-Za-z0-9]'), '');
    if (sanitizedExt.isEmpty) {
      return prefix;
    }
    return '$prefix.$sanitizedExt';
  }

  bool _shouldAllowMultiple(FileSelectorParams params) {
    final dynamic dynamicParams = params;

    try {
      final value = dynamicParams.allowMultiple;
      if (value is bool) {
        return value;
      }
    } catch (_) {}

    try {
      final mode = dynamicParams.mode;
      if (mode != null) {
        final modeString = mode.toString().toLowerCase();
        if (modeString.contains('multiple')) {
          return true;
        }
      }
    } catch (_) {}

    return false;
  }

  Future<bool> _handleBack() async {
    if (await _controller.canGoBack()) {
      _controller.goBack();
      return false;
    }
    return true;
  }

  Future<Map<String, String>> _collectCookies() async {
    try {
      final rawResult = await _controller.runJavaScriptReturningResult('document.cookie');
      if (rawResult == null) {
        return {};
      }

      String? cookieString;
      if (rawResult is String) {
        cookieString = rawResult;
      } else {
        cookieString = rawResult.toString();
      }

      if (cookieString == null) {
        return {};
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
    } catch (error) {
      debugPrint('Не удалось получить cookies: $error');
      return {};
    }
  }

  Future<void> _checkTermsAndLoad() async {
    final accepted = await _ensureTermsAccepted();
    if (!mounted) return;
    if (accepted) {
      _controller.loadRequest(Uri.parse(_startUrl));
    }
  }

  Future<bool> _ensureTermsAccepted() async {
    try {
      final marker = await _termsAcceptanceMarker();
      if (await marker.exists()) {
        return true;
      }
    } catch (error) {
      debugPrint('Не удалось проверить соглашение с правилами: $error');
      return true;
    }

    while (mounted) {
      final accepted = await showDialog<bool>(
        context: context,
        barrierDismissible: false,
        builder: (context) {
          final theme = Theme.of(context);
          return AlertDialog(
            title: const Text('Согласие с правилами'),
            content: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    'Перед использованием приложения подтвердите, что вы ознакомились '
                    'и согласны с правилами сервиса «Калейдоскоп книг».',
                    style: theme.textTheme.bodyMedium,
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'Полные правила доступны на сайте:',
                    style: theme.textTheme.bodySmall,
                  ),
                  const SizedBox(height: 8),
                  SelectableText(
                    '${_siteOrigin.scheme}://${_siteOrigin.host}/rules/',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.primary,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Нажимая «Принимаю правила», вы подтверждаете, что ознакомились '
                    'с документом и обязуетесь соблюдать требования сервиса.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(context).pop(false),
                child: const Text('Закрыть приложение'),
              ),
              FilledButton(
                onPressed: () => Navigator.of(context).pop(true),
                child: const Text('Принимаю правила'),
              ),
            ],
          );
        },
      );

      if (accepted == true) {
        try {
          final marker = await _termsAcceptanceMarker();
          if (!await marker.exists()) {
            await marker.create(recursive: true);
          }
          await marker.writeAsString(DateTime.now().toIso8601String());
        } catch (error) {
          debugPrint('Не удалось сохранить подтверждение правил: $error');
        }
        return true;
      }

      if (accepted == false) {
        await _closeApplication();
        return false;
      }
    }

    return false;
  }

  Future<File> _termsAcceptanceMarker() async {
    final directory = await getApplicationSupportDirectory();
    return File('${directory.path}/mybooks_terms_v1.txt');
  }

  Future<void> _closeApplication() async {
    if (Platform.isAndroid) {
      await SystemNavigator.pop();
    } else {
      exit(0);
    }
  }

  bool _shouldInterceptDownload(Uri uri) {
    final path = uri.path;
    if (path == '/accounts/me/print/monthly/' || path == '/accounts/me/print/monthly') {
      return true;
    }

    final segments = uri.pathSegments;
    if (segments.length >= 3 && segments.first == 'books' && segments.last == 'print-review') {
      return true;
    }

    return false;
  }

  Future<void> _startDownload(Uri uri) async {
    if (!mounted) return;
    
    await showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Row(
            children: [
              Icon(Icons.download, color: Colors.deepPurple),
              SizedBox(width: 8),
              Text('Скачивание файлов'),
            ],
          ),
          content: const Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Скачивание файлов доступно только в веб-версии сайта.',
                style: TextStyle(fontSize: 16),
              ),
              SizedBox(height: 16),
              Text(
                'Чтобы скачать файлы:',
                style: TextStyle(fontWeight: FontWeight.w500),
              ),
              SizedBox(height: 8),
              Text('1. Откройте браузер на вашем устройстве'),
              Text('2. Перейдите на сайт kalejdoskopknig.ru'),
              Text('3. Войдите в свой аккаунт'),
              Text('4. Скачайте нужные файлы'),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Закрыть'),
            ),
            FilledButton(
              onPressed: () {
                Navigator.of(context).pop();
                _openInBrowser();
              },
              child: const Text('Открыть в браузере'),
            ),
          ],
        );
      },
    );
  }

  Future<void> _openInBrowser() async {
    try {
      final url = _startUrl;
      if (await canLaunchUrl(Uri.parse(url))) {
        await launchUrl(
          Uri.parse(url),
          mode: LaunchMode.externalApplication,
        );
      } else {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Не удалось открыть браузер')),
        );
      }
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Ошибка при открытии браузера: $error')),
      );
    }
  }

  Future<void> _openRewardPanel() async {
    if (_rewardLoading) return;

    setState(() => _rewardLoading = true);
    try {
      final cookies = await _collectCookies();
      final config = await _rewardAdsService.fetchConfig(cookies: cookies);

      if (!config.isReady) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Рекламный модуль временно отключён.'),
          ),
        );
        return;
      }

      if (!mounted) return;
      final result = await showModalBottomSheet<RewardAdClaimResult>(
        context: context,
        isScrollControlled: true,
        builder: (context) => RewardAdSheet(
          config: config,
          service: _rewardAdsService,
          cookieProvider: _collectCookies,
        ),
      );

      if (result != null && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              'Начислено ${result.coinsAwarded} монет.',
            ),
          ),
        );
      }
    } on RewardAdsException catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.message)),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Не удалось открыть панель рекламы: $error')),
      );
    } finally {
      if (mounted) {
        setState(() => _rewardLoading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvoked: (bool didPop) async {
        if (!didPop) {
          final shouldPop = await _handleBack();
          if (shouldPop && mounted) {
            Navigator.of(context).pop();
          }
        }
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Мир в книгах'),
          backgroundColor: Colors.white,
          foregroundColor: const Color.fromARGB(255,174,181,184),
          elevation: 4,
          actions: [
            _rewardLoading
                ? const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 16.0),
                    child: SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    ),
                  )
                : Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8.0),
                    child: TextButton.icon(
                      onPressed: _openRewardPanel,
                      style: TextButton.styleFrom(
                        foregroundColor: Colors.white,
                        backgroundColor: const Color.fromARGB(255, 140, 143, 144),
                      ),
                      icon: const Icon(Icons.play_circle_outline, size: 18),
                      label: const Text('20 монет'),
                    ),
                  ),
          ],
        ),
        body: Stack(
          children: [
            WebViewWidget(controller: _controller),
            if (_loading) const Center(child: CircularProgressIndicator()),
          ],
        ),
      ),
    );
  }
}

class RewardAdSheet extends StatefulWidget {
  const RewardAdSheet({
    super.key,
    required this.config,
    required this.service,
    required this.cookieProvider,
  });

  final RewardAdConfig config;
  final RewardAdsService service;
  final Future<Map<String, String>> Function() cookieProvider;

  @override
  State<RewardAdSheet> createState() => _RewardAdSheetState();
}

class _RewardAdSheetState extends State<RewardAdSheet> {
  bool _claiming = false;
  RewardAdsException? _error;

  Future<void> _claimReward() async {
    setState(() {
      _claiming = true;
      _error = null;
    });

    try {
      final cookies = await widget.cookieProvider();
      final result = await widget.service.claimReward(
        config: widget.config,
        cookies: cookies,
      );
      if (!mounted) return;
      Navigator.of(context).pop(result);
    } on RewardAdsException catch (error) {
      if (!mounted) return;
      setState(() => _error = error);
    } catch (error) {
      if (!mounted) return;
      setState(
        () => _error = RewardAdsException(
          'Не удалось начислить монеты: $error',
          code: RewardAdsError.network,
        ),
      );
    } finally {
      if (mounted) {
        setState(() => _claiming = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: 24,
          right: 24,
          top: 24,
          bottom: MediaQuery.of(context).viewInsets.bottom + 24,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Рекламная награда', style: theme.textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(
              'Яндекс · ${widget.config.rewardAmount} ${widget.config.currency}',
              style: theme.textTheme.bodyMedium,
            ),
            const SizedBox(height: 8),
            Text(
              'Просмотрите рекламный ролик и подтвердите получение награды, '
              'чтобы монеты были начислены на счёт.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(
                _error!.message,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.error,
                ),
              ),
            ],
            const SizedBox(height: 16),
            if (kDebugMode)
              FilledButton.icon(
                onPressed: _claiming ? null : _claimReward,
                icon: _claiming
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Icon(Icons.play_circle_fill),
                label: const Text('Симулировать получение награды'),
              )
            else
              Text(
                'В релизной сборке интегрируйте SDK рекламы и вызывайте '
                'RewardAdsService.claimReward(...) после события rewarded. '
                'Эта панель служит для проверки конфигурации.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            const SizedBox(height: 16),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: _claiming ? null : () => Navigator.of(context).maybePop(),
                child: const Text('Закрыть'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}