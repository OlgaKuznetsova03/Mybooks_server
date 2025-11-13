import 'dart:async';
import 'dart:convert';
import 'dart:io';

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
import 'dart:developer';

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
  late final OfflineNotesStorage _offlineNotesStorage;
  final TextEditingController _noteController = TextEditingController();
  List<OfflineNote> _offlineNotes = [];
  bool _savingNote = false;
  ValueListenable<bool>? _connectivityListenable;

  bool _loading = true;
  bool _webViewError = false;
  bool _isOffline = false;

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
          onPageStarted: (_) => setState(() {
                _loading = true;
                _webViewError = false;
              }),
          onPageFinished: (_) => setState(() {
                _loading = false;
                _webViewError = false;
              }),
          onWebResourceError: (_) => setState(() {
                _loading = false;
                _webViewError = true;
              }),
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
  void didUpdateWidget(covariant MainWebViewPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.onlineNotifier != widget.onlineNotifier) {
      _attachConnectivity(widget.onlineNotifier);
    }
  }

  @override
  void dispose() {
    _detachConnectivity();
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

  void _handleConnectivityChange() {
    final notifier = _connectivityListenable;
    if (notifier == null || !mounted) return;
    final offline = !notifier.value;
    if (offline == _isOffline) return;
    setState(() => _isOffline = offline);
    if (!offline && _webViewError) {
      _controller.reload();
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

  void _reloadWebView() {
    if (!mounted) return;
    setState(() => _webViewError = false);
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
        body: Stack(
          children: [
            Positioned.fill(child: WebViewWidget(controller: _controller)),
            if (_loading) const Center(child: CircularProgressIndicator()),
            if (_webViewError && !_isOffline)
              Positioned.fill(
                child: _buildStatusOverlay(
                  icon: Icons.cloud_off,
                  title: 'Не удалось загрузить сайт',
                  description:
                      'Сервис временно недоступен. Попробуйте обновить страницу или вернитесь позже.',
                  onPressed: _reloadWebView,
                  actionLabel: 'Перезагрузить вкладку',
                ),
              ),
            if (_isOffline)
              Positioned.fill(
                child: _buildStatusOverlay(
                  icon: Icons.wifi_off,
                  title: 'Вы офлайн',
                  description:
                      'Последняя версия сайта сохранена. Мы автоматически обновим страницу, как только интернет появится.',
                  onPressed: _reloadWebView,
                  actionLabel: 'Проверить соединение',
                  extraContent: _buildOfflineNotesPanel(),
                ),
              ),
          ],
        ),
      ),
    );
  }
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