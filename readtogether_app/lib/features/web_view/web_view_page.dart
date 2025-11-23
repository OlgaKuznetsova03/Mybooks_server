import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:flutter/foundation.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart'; 
import 'package:webview_flutter_wkwebview/webview_flutter_wkwebview.dart';

import '../../features/ads/ad_banner.dart';
import '../../features/ads/yandex_ad_dialog.dart';
import '../../features/celebration/finish_celebration.dart';
import '../../features/offline_notes/offline_note_model.dart';
import '../../features/offline_notes/offline_notes_panel.dart';
import '../../features/offline_notes/offline_notes_storage.dart';
import '../../utils/constants.dart';
import '../../widgets/common/status_overlay.dart';
import '../../widgets/dialogs/terms_dialog.dart';
import 'web_view_controller.dart';
import 'web_view_navigation.dart';

class MainWebViewPage extends StatefulWidget {
  const MainWebViewPage({super.key, this.onlineNotifier});

  final ValueListenable<bool>? onlineNotifier;

  @override
  State<MainWebViewPage> createState() => _MainWebViewPageState();
}

class _MainWebViewPageState extends State<MainWebViewPage> {
  late final String _startUrl;
  late final WebViewManager _webViewManager;
  late final WebViewNavigation _navigation;
  late final OfflineNotesStorage _offlineNotesStorage;
  final TextEditingController _noteController = TextEditingController();
  final HttpClient _httpClient = HttpClient();

  List<OfflineNote> _offlineNotes = [];
  bool _savingNote = false;
  ValueListenable<bool>? _connectivityListenable;
  bool _webViewError = false;
  bool _isOffline = false;
  bool _showOfflineRecoveryOverlay = false;
  bool _wasOffline = false;
  bool _reconnectDialogVisible = false;
  int _coinsBalance = 0;
  bool _rewardInProgress = false;
  bool _loadingTimedOut = false;
  bool _shouldReloadAfterReconnect = false;
  bool _celebrationLoading = false;
  FinishCelebrationData? _celebrationData; // ДОБАВЬТЕ ЭТУ ПЕРЕМЕННУЮ
  Timer? _offlineRecoveryTimer;

  @override
  void initState() {
    super.initState();

    _startUrl = _prepareStartUrl(AppConstants.defaultSiteUrl);
    _webViewManager = WebViewManager(startUrl: _startUrl);
    _navigation = WebViewNavigation(webViewManager: _webViewManager, context: context);
    _offlineNotesStorage = OfflineNotesStorage();

    _attachConnectivity(widget.onlineNotifier);
    _loadOfflineNotes();

    _webViewManager.stateNotifier.addListener(_handleWebViewStateChanged);

    _webViewManager.initialize(
      onNavigationRequest: _navigation.handleNavigationRequest,
      onJavaScriptMessage: _handleJavaScriptMessage,
      context: context,
    );

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
    _webViewManager.dispose();
    _detachConnectivity();
    _offlineRecoveryTimer?.cancel();
    _noteController.dispose();
    super.dispose();
  }

  void _handleWebViewStateChanged() {
    final state = _webViewManager.stateNotifier.value;
    setState(() {
      _webViewError = state.hasError;
      _loadingTimedOut = state.isLoadingTimedOut;
    });
  }

  void _attachConnectivity(ValueListenable<bool>? notifier) {
    _detachConnectivity();
    _connectivityListenable = notifier;
    if (notifier != null) {
      _isOffline = !notifier.value;
      _shouldReloadAfterReconnect = _isOffline;
      _webViewManager.updateConnectivity(notifier.value);
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
    setState(() {
      _isOffline = offline;
      if (offline) {
        _wasOffline = true;
        _showOfflineRecoveryOverlay = false;
        _offlineRecoveryTimer?.cancel();
      }
    });
    _webViewManager.updateConnectivity(notifier.value);
    if (offline) {
      _shouldReloadAfterReconnect = true;
    }
    if (!offline && (_webViewError || _loadingTimedOut || _shouldReloadAfterReconnect)) {
      _shouldReloadAfterReconnect = false;
      _startOfflineRecoveryOverlay();
      _reloadWebView();
    }

    if (!offline && _wasOffline) {
      _wasOffline = false;
      _showReconnectPrompt();
    }
  }

  Future<void> _showReconnectPrompt() async {
    if (_reconnectDialogVisible || !mounted) return;
    _reconnectDialogVisible = true;

    final shouldOpenCatalog = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      barrierColor: Colors.white,
      builder: (context) => AlertDialog(
        title: const Text('Мы снова онлайн'),
        content: const Text(
          'Подключение восстановлено. Вернёмся к каталогу книг?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Остаться здесь'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Перейти к книгам'),
          ),
        ],
      ),
    );

    _reconnectDialogVisible = false;
    if (!mounted) return;

    if (shouldOpenCatalog == true) {
      await _openCatalog();
    }
  }

  void _startOfflineRecoveryOverlay() {
    _offlineRecoveryTimer?.cancel();
    setState(() => _showOfflineRecoveryOverlay = true);
    _offlineRecoveryTimer = Timer(const Duration(seconds: 4), () {
      if (!mounted) return;
      setState(() => _showOfflineRecoveryOverlay = false);
    });
  }

  Future<bool> _ensureTermsAccepted() async {
    try {
      final marker = await _termsAcceptanceMarker();
      if (await marker.exists()) {
        return true;
      }
    } catch (_) {
      return true;
    }

    while (mounted) {
      final accepted = await showDialog<bool>(
        context: context,
        barrierDismissible: false,
        builder: (context) => TermsDialog(siteOrigin: _webViewManager.siteOrigin),
      );

      if (accepted == true) {
        try {
          final marker = await _termsAcceptanceMarker();
          await marker.create(recursive: true);
          await marker.writeAsString('Accepted at ${DateTime.now()}');
        } catch (_) {}
        return true;
      } else if (accepted == false) {
        await _closeApplication();
        return false;
      }
    }
    return false;
  }

  Future<void> _checkTermsAndLoad() async {
    final accepted = await _ensureTermsAccepted();
    if (!mounted) return;
    if (accepted) {
      try {
        await _webViewManager.controller.loadRequest(Uri.parse(_startUrl));
      } catch (_) {
        if (mounted) {
          setState(() {
            _webViewError = true;
          });
        }
      }
    }
  }

  Future<void> _closeApplication() async {
    if (Platform.isAndroid) {
      await SystemNavigator.pop();
    } else {
      exit(0);
    }
  }

  String _prepareStartUrl(String rawUrl) {
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

  Future<void> _handleJavaScriptMessage(JavaScriptMessage message) async {
    Map<String, dynamic>? payload;

    try {
      final decoded = jsonDecode(message.message);
      if (decoded is Map<String, dynamic>) {
        payload = decoded;
      } else if (decoded is Map) {
        payload = decoded.map((key, value) => MapEntry(key.toString(), value));
      }
    } catch (_) {}

    if (payload == null) return;

    final rawType = payload['type'] ?? payload['event'];
    final type = rawType is String ? rawType.toLowerCase() : rawType?.toString().toLowerCase();
    
    if (type == 'book_finished' || type == 'bookfinished' || type == 'book-finished') {
      await _handleFinishCelebration(payload);
    }
  }

  Future<void> _handleFinishCelebration(Map<String, dynamic> payload) async {
    final apiUrl = payload['api_url'] ?? payload['apiUrl'] ?? payload['api'];
    final points = payload['points'] ?? payload['reward'] ?? payload['coins'];
    final fallbackReward = _buildRewardText(points, fallback: payload['rewardText'] as String?);
    final fallbackTitle = (payload['title'] ?? payload['bookTitle'])?.toString();
    final fallbackCover = (payload['cover'] ?? payload['cover_url'] ?? payload['coverUrl'])?.toString();

    FinishCelebrationData? celebrationData;

    if (apiUrl is String && apiUrl.trim().isNotEmpty) {
      final data = await _loadCelebrationFromApi(
        apiUrl,
        fallbackTitle: fallbackTitle,
        fallbackCover: fallbackCover,
        fallbackRewardText: fallbackReward,
      );
      if (data != null) {
        celebrationData = data;
      }
    }

    if (celebrationData == null && fallbackReward != null && fallbackTitle != null) {
      celebrationData = FinishCelebrationData(
        title: fallbackTitle,
        rewardText: fallbackReward,
        coverUrl: fallbackCover,
      );
    }

    // ВЫЗОВ СТАРОЙ АНИМАЦИИ
    if (celebrationData != null && mounted) {
      setState(() => _celebrationData = celebrationData);
    }
  }

  Future<FinishCelebrationData?> _loadCelebrationFromApi(
    String apiUrl, {
    String? fallbackTitle,
    String? fallbackCover,
    String? fallbackRewardText,
  }) async {
    if (_celebrationLoading) return null;
    _celebrationLoading = true;

    try {
      final uri = Uri.tryParse(apiUrl);
      if (uri == null) {
        return null;
      }

      final request = await _httpClient.getUrl(uri);
      final response = await request.close();
      if (response.statusCode != HttpStatus.ok) {
        return null;
      }

      final raw = await response.transform(utf8.decoder).join();
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return null;

      final title = decoded['title']?.toString() ?? fallbackTitle;
      final rewardText = decoded['reward']?.toString() ?? fallbackRewardText;
      final cover = decoded['cover']?.toString() ?? fallbackCover;

      if (title != null && rewardText != null) {
        return FinishCelebrationData(title: title, rewardText: rewardText, coverUrl: cover);
      }
      return null;
    } catch (_) {
      return null;
    } finally {
      _celebrationLoading = false;
    }
  }

  String? _buildRewardText(dynamic reward, {String? fallback}) {
    if (reward is num) {
      final value = reward.toInt();
      if (value > 0) {
        return '+$value баллов за чтение';
      }
    }
    if (reward is String && reward.trim().isNotEmpty) {
      return reward;
    }
    return fallback;
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

  Future<void> _loadOfflineNotes() async {
    try {
      final stored = await _offlineNotesStorage.readNotes();
      if (!mounted) return;
      setState(() => _offlineNotes = stored);
    } catch (_) {}
  }

  Future<File> _termsAcceptanceMarker() async {
    final directory = await getApplicationSupportDirectory();
    return File('${directory.path}/mybooks_terms_v1.txt');
  }

  void _reloadWebView() {
    if (!mounted) return;
    setState(() {
      _webViewError = false;
      _loadingTimedOut = false;
    });
    _webViewManager.reload();
  }

  Future<void> _openCatalog() async {
    if (!mounted) return;
    try {
      setState(() {
        _webViewError = false;
        _loadingTimedOut = false;
        _showOfflineRecoveryOverlay = false;
      });
      await _webViewManager.controller.loadRequest(Uri.parse(_startUrl));
    } catch (_) {
      _reloadWebView();
    }
  }

  bool get _isOfflineOverlayVisible =>
      _webViewManager.isOffline || _showOfflineRecoveryOverlay;

  Widget _buildOfflineNotesPanel() {
    return OfflineNotesPanel(
      noteController: _noteController,
      offlineNotes: _offlineNotes,
      savingNote: _savingNote,
      onSave: _handleSaveOfflineNote,
      onDelete: _handleDeleteOfflineNote,
    );
  }

  Widget _buildOfflineBanner() {
    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: Container(
        padding: const EdgeInsets.all(8),
        color: Colors.orange.withOpacity(0.9),
        child: Row(
          children: [
            const Icon(Icons.wifi_off, size: 16, color: Colors.white),
            const SizedBox(width: 8),
            const Expanded(
              child: Text(
                'Режим оффлайн. Используются сохраненные данные.',
                style: TextStyle(color: Colors.white, fontSize: 12),
              ),
            ),
            IconButton(
              icon: const Icon(Icons.close, size: 16, color: Colors.white),
              onPressed: () {
                _webViewManager.showOfflineBanner = false;
                setState(() {});
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStatusOverlays() {
    return ValueListenableBuilder<WebViewState>(
      valueListenable: _webViewManager.stateNotifier,
      builder: (context, state, child) {
        if (state.isLoading && !_webViewManager.isOffline) {
          return const Center(child: CircularProgressIndicator());
        }

        if (state.isLoadingTimedOut || _isOfflineOverlayVisible) {
          return StatusOverlay.offline(
            isOffline: _isOfflineOverlayVisible,
            onReload:
                _webViewManager.isOffline || _showOfflineRecoveryOverlay ? null : _reloadWebView,
            offlineNotesPanel: _buildOfflineNotesPanel(),
          );
        }

        if (state.hasError && !_webViewManager.isOffline) {
          return StatusOverlay.error(onReload: _reloadWebView);
        }

        return const SizedBox.shrink();
      },
    );
  }

  Widget _buildRewardBanner() {
    return AdBanner(
      isEnabled: AppConstants.isYandexAdEnabled,
      rewardInProgress: _rewardInProgress,
      onWatchAd: _handleWatchYandexAd,
    );
  }

  Future<void> _handleWatchYandexAd() async {
    if (_rewardInProgress || !AppConstants.isYandexAdEnabled) return;
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

  Future<bool> _handleBack() async {
    return _navigation.handleBack();
  }

  void _handleCelebrationClosed() {
    setState(() => _celebrationData = null);
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvoked: (bool didPop) async {
        if (!didPop) {
          final shouldPop = await _handleBack();
          if (shouldPop && mounted) Navigator.of(context).pop();
        }
      },
      child: Scaffold(
        backgroundColor: Colors.white,
        body: Column(
          children: [
            SafeArea(bottom: false, child: _buildRewardBanner()),
            Expanded(
              child: Stack(
                clipBehavior: Clip.none,
                children: [
                  WebViewWidget(controller: _webViewManager.controller),
                  if (_webViewManager.showOfflineBanner) _buildOfflineBanner(),
                  _buildStatusOverlays(),
                  
                  // СТАРАЯ АНИМАЦИЯ ИЗ MAIN.DART
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