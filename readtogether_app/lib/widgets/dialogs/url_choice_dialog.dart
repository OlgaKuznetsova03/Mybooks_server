import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

enum UrlDecision { openInBrowser, openInApp }

Future<UrlDecision?> showUrlChoiceDialog(BuildContext context, Uri uri) {
  return showDialog<UrlDecision>(
    context: context,
    builder: (context) => AlertDialog(
      title: const Text('Открыть ссылку'),
      content: Text('Открыть "${uri.host}" в:'),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context, UrlDecision.openInBrowser),
          child: const Text('Браузере'),
        ),
        TextButton(
          onPressed: () => Navigator.pop(context, UrlDecision.openInApp),
          child: const Text('Приложении'),
        ),
      ],
    ),
  );
}

NavigationDecision mapDecisionToNavigation(UrlDecision decision) {
  switch (decision) {
    case UrlDecision.openInBrowser:
      return NavigationDecision.prevent;
    case UrlDecision.openInApp:
      return NavigationDecision.navigate;
  }
}