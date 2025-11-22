import 'package:flutter/material.dart';

class StatusOverlay extends StatelessWidget {
  const StatusOverlay._({
    required this.icon,
    required this.title,
    required this.description,
    required this.actionLabel,
    required this.onPressed,
    this.extraContent,
  });

  factory StatusOverlay.offline({
    required bool isOffline,
    required VoidCallback onReload,
    Widget? offlineNotesPanel,
  }) {
    return StatusOverlay._(
      icon: isOffline ? Icons.wifi_off : Icons.timer_off,
      title: isOffline ? 'Вы оффлайн' : 'Долгая загрузка',
      description: isOffline
          ? 'Последняя версия приложения сохранена. Мы автоматически обновим страницу, как только интернет появится.'
          : 'Сайт загружается дольше обычного. Проверьте соединение или попробуйте позже.',
      actionLabel: isOffline ? 'Проверить соединение' : 'Перезагрузить',
      onPressed: onReload,
      extraContent: offlineNotesPanel,
    );
  }

  factory StatusOverlay.error({
    required VoidCallback onReload,
  }) {
    return StatusOverlay._(
      icon: Icons.cloud_off,
      title: 'Не удалось загрузить приложение',
      description: 'Сервис временно недоступен. Попробуйте обновить страницу или вернитесь позже.',
      actionLabel: 'Перезагрузить вкладку',
      onPressed: onReload,
    );
  }

  final IconData icon;
  final String title;
  final String description;
  final String actionLabel;
  final VoidCallback onPressed;
  final Widget? extraContent;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      color: Colors.white,
      alignment: Alignment.center,
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480),
          child: Card(
            elevation: 0,
            color: Colors.grey.shade100,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
            child: Padding(
              padding: const EdgeInsets.all(22),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Icon(icon, size: 46, color: theme.colorScheme.primary),
                  const SizedBox(height: 12),
                  Text(
                    title,
                    style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8),
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
                    extraContent!,
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}