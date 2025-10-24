import 'dart:io';
import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';
import 'package:webview_flutter_wkwebview/webview_flutter_wkwebview.dart';
import 'package:file_picker/file_picker.dart';
import 'package:path_provider/path_provider.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ReadTogetherApp());
}

class ReadTogetherApp extends StatelessWidget {
  const ReadTogetherApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ReadTogether',
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF40535c),
        useMaterial3: true,
      ),
      debugShowCheckedModeBanner: false,
      home: const WebViewPage(),
    );
  }
}

class WebViewPage extends StatefulWidget {
  const WebViewPage({super.key});
  @override
  State<WebViewPage> createState() => _WebViewPageState();
}

class _WebViewPageState extends State<WebViewPage> {
  late final WebViewController _controller;
  bool _loading = true;

  final String startUrl = 'https://gawkier-josie-multivalent.ngrok-free.dev/';

  @override
  void initState() {
    super.initState();

    // Параметры платформенного контроллера
    final PlatformWebViewControllerCreationParams params;
    if (WebViewPlatform.instance is WebKitWebViewPlatform) {
      params = WebKitWebViewControllerCreationParams(
        allowsInlineMediaPlayback: true,
        // mediaTypesRequiringUserAction — опустим, не обязателен
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
          onNavigationRequest: (req) {
            final url = req.url.toLowerCase();
            final isOwn = url.contains('gawkier-josie-multivalent.ngrok-free.dev');
            if (!isOwn && (url.startsWith('http://') || url.startsWith('https://'))) {
              // при желании можно открыть внешние ссылки во внешнем браузере (url_launcher)
              return NavigationDecision.prevent;
            }
            return NavigationDecision.navigate;
          },
        ),
      )
      ..loadRequest(Uri.parse(startUrl));

    // ANDROID: выбор файла для <input type="file">
    if (controller.platform is AndroidWebViewController) {
      final android = controller.platform as AndroidWebViewController;
      android
        ..setMediaPlaybackRequiresUserGesture(false)
        ..setOnShowFileSelector(_onShowFileSelector);
    }

    _controller = controller;
  }

  // Важно: тип из android-плагина — FileSelectorParams
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
            .expand((e) => e.split(',')) // ".jpg,.png"
            .map((e) => e.replaceAll('.', '').trim())
            .where((e) => e.isNotEmpty)
            .toList();
      }
    }

    final result = await FilePicker.platform.pickFiles(
      allowMultiple: _shouldAllowMultiple(params),
      type: type,
      allowedExtensions: customExt,
      withData: true, // если path == null — сохраним bytes во временный файл
    );

    if (result == null) return <String>[]; // пользователь отменил

    final List<String> paths = [];
    final tempDir = await getTemporaryDirectory();
    for (final f in result.files) {
      if (f.path != null && f.path!.isNotEmpty) {
        paths.add(_normalizeForWebView(f.path!));
        continue;
      }

      final targetFile =
          await _createTempFile(tempDir.path, f.name, f.extension);

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

    // Если платформенный плагин уже вернул URI (например, content://),
    // то WebView сможет обработать его без преобразований.
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
    final generatedName = sanitizedName ??
        _buildFallbackName(fallbackExtension: fallbackExtension);
    final uniqueName =
        '${DateTime.now().microsecondsSinceEpoch}_${generatedName}';
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

  String _buildFallbackName({String? fallbackExtension}) {
    final ext = fallbackExtension?.trim();
    if (ext == null || ext.isEmpty) {
      return 'upload';
    }
    final sanitizedExt = ext.replaceAll(RegExp(r'[^A-Za-z0-9]'), '');
    if (sanitizedExt.isEmpty) {
      return 'upload';
    }
    return 'upload.$sanitizedExt';
  }

  bool _shouldAllowMultiple(FileSelectorParams params) {
    final dynamic dynamicParams = params;

    try {
      final value = dynamicParams.allowMultiple;
      if (value is bool) {
        return value;
      }
    } catch (_) {
      // Property not available on this plugin version.
    }

    try {
      final mode = dynamicParams.mode;
      if (mode != null) {
        final modeString = mode.toString().toLowerCase();
        if (modeString.contains('multiple')) {
          return true;
        }
      }
    } catch (_) {
      // Property not available on this plugin version.
    }

    return false;
  }

  Future<bool> _handleBack() async {
    if (await _controller.canGoBack()) {
      _controller.goBack();
      return false;
    }
    return true;
  }

  @override
  Widget build(BuildContext context) {
    return WillPopScope(
      onWillPop: _handleBack,
      child: Scaffold(
        appBar: AppBar(title: const Text('ReadTogether')),
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
