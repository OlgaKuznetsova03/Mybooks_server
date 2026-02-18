import 'package:flutter/material.dart';

class TermsDialog extends StatelessWidget {
  const TermsDialog({super.key, required this.siteOrigin});

  final Uri siteOrigin;

  @override
  Widget build(BuildContext context) {
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
              '${siteOrigin.scheme}://${siteOrigin.host}/rules/',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.primary,
              ),
            ),
            const SizedBox(height: 16),
            Text(
              'Нажимая «Принимаю правила», вы подтверждаете, что ознакомились '
              'с документом и обязуетесь соблюдать требования сервиса.',
              style: theme.textTheme.bodySmall,
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context, false),
          child: const Text('Не принимаю'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(context, true),
          child: const Text('Принимаю правила'),
        ),
      ],
    );
  }
}