import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

class UrlLauncher {
  Future<bool> launchExternalUrl(Uri uri, BuildContext context) async {
    try {
      if (!_isStandardWebScheme(uri.scheme) && !_isStandardExternalScheme(uri.scheme)) {
        try {
          final launched = await launchUrl(
            uri,
            mode: LaunchMode.externalApplication,
          );
          if (launched) {
            return true;
          }
          if (context.mounted) {
            _showUrlLaunchError(
              context,
              uri,
              'Не удалось открыть ссылку. Убедитесь, что приложение установлено.',
            );
          }
          return false;
        } catch (e) {
          if (context.mounted) {
            _showUrlLaunchError(context, uri, 'Ошибка при открытии ссылки: $e');
          }
          return false;
        }
      }

      if (await canLaunchUrl(uri)) {
        final launched = await launchUrl(
          uri,
          mode: LaunchMode.externalApplication,
          webOnlyWindowName: '_blank',
        );

        if (launched) {
          return true;
        }
        if (context.mounted) {
          _showUrlLaunchError(context, uri, 'Не удалось открыть ссылку');
        }
        return false;
      } else {
        if (context.mounted) {
          _showUrlLaunchError(context, uri, 'Нет приложения для обработки этой ссылки');
        }
        return false;
      }
    } catch (error) {
      if (context.mounted) {
        _showUrlLaunchError(context, uri, 'Ошибка при открытии ссылки: $error');
      }
      return false;
    }
  }

  bool _isStandardWebScheme(String scheme) {
    return scheme == 'http' || scheme == 'https';
  }

  bool _isStandardExternalScheme(String scheme) {
    return scheme == 'tel' || scheme == 'mailto' || scheme == 'sms';
  }

  void _showUrlLaunchError(BuildContext context, Uri uri, String message) {
    String detailedMessage = message;
    String? appName;

    switch (uri.scheme) {
      case 'tg':
        appName = 'Telegram';
        detailedMessage = '$message\n\nУбедитесь, что $appName установлен на вашем устройстве.';
        break;
      case 'whatsapp':
        appName = 'WhatsApp';
        detailedMessage = '$message\n\nУбедитесь, что $appName установлен на вашем устройстве.';
        break;
      case 'viber':
        appName = 'Viber';
        detailedMessage = '$message\n\nУбедитесь, что $appName установлен на вашем устройстве.';
        break;
      default:
        if (!_isStandardWebScheme(uri.scheme)) {
          detailedMessage = '$message\n\nСхема: ${uri.scheme}';
        }
    }

    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(detailedMessage),
              if (uri.toString().length < 100)
                Text(
                  'Ссылка: ${uri.toString()}',
                  style: const TextStyle(fontSize: 12, color: Colors.white70),
                ),
            ],
          ),
          duration: const Duration(seconds: 5),
          action: SnackBarAction(
            label: 'OK',
            onPressed: () {},
          ),
        ),
      );
    }
  }
}