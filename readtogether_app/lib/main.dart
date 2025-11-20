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
  List<OfflineNote> _offlineNotes = [];
  bool _savingNote = false;
  ValueListenable<bool>? _connectivityListenable;

  bool _loading = true;
  bool _webViewError = false;
  bool _isOffline = false;
  int _coinsBalance = 0;
  bool _rewardInProgress = false;

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
      unawaited(_launchExternalUrl(uri));
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
        );
      } else {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Не удалось открыть ссылку')),
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

  Widget _buildRewardBanner() {
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
    if (_rewardInProgress) return;
    setState(() => _rewardInProgress = true);
    try {
      final rewarded = await showDialog<bool>(
        context: context,
        barrierDismissible: false,
        builder: (_) => const YandexAdDialog(),
      );
      if (rewarded == true && mounted) {
        setState(() => _coinsBalance += 20);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Спасибо! На ваш счёт зачислено 20 монет.')),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _rewardInProgress = false);
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
                  if (_webViewError && !_isOffline)
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
                  if (_isOffline)
                    Positioned.fill(
                      child: _buildStatusOverlay(
                        icon: Icons.wifi_off,
                        title: 'Вы оффлайн',
                        description:
                            'Последняя версия приложения сохранена. Мы автоматически обновим страницу, как только интернет появится.',
                        onPressed: _reloadWebView,
                        actionLabel: 'Проверить соединение',
                        extraContent: _buildOfflineNotesPanel(),
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