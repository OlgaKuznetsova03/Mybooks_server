import 'dart:async';

import 'package:flutter/material.dart';

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