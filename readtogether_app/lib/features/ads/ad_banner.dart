import 'package:flutter/material.dart';

class AdBanner extends StatelessWidget {
  const AdBanner({
    super.key,
    required this.isEnabled,
    required this.rewardInProgress,
    required this.onWatchAd,
  });

  final bool isEnabled;
  final bool rewardInProgress;
  final VoidCallback onWatchAd;

  @override
  Widget build(BuildContext context) {
    if (!isEnabled) {
      return const SizedBox.shrink();
    }

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
            onPressed: rewardInProgress ? null : onWatchAd,
            child: rewardInProgress
                ? const SizedBox(
                    height: 16,
                    width: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Смотреть', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w500)),
          ),
        ],
      ),
    );
  }
}