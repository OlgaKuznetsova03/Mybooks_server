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

  Future<NavigationDecision> handleNavigationRequest(NavigationRequest request) async {
    final uri = Uri.tryParse(request.url);
    if (uri == null) return NavigationDecision.navigate;

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

  Future<bool> handleBack() async {
    if (await webViewManager.controller.canGoBack()) {
      webViewManager.controller.goBack();
      return false;
    }
    return true;
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
}