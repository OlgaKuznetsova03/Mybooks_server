import 'package:flutter/material.dart';

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