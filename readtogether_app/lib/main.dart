import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:file_picker/file_picker.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';
import 'package:webview_flutter_wkwebview/webview_flutter_wkwebview.dart';
import 'package:flutter/foundation.dart';

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
      home: const KaleidoscopeHome(),
    );
  }
}

class KaleidoscopeHome extends StatefulWidget {
  const KaleidoscopeHome({super.key});

  @override
  State<KaleidoscopeHome> createState() => _KaleidoscopeHomeState();
}

class _KaleidoscopeHomeState extends State<KaleidoscopeHome> {
  final ValueNotifier<bool> _isOnlineNotifier = ValueNotifier(true);
  final Connectivity _connectivity = Connectivity();

  StreamSubscription<dynamic>? _connectivitySubscription;

  @override
  void initState() {
    super.initState();
    _initConnectivity();
  }

  Future<void> _initConnectivity() async {
    try {
      final result = await _connectivity.checkConnectivity();
      _handleConnectivityResult(result);
    } catch (_) {}

    _connectivitySubscription =
        _connectivity.onConnectivityChanged.listen(_handleConnectivityResult);
  }

  void _handleConnectivityResult(dynamic result) {
    bool hasConnection = true;
    if (result is ConnectivityResult) {
      hasConnection = result != ConnectivityResult.none;
    } else if (result is List<ConnectivityResult>) {
      hasConnection = result.any((e) => e != ConnectivityResult.none);
    }
    if (_isOnlineNotifier.value != hasConnection) {
      _isOnlineNotifier.value = hasConnection;
    }
  }

  @override
  void dispose() {
    _connectivitySubscription?.cancel();
    _isOnlineNotifier.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MainWebViewPage(onlineNotifier: _isOnlineNotifier);
  }
}

class MainWebViewPage extends StatefulWidget {
  const MainWebViewPage({super.key, this.onlineNotifier});

  final ValueListenable<bool>? onlineNotifier;

  @override
  State<MainWebViewPage> createState() => _MainWebViewPageState();
}

class _MainWebViewPageState extends State<MainWebViewPage> {
  static const String _fallbackSiteUrl = 'https://kalejdoskopknig.ru/';
  static const String _defaultSiteUrl = String.fromEnvironment(
    'MYBOOKS_SITE_URL',
    defaultValue: _fallbackSiteUrl,
  );

  late final WebViewController _controller;
  late final Uri _siteOrigin;
  late final String _startUrl;
  late final OfflineNotesStorage _offlineNotesStorage;
  final TextEditingController _noteController = TextEditingController();
  final HttpClient _httpClient = HttpClient();
  List<OfflineNote> _offlineNotes = [];
  bool _savingNote = false;
  ValueListenable<bool>? _connectivityListenable;

  bool _loading = true;
  bool _webViewError = false;
  bool _isOffline = false;
  int _coinsBalance = 0;
  bool _rewardInProgress = false;
  Timer? _loadingTimer;
  static const int _loadingTimeoutSeconds = 5;
  bool _loadingTimedOut = false;
  final bool _isYandexAdEnabled = true;
  FinishCelebrationData? _celebrationData;
  bool _celebrationLoading = false;

  @override
  void initState() {
    super.initState();

    _startUrl = _prepareStartUrl(_defaultSiteUrl);
    _siteOrigin = Uri.parse(_startUrl);
    _offlineNotesStorage = OfflineNotesStorage();
    _attachConnectivity(widget.onlineNotifier);
    _loadOfflineNotes();

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
          onPageStarted: (_) => _handlePageStarted(),
          onPageFinished: (_) => _handlePageFinished(),
          onWebResourceError: (WebResourceError error) => _handleWebResourceError(error),
          onNavigationRequest: _handleNavigationRequest,
        ),
      );

    controller.addJavaScriptChannel(
      'ReadTogetherApp',
      onMessageReceived: _handleJavaScriptMessage,
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
  void didUpdateWidget(covariant MainWebViewPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.onlineNotifier != widget.onlineNotifier) {
      _attachConnectivity(widget.onlineNotifier);
    }
  }

  @override
  void dispose() {
    _detachConnectivity();
    _loadingTimer?.cancel();
    _noteController.dispose();
    super.dispose();
  }

  void _attachConnectivity(ValueListenable<bool>? notifier) {
    _detachConnectivity();
    _connectivityListenable = notifier;
    if (notifier != null) {
      _isOffline = !notifier.value;
      notifier.addListener(_handleConnectivityChange);
    }
  }

  void _detachConnectivity() {
    _connectivityListenable?.removeListener(_handleConnectivityChange);
    _connectivityListenable = null;
  }

  void _handlePageStarted() {
    setState(() {
      _loading = true;
      _webViewError = false;
      _loadingTimedOut = false;
    });

    _loadingTimer?.cancel();
    _loadingTimer = Timer(
      const Duration(seconds: _loadingTimeoutSeconds),
      _handleLoadingTimeout,
    );
  }

  void _handlePageFinished() {
    _loadingTimer?.cancel();
    setState(() {
      _loading = false;
      _webViewError = false;
      _loadingTimedOut = false;
    });
  }

  void _handleWebResourceError(WebResourceError error) {
    _loadingTimer?.cancel();
    setState(() {
      _loading = false;

      // Игнорируем ошибки загрузки вспомогательных ресурсов (например, рекламных
      // блоков), чтобы не показывать экран «Не удалось загрузить приложение»
      // при успешной загрузке основной страницы.
      final isMainFrameError = error.isForMainFrame ?? true;
      _webViewError = isMainFrameError;
    });
  }

  void _handleLoadingTimeout() {
    if (!mounted) return;

    setState(() {
      _loadingTimedOut = true;
      _loading = false;
    });
  }

  void _handleConnectivityChange() {
    final notifier = _connectivityListenable;
    if (notifier == null || !mounted) return;
    final offline = !notifier.value;
    if (offline == _isOffline) return;
    setState(() => _isOffline = offline);
    if (!offline && (_webViewError || _loadingTimedOut)) {
      _reloadWebView();
    }
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
      unawaited(_launchExternalUrl(uri));
      return NavigationDecision.prevent;
    }

    if (uri.scheme == 'tel' || uri.scheme == 'mailto' || uri.scheme == 'sms') {
      unawaited(_launchExternalUrl(uri));
      return NavigationDecision.prevent;
    }

    if (uri.scheme == 'data' || uri.scheme == 'blob' || uri.scheme == 'about') {
      return NavigationDecision.navigate;
    }

    debugPrint('Блокируем навигацию для схемы: ${uri.scheme}');
    return NavigationDecision.prevent;
  }

  void _handleJavaScriptMessage(JavaScriptMessage message) {
    Map<String, dynamic>? payload;

    try {
      final decoded = jsonDecode(message.message);
      if (decoded is Map<String, dynamic>) {
        payload = decoded;
      } else if (decoded is Map) {
        payload = decoded.map((key, value) => MapEntry(key.toString(), value));
      }
    } catch (error) {
      debugPrint('Не удалось разобрать сообщение из WebView: $error');
    }

    if (payload == null) return;

    final rawType = payload['type'] ?? payload['event'];
    final type = rawType is String ? rawType.toLowerCase() : rawType?.toString().toLowerCase();
    if (type != 'book_finished' && type != 'bookfinished' && type != 'book-finished') {
      return;
    }

    unawaited(_handleFinishCelebration(payload));
  }

  Future<void> _handleFinishCelebration(Map<String, dynamic> payload) async {
    final apiUrl = payload['api_url'] ?? payload['apiUrl'] ?? payload['api'];
    final points = payload['points'] ?? payload['reward'] ?? payload['coins'];
    final fallbackReward = _buildRewardText(points, fallback: payload['rewardText'] as String?);
    final fallbackTitle = (payload['title'] ?? payload['bookTitle'])?.toString();
    final fallbackCover = (payload['cover'] ?? payload['cover_url'] ?? payload['coverUrl'])?.toString();

    if (apiUrl is String && apiUrl.trim().isNotEmpty) {
      final data = await _loadCelebrationFromApi(
        apiUrl,
        fallbackTitle: fallbackTitle,
        fallbackCover: fallbackCover,
        fallbackRewardText: fallbackReward,
      );

      if (!mounted || data == null) return;
      setState(() => _celebrationData = data);
      return;
    }

    final data = FinishCelebrationData(
      title: fallbackTitle ?? 'Книга прочитана',
      coverUrl: fallbackCover,
      rewardText: fallbackReward ?? '+1 к прочитанным книгам',
    );

    if (!mounted) return;
    setState(() => _celebrationData = data);
  }

  String? _buildRewardText(dynamic points, {String? fallback}) {
    if (fallback != null && fallback.trim().isNotEmpty) {
      return fallback;
    }

    if (points == null) return null;

    num? numericPoints;
    if (points is num) {
      numericPoints = points;
    } else {
      numericPoints = num.tryParse(points.toString());
    }

    if (numericPoints == null) return null;
    if (numericPoints == 1) {
      return '+1 к прочитанным книгам';
    }
    return '+${numericPoints.toString()} к книжному пути';
  }

  Future<FinishCelebrationData?> _loadCelebrationFromApi(
    String rawUrl, {
    String? fallbackTitle,
    String? fallbackCover,
    String? fallbackRewardText,
  }) async {
    if (_celebrationLoading) return null;
    setState(() => _celebrationLoading = true);

    try {
      final uri = _resolveApiUri(rawUrl);
      final request = await _httpClient.getUrl(uri);
      final response = await request.close();
      if (response.statusCode >= 200 && response.statusCode < 300) {
        final body = await response.transform(utf8.decoder).join();
        final decoded = jsonDecode(body);
        if (decoded is Map<String, dynamic>) {
          final title = (decoded['title'] ?? decoded['name'] ?? fallbackTitle)?.toString();
          final cover = (decoded['cover'] ?? decoded['cover_url'] ?? decoded['image'] ?? fallbackCover)?.toString();
          final points = decoded['points'] ?? decoded['reward'] ?? decoded['coins'];
          final rewardText = _buildRewardText(points, fallback: fallbackRewardText) ??
              fallbackRewardText ??
              '+1 к прочитанным книгам';

          return FinishCelebrationData(
            title: title ?? 'Книга прочитана',
            coverUrl: cover,
            rewardText: rewardText,
          );
        }
      }
    } catch (error) {
      debugPrint('Не удалось загрузить данные анимации: $error');
    } finally {
      if (mounted) {
        setState(() => _celebrationLoading = false);
      }
    }

    if (fallbackTitle != null || fallbackCover != null || fallbackRewardText != null) {
      return FinishCelebrationData(
        title: fallbackTitle ?? 'Книга прочитана',
        coverUrl: fallbackCover,
        rewardText: fallbackRewardText ?? '+1 к прочитанным книгам',
      );
    }
    return null;
  }

  Uri _resolveApiUri(String rawUrl) {
    final trimmed = rawUrl.trim();
    if (trimmed.isEmpty) return _siteOrigin;

    try {
      final parsed = Uri.parse(trimmed);
      if (parsed.hasScheme) {
        return parsed;
      }
      return _siteOrigin.resolve(trimmed);
    } catch (_) {
      return _siteOrigin;
    }
  }

  bool _isSameOrigin(Uri uri) {
    if (uri.host.isEmpty) {
      return true;
    }

    final currentHost = _siteOrigin.host.toLowerCase();
    final targetHost = uri.host.toLowerCase();

    if (targetHost != currentHost) {
      if (!targetHost.endsWith('.$currentHost')) {
        return false;
      }
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
          .replace(
            path: normalisedPath,
            queryParameters: const {},
            fragment: null,
          )
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
      try {
        await _controller.loadRequest(Uri.parse(_startUrl));
      } catch (error) {
        if (mounted) {
          setState(() {
            _webViewError = true;
            _loading = false;
          });
        }
        debugPrint('Ошибка загрузки WebView: $error');
      }
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

  Future<void> _startDownload(Uri uri) async {
    if (!mounted) return;

    final navigator = Navigator.of(context, rootNavigator: true);
    final progressDialog = showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => const DownloadProgressDialog(),
    );

    File? downloadedFile;
    Object? downloadError;
    try {
      downloadedFile = await _downloadPdf(uri);
    } catch (error) {
      downloadError = error;
    } finally {
      if (navigator.canPop()) {
        navigator.pop();
      }
      await progressDialog;
    }

    if (!mounted) return;

    if (downloadedFile != null) {
      final fileUri = Uri.file(downloadedFile.path).toString();
      if (await canLaunchUrl(Uri.parse(fileUri))) {
        await launchUrl(Uri.parse(fileUri));
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('PDF открывается...')),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('PDF сохранён в: ${downloadedFile.path}')),
        );
      }
    } else if (downloadError != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Не удалось скачать файл: $downloadError')),
      );
    }
  }

  Future<File> _downloadPdf(Uri uri) async {
    final client = HttpClient();
    try {
      final request = await client.getUrl(uri);
      final cookies = await _collectCookies();
      if (cookies.isNotEmpty) {
        request.headers.set(
          HttpHeaders.cookieHeader,
          cookies.entries.map((e) => '${e.key}=${e.value}').join('; '),
        );
      }
      final response = await request.close();
      if (response.statusCode != HttpStatus.ok) {
        throw HttpException('Код ответа: ${response.statusCode}');
      }
      final bytes = await consolidateHttpClientResponseBytes(response);
      final targetDir = await _resolveDownloadsDirectory();
      final fileName = _downloadFileName(uri);
      final file = File('${targetDir.path}/$fileName');
      await file.create(recursive: true);
      await file.writeAsBytes(bytes, flush: true);
      return file;
    } finally {
      client.close(force: true);
    }
  }

  Future<Directory> _resolveDownloadsDirectory() async {
    if (!kIsWeb && (Platform.isMacOS || Platform.isWindows || Platform.isLinux)) {
      final downloads = await getDownloadsDirectory();
      if (downloads != null) {
        return downloads;
      }
    }
    return getApplicationDocumentsDirectory();
  }

  String _downloadFileName(Uri uri) {
    final rawName = uri.pathSegments.isNotEmpty ? uri.pathSegments.last : 'document.pdf';
    final sanitized = _sanitizeFileName(rawName) ?? 'document.pdf';
    if (sanitized.toLowerCase().endsWith('.pdf')) {
      return sanitized;
    }
    return '$sanitized.pdf';
  }

  Future<void> _launchExternalUrl(Uri uri) async {
    try {
      if (await canLaunchUrl(uri)) {
        await launchUrl(
          uri,
          mode: LaunchMode.externalApplication,
          webOnlyWindowName: '_blank',
        );
      } else {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Не удалось открыть ссылку: ${uri.toString()}')),
        );
      }
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Ошибка при открытии ссылки: $error')),
      );
    }
  }

  void _reloadWebView() {
    if (!mounted) return;
    setState(() {
      _webViewError = false;
      _loadingTimedOut = false;
    });
    _controller.reload();
  }

  Future<void> _loadOfflineNotes() async {
    try {
      final stored = await _offlineNotesStorage.readNotes();
      if (!mounted) return;
      setState(() => _offlineNotes = stored);
    } catch (_) {}
  }

  Future<void> _handleSaveOfflineNote() async {
    final text = _noteController.text.trim();
    if (text.isEmpty || _savingNote) {
      return;
    }

    setState(() => _savingNote = true);
    try {
      final note = OfflineNote(
        id: DateTime.now().microsecondsSinceEpoch.toString(),
        text: text,
        createdAt: DateTime.now(),
      );
      final updated = [note, ..._offlineNotes];
      await _offlineNotesStorage.writeNotes(updated);
      if (!mounted) return;
      setState(() {
        _offlineNotes = updated;
        _noteController.clear();
      });
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Не удалось сохранить заметку: $error')),
      );
    } finally {
      if (mounted) {
        setState(() => _savingNote = false);
      }
    }
  }

  Future<void> _handleDeleteOfflineNote(String id) async {
    final updated = _offlineNotes.where((note) => note.id != id).toList();
    setState(() => _offlineNotes = updated);
    try {
      await _offlineNotesStorage.writeNotes(updated);
    } catch (_) {}
  }

  String _formatNoteDate(DateTime date) {
    final twoDigits = (int value) => value.toString().padLeft(2, '0');
    final day = twoDigits(date.day);
    final month = twoDigits(date.month);
    final hours = twoDigits(date.hour);
    final minutes = twoDigits(date.minute);
    return '$day.$month.${date.year} · $hours:$minutes';
  }

  Widget _buildOfflineNotesPanel() {
    final theme = Theme.of(context);
    final recentNotes = _offlineNotes.take(3).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Запишите идею', style: theme.textTheme.titleMedium),
        const SizedBox(height: 8),
        Text(
          'Последние действия уже сохранены на устройстве. '
          'Добавьте заметку — мы подскажем, когда её можно синхронизировать.',
          style: theme.textTheme.bodySmall,
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _noteController,
          minLines: 2,
          maxLines: 4,
          decoration: InputDecoration(
            hintText: 'Напишите короткую заметку о чтении или идею для марафона',
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(16)),
          ),
        ),
        const SizedBox(height: 8),
        FilledButton.icon(
          onPressed: _savingNote ? null : _handleSaveOfflineNote,
          icon: _savingNote
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                )
              : const Icon(Icons.edit_note),
          label: Text(_savingNote ? 'Сохраняем…' : 'Сохранить заметку'),
        ),
        const SizedBox(height: 16),
        Text('Сохранённые заметки', style: theme.textTheme.titleSmall),
        const SizedBox(height: 8),
        if (recentNotes.isEmpty)
          Text(
            'Здесь появятся ваши заметки. Они будут синхронизированы, когда связь восстановится.',
            style: theme.textTheme.bodySmall,
          )
        else
          ...recentNotes.map(
            (note) => Card(
              margin: const EdgeInsets.only(bottom: 8),
              child: ListTile(
                title: Text(
                  note.text,
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                ),
                subtitle: Text('Создано ${_formatNoteDate(note.createdAt)}'),
                trailing: IconButton(
                  tooltip: 'Удалить',
                  icon: const Icon(Icons.delete_outline),
                  onPressed: () => _handleDeleteOfflineNote(note.id),
                ),
              ),
            ),
          ),
      ],
    );
  }

  Widget _buildStatusOverlay({
    required IconData icon,
    required String title,
    required String description,
    VoidCallback? onPressed,
    String actionLabel = 'Повторить',
    Widget? extraContent,
  }) {
    final theme = Theme.of(context);
    return Material(
      color: theme.colorScheme.surface.withOpacity(0.98),
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Icon(icon, size: 48, color: theme.colorScheme.primary),
                const SizedBox(height: 16),
                Text(
                  title,
                  style: theme.textTheme.titleLarge,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 12),
                Text(
                  description,
                  style: theme.textTheme.bodyMedium,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: onPressed,
                  child: Text(actionLabel),
                ),
                if (extraContent != null) ...[
                  const SizedBox(height: 24),
                  extraContent,
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildRewardBanner() {
    if (!_isYandexAdEnabled) {
      return const SizedBox.shrink();
    }

    return Container(
      width: double.infinity,
      height: 50,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border(bottom: BorderSide(color: Colors.grey.shade300, width: 1)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            'Реклама Яндекс · 20 монет',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              color: const Color(0xFF40535c),
              fontWeight: FontWeight.w500,
            ),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: const Color(0xFF40535c),
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 6),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            ),
            onPressed: _rewardInProgress ? null : _handleWatchYandexAd,
            child: _rewardInProgress
                ? const SizedBox(height: 16, width: 16, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Смотреть', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w500)),
          ),
        ],
      ),
    );
  }

  Future<void> _handleWatchYandexAd() async {
    if (_rewardInProgress || !_isYandexAdEnabled) return;
    setState(() => _rewardInProgress = true);
    try {
      final rewarded = await showDialog<bool>(
        context: context,
        barrierDismissible: false,
        builder: (_) => const YandexAdDialog(),
      ).timeout(const Duration(seconds: 30), onTimeout: () => false);
      if (rewarded == true && mounted) {
        setState(() => _coinsBalance += 20);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Спасибо! На ваш счёт зачислено 20 монет.')),
        );
      } else if (rewarded == false && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Не удалось показать рекламу. Попробуйте позже.')),
        );
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Ошибка при показе рекламы: $error')),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _rewardInProgress = false);
     }
    }
  }

  void _handleCelebrationClosed() {
    if (!mounted) return;
    setState(() => _celebrationData = null);
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
        backgroundColor: Colors.white,
        body: Column(
          children: [
            // Рекламный баннер Яндекс - теперь в самом верху
            SafeArea(
              bottom: false,
              child: _buildRewardBanner(),
            ),
            
            // Основной контент с WebView
            Expanded(
              child: Stack(
                clipBehavior: Clip.none,
                children: [
                  Positioned.fill(child: WebViewWidget(controller: _controller)),

                  if (_loading) const Center(child: CircularProgressIndicator()),
                  if (_loadingTimedOut || _isOffline)
                    Positioned.fill(
                      child: _buildStatusOverlay(
                        icon: _isOffline ? Icons.wifi_off : Icons.timer_off,
                        title: _isOffline ? 'Вы оффлайн' : 'Долгая загрузка',
                        description: _isOffline
                            ? 'Последняя версия приложения сохранена. Мы автоматически обновим страницу, как только интернет появится.'
                            : 'Сайт загружается дольше обычного. Проверьте соединение или попробуйте позже.',
                        onPressed: _reloadWebView,
                        actionLabel: _isOffline ? 'Проверить соединение' : 'Перезагрузить',
                        extraContent: _buildOfflineNotesPanel(),
                      ),
                    ),
                  if (_webViewError && !_isOffline && !_loadingTimedOut)
                    Positioned.fill(
                      child: _buildStatusOverlay(
                        icon: Icons.cloud_off,
                        title: 'Не удалось загрузить приложение',
                        description:
                            'Сервис временно недоступен. Попробуйте обновить страницу или вернитесь позже.',
                        onPressed: _reloadWebView,
                        actionLabel: 'Перезагрузить вкладку',
                      ),
                    ),
                  if (_celebrationData != null)
                    Positioned.fill(
                      child: FinishBookCelebration(
                        data: _celebrationData!,
                        onClose: _handleCelebrationClosed,
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// Вынесенные отдельно классы (должны быть на верхнем уровне)

class DownloadProgressDialog extends StatelessWidget {
  const DownloadProgressDialog({super.key});

  @override
  Widget build(BuildContext context) {
    return const AlertDialog(
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          CircularProgressIndicator(),
          SizedBox(height: 16),
          Text('Скачиваем PDF…'),
        ],
      ),
    );
  }
}

class YandexAdDialog extends StatefulWidget {
  const YandexAdDialog({super.key});

  @override
  State<YandexAdDialog> createState() => _YandexAdDialogState();
}

class _YandexAdDialogState extends State<YandexAdDialog> {
  static const _totalDuration = Duration(seconds: 6);
  static const _labelColor = Color.fromARGB(255, 174, 181, 184);
  Timer? _timer;
  double _progress = 0;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(milliseconds: 120), (timer) {
      final step = 120 / _totalDuration.inMilliseconds;
      setState(() {
        _progress = (_progress + step).clamp(0.0, 1.0);
      });
      if (_progress >= 1) {
        timer.cancel();
        if (mounted) {
          Navigator.of(context).pop(true);
        }
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Смотрим рекламу от Яндекс'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Подождите несколько секунд — после просмотра монеты поступят на ваш счёт.',
            style: TextStyle(color: _labelColor),
          ),
          const SizedBox(height: 16),
          LinearProgressIndicator(value: _progress),
          const SizedBox(height: 12),
          Text('${(_progress * 100).clamp(0, 100).toStringAsFixed(0)} %'),
        ],
      ),
    );
  }
}

class FinishCelebrationData {
  FinishCelebrationData({
    required this.title,
    required this.rewardText,
    this.coverUrl,
  });

  final String title;
  final String rewardText;
  final String? coverUrl;
}

class FinishBookCelebration extends StatefulWidget {
  const FinishBookCelebration({
    super.key,
    required this.data,
    required this.onClose,
  });

  final FinishCelebrationData data;
  final VoidCallback onClose;

  @override
  State<FinishBookCelebration> createState() => _FinishBookCelebrationState();
}

class _FinishBookCelebrationState extends State<FinishBookCelebration>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _overlay;
  late final Animation<double> _glow;
  late final Animation<double> _edge;
  late final Animation<double> _trophyScale;
  late final Animation<Offset> _textSlide;
  late final List<_StarSpec> _stars;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 6000),
    )..forward();

    _overlay = CurvedAnimation(
      parent: _controller,
      curve: const Interval(0, 0.25, curve: Curves.easeOut),
    );
    _glow = CurvedAnimation(
      parent: _controller,
      curve: const Interval(0.1, 0.45, curve: Curves.easeOut),
    );
    _edge = CurvedAnimation(
      parent: _controller,
      curve: const Interval(0.2, 0.7, curve: Curves.easeInOut),
    );
    _trophyScale = CurvedAnimation(
      parent: _controller,
      curve: const Interval(0.55, 0.95, curve: Curves.elasticOut),
    );
    _textSlide = Tween(begin: const Offset(0, 0.25), end: Offset.zero).animate(
      CurvedAnimation(
        parent: _controller,
        curve: const Interval(0.65, 1, curve: Curves.easeOut),
      ),
    );

    _stars = [
      const _StarSpec(alignment: Alignment(-0.8, -0.05), start: 0.08, end: 0.9, size: 18, rotation: -0.35, horizontalDrift: 12, verticalLift: -36, wobbleTurns: 1.4),
      const _StarSpec(alignment: Alignment(0.85, 0.05), start: 0.06, end: 0.92, size: 18, rotation: 0.4, horizontalDrift: 10, verticalLift: -34, wobbleTurns: 1.6),
      const _StarSpec(alignment: Alignment(-0.5, -0.35), start: 0.12, end: 0.94, size: 22, rotation: 0.2, horizontalDrift: 8, verticalLift: -42, wobbleTurns: 1.2),
      const _StarSpec(alignment: Alignment(0.55, -0.3), start: 0.14, end: 0.96, size: 22, rotation: -0.15, horizontalDrift: 14, verticalLift: -40, wobbleTurns: 1.35),
      const _StarSpec(alignment: Alignment(-0.15, -0.55), start: 0.18, end: 0.98, size: 26, rotation: 0.1, horizontalDrift: 6, verticalLift: -44, wobbleTurns: 1.1),
      const _StarSpec(alignment: Alignment(0.2, 0.0), start: 0.22, end: 0.94, size: 16, rotation: -0.25, horizontalDrift: 10, verticalLift: -32, wobbleTurns: 1.8),
      const _StarSpec(alignment: Alignment(-0.1, 0.3), start: 0.24, end: 0.98, size: 14, rotation: 0.3, horizontalDrift: 12, verticalLift: -28, wobbleTurns: 2.0),
      const _StarSpec(alignment: Alignment(0.35, 0.25), start: 0.28, end: 1.0, size: 16, rotation: -0.4, horizontalDrift: 9, verticalLift: -30, wobbleTurns: 1.6),
      const _StarSpec(alignment: Alignment(0.0, -0.1), start: 0.1, end: 0.95, size: 20, rotation: 0.18, horizontalDrift: 16, verticalLift: -38, wobbleTurns: 1.75),
      const _StarSpec(alignment: Alignment(-0.65, 0.15), start: 0.32, end: 0.98, size: 17, rotation: -0.2, horizontalDrift: 11, verticalLift: -33, wobbleTurns: 1.5),
      const _StarSpec(alignment: Alignment(0.7, -0.55), start: 0.36, end: 1.0, size: 19, rotation: 0.28, horizontalDrift: 15, verticalLift: -46, wobbleTurns: 1.4),
      const _StarSpec(alignment: Alignment(-0.35, -0.75), start: 0.2, end: 0.88, size: 18, rotation: -0.22, horizontalDrift: 7, verticalLift: -48, wobbleTurns: 1.25),
      const _StarSpec(alignment: Alignment(0.6, 0.45), start: 0.42, end: 1.0, size: 15, rotation: 0.35, horizontalDrift: 10, verticalLift: -26, wobbleTurns: 1.9),
      const _StarSpec(alignment: Alignment(-0.45, 0.55), start: 0.46, end: 1.0, size: 15, rotation: -0.3, horizontalDrift: 10, verticalLift: -24, wobbleTurns: 1.65),
    ];
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        return Material(
          color: Colors.black.withOpacity(0.45 * _overlay.value),
          child: Stack(
            alignment: Alignment.center,
            children: [
              Positioned.fill(
                child: GestureDetector(
                  onTap: widget.onClose,
                ),
              ),
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Stack(
                    clipBehavior: Clip.none,
                    children: [
                      _buildCard(theme),
                      _buildStarConfetti(),
                      Positioned(
                        top: -30 * _trophyScale.value,
                        left: 0,
                        right: 0,
                        child: ScaleTransition(
                          scale: _trophyScale,
                          child: _buildTrophy(theme),
                        ),
                      ),
                      Positioned(
                        top: 8,
                        right: 8,
                        child: IconButton(
                          tooltip: 'Закрыть',
                          style: IconButton.styleFrom(
                            backgroundColor: Colors.white,
                            foregroundColor: Colors.grey.shade700,
                            shape: const CircleBorder(),
                          ),
                          onPressed: widget.onClose,
                          icon: const Icon(Icons.close),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildCard(ThemeData theme) {
    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(24),
        boxShadow: const [
          BoxShadow(
            color: Colors.black26,
            blurRadius: 18,
            offset: Offset(0, 12),
          ),
        ],
      ),
      padding: const EdgeInsets.fromLTRB(20, 48, 20, 20),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          _buildCover(),
          const SizedBox(height: 18),
          Text(
            widget.data.title,
            textAlign: TextAlign.center,
            style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 10),
          SlideTransition(
            position: _textSlide,
            child: AnimatedOpacity(
              duration: const Duration(milliseconds: 240),
              opacity: _controller.value >= 0.65 ? 1 : 0,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: const Color(0xFF1E3C3D),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  widget.data.rewardText,
                  style: theme.textTheme.titleMedium?.copyWith(
                    color: Colors.amber.shade100,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 14),
          TextButton(
            onPressed: widget.onClose,
            child: const Text('Продолжить'),
          ),
        ],
      ),
    );
  }

  Widget _buildCover() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(18),
        boxShadow: [
          BoxShadow(
            color: Colors.amber.withOpacity(0.32 * _glow.value),
            blurRadius: 28 * _glow.value + 6,
            spreadRadius: 2 * _glow.value,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 240),
        padding: EdgeInsets.all(4 + 6 * _edge.value),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(14),
          gradient: _edge.value > 0
              ? LinearGradient(
                  colors: [
                    const Color(0xFFFFF4D6),
                    const Color(0xFFFFE6A7),
                    const Color(0xFFDFB85A),
                  ],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  stops: const [0.0, 0.35, 1.0],
                )
              : null,
          border: Border.all(
            color: Color.lerp(
                  const Color(0xFFFFEEC3),
                  const Color(0xFFB8860B),
                  _edge.value,
                ) ??
                const Color(0xFFFFEEC3),
            width: 3.4 + 2 * _edge.value,
          ),
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(10),
          child: AspectRatio(
            aspectRatio: 0.66,
            child: widget.data.coverUrl != null
                ? Image.network(
                    widget.data.coverUrl!,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => _buildCoverFallback(),
                  )
                : _buildCoverFallback(),
          ),
        ),
      ),
    );
  }

  Widget _buildCoverFallback() {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF23353D),
        gradient: const LinearGradient(
          colors: [Color(0xFF263A42), Color(0xFF3F535F)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      alignment: Alignment.center,
      child: const Icon(Icons.auto_stories, color: Colors.white70, size: 42),
    );
  }

  Widget _buildTrophy(ThemeData theme) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: const [
          BoxShadow(color: Colors.black26, blurRadius: 16, offset: Offset(0, 8)),
        ],
        border: Border.all(color: Colors.amber.shade200, width: 2),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.emoji_events, color: Colors.amber.shade600, size: 26),
          const SizedBox(width: 8),
          Text(
            'Книга прочитана',
            style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
          ),
        ],
      ),
    );
  }

  Widget _buildStarConfetti() {
    return Positioned.fill(
      child: IgnorePointer(
        child: Stack(
          children: _stars.map(_buildStar).toList(),
        ),
      ),
    );
  }

  Widget _buildStar(_StarSpec spec) {
    final animation = CurvedAnimation(
      parent: _controller,
      curve: Interval(spec.start, spec.end, curve: Curves.easeOut),
    );

    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        final progress = animation.value;
        final opacity = Curves.easeIn.transform(progress.clamp(0.0, 1.0));
        final eased = Curves.easeOutCubic.transform(progress);
        final scale = Tween<double>(begin: 0.35, end: 1.05).transform(eased);
        final verticalShift = Tween<double>(begin: 12, end: spec.verticalLift)
            .transform(eased);
        final wobble = math.sin(progress * math.pi * spec.wobbleTurns) *
            spec.horizontalDrift;
        final rotation =
            spec.rotation + math.sin(progress * math.pi * 1.1) * 0.28;

        return Align(
          alignment: spec.alignment,
          child: Opacity(
            opacity: opacity,
            child: Transform.translate(
              offset: Offset(wobble, verticalShift),
              child: Transform.scale(
                scale: scale,
                child: Transform.rotate(
                  angle: rotation,
                  child: Container(
                    decoration: BoxDecoration(
                      boxShadow: [
                        BoxShadow(
                          color: Colors.amber.withOpacity(0.55 * opacity),
                          blurRadius: 12,
                          spreadRadius: 1,
                        ),
                      ],
                    ),
                    child: Icon(
                      Icons.star_rounded,
                      color: Colors.amber.shade300,
                      size: spec.size,
                    ),
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class _StarSpec {
  const _StarSpec({
    required this.alignment,
    required this.start,
    required this.end,
    required this.size,
    required this.rotation,
    this.horizontalDrift = 0,
    this.verticalLift = -26,
    this.wobbleTurns = 1.0,
  });

  final Alignment alignment;
  final double start;
  final double end;
  final double size;
  final double rotation;
  final double horizontalDrift;
  final double verticalLift;
  final double wobbleTurns;
}

class OfflineNote {
  OfflineNote({
    required this.id,
    required this.text,
    required this.createdAt,
  });

  final String id;
  final String text;
  final DateTime createdAt;

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'text': text,
      'created_at': createdAt.toIso8601String(),
    };
  }

  factory OfflineNote.fromJson(Map<String, dynamic> json) {
    return OfflineNote(
      id: (json['id'] as String?) ?? '',
      text: (json['text'] as String?) ?? '',
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
    );
  }
}

class OfflineNotesStorage {
  Future<File> _notesFile() async {
    final directory = await getApplicationSupportDirectory();
    return File('${directory.path}/offline_notes.json');
  }

  Future<List<OfflineNote>> readNotes() async {
    try {
      final file = await _notesFile();
      if (!await file.exists()) {
        return const [];
      }
      final raw = await file.readAsString();
      if (raw.trim().isEmpty) {
        return const [];
      }
      final List<dynamic> data = jsonDecode(raw) as List<dynamic>;
      return data
          .whereType<Map<String, dynamic>>()
          .map(OfflineNote.fromJson)
          .where((note) => note.text.trim().isNotEmpty)
          .toList();
    } catch (_) {
      return const [];
    }
  }

  Future<void> writeNotes(List<OfflineNote> notes) async {
    final file = await _notesFile();
    final payload = jsonEncode(notes.map((note) => note.toJson()).toList());
    await file.writeAsString(payload);
  }
}