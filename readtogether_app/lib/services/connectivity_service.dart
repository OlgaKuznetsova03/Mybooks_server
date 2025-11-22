import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';

class ConnectivityService {
  final ValueNotifier<bool> isOnlineNotifier = ValueNotifier(true);
  final Connectivity _connectivity = Connectivity();
  StreamSubscription<dynamic>? _connectivitySubscription;

  Future<void> init() async {
    try {
      final result = await _connectivity.checkConnectivity();
      _handleConnectivityResult(result);
    } catch (_) {}

    _connectivitySubscription =
        _connectivity.onConnectivityChanged.listen(_handleConnectivityResult);
  }

  void _handleConnectivityResult(dynamic result) {
    bool hasConnection = true;
    if (result is ConnectivityResult) {
      hasConnection = result != ConnectivityResult.none;
    } else if (result is List<ConnectivityResult>) {
      hasConnection = result.any((e) => e != ConnectivityResult.none);
    }

    final wasOnline = isOnlineNotifier.value;
    if (wasOnline != hasConnection) {
      isOnlineNotifier.value = hasConnection;

      if (!hasConnection && wasOnline) {
        _notifyOfflineMode();
      } else if (hasConnection && !wasOnline) {
        _notifyOnlineMode();
      }
    }
  }

  void _notifyOfflineMode() {
    debugPrint('App entered offline mode');
  }

  void _notifyOnlineMode() {
    debugPrint('App restored online connection');
  }

  void dispose() {
    _connectivitySubscription?.cancel();
    isOnlineNotifier.dispose();
  }
}