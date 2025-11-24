import 'dart:async';
import 'dart:convert';
import 'dart:io';

/// Error codes that can be produced by [RewardAdsService].
enum RewardAdsError {
  notAuthenticated,
  invalidPayload,
  network,
  disabled,
  invalidResponse,
}

/// A domain specific exception thrown when advertising requests fail.
class RewardAdsException implements Exception {
  RewardAdsException(this.message, {this.code});

  final String message;
  final RewardAdsError? code;

    @override
    String toString() =>
        "RewardAdsException(message: '$message', code: ${code?.name ?? 'none'})";
}

/// Configuration required to initialise a rewarded ad placement.
class RewardAdConfig {
  RewardAdConfig({
    required this.placementId,
    required this.rewardAmount,
    required this.currency,
    required this.enabled,
    required this.requiresAuthentication,
  });

  factory RewardAdConfig.fromJson(Map<String, dynamic> json) {
    return RewardAdConfig(
      placementId: (json['placement_id'] as String? ?? '').trim(),
      rewardAmount: (json['reward_amount'] as num?)?.toInt() ?? 0,
      currency: (json['currency'] as String? ?? 'coins').trim(),
      enabled: json['enabled'] == true,
      requiresAuthentication: json['requires_authentication'] == true,
    );
  }

  final String placementId;
  final int rewardAmount;
  final String currency;
  final bool enabled;
  final bool requiresAuthentication;

  bool get isReady => enabled && placementId.isNotEmpty;
}

/// Result returned when a reward has been successfully claimed.
class RewardAdClaimResult {
  RewardAdClaimResult({
    required this.transactionId,
    required this.coinsAwarded,
    required this.balanceAfter,
    required this.unlimitedBalance,
    this.rewardId,
  });

  factory RewardAdClaimResult.fromJson(Map<String, dynamic> json) {
    return RewardAdClaimResult(
      transactionId: (json['transaction_id'] as num?)?.toInt() ?? 0,
      coinsAwarded: (json['coins_awarded'] as num?)?.toInt() ?? 0,
      balanceAfter: json['balance_after'] == null
          ? null
          : (json['balance_after'] as num).toInt(),
      unlimitedBalance: json['unlimited_balance'] == true,
      rewardId: (json['reward_id'] as String?)?.trim(),
    );
  }

  final int transactionId;
  final int coinsAwarded;
  final int? balanceAfter;
  final bool unlimitedBalance;
  final String? rewardId;
}

/// Service responsible for interacting with the backend advertising API.
class RewardAdsService {
  RewardAdsService({
    required Uri siteOrigin,
    HttpClient? httpClient,
    String? clientHeader,
    String? clientId,
  })  : _origin = _normaliseOrigin(siteOrigin),
        _httpClient = httpClient ?? HttpClient(),
        _clientHeader = (clientHeader ?? 'X-MyBooks-Client').trim(),
        _clientId = (clientId ?? 'mybooks-flutter').trim();

  final Uri _origin;
  final HttpClient _httpClient;
  final String _clientHeader;
  final String _clientId;

  Uri get _configUri => _origin.replace(path: '/accounts/api/reward-ads/config/');
  Uri get _claimUri => _origin.replace(path: '/accounts/api/reward-ads/claim/');

  /// Retrieve the current reward advertising configuration.
  Future<RewardAdConfig> fetchConfig({Map<String, String>? cookies}) async {
    final response = await _send(
      'GET',
      _configUri,
      cookies: cookies,
    );

    if (response.statusCode == HttpStatus.notFound) {
      throw RewardAdsException(
        'Рекламный модуль недоступен или выключен.',
        code: RewardAdsError.disabled,
      );
    }

    if (response.statusCode >= HttpStatus.badRequest) {
      throw RewardAdsException(
        'Не удалось загрузить конфигурацию рекламы (HTTP ${response.statusCode}).',
        code: RewardAdsError.network,
      );
    }

    final Map<String, dynamic> data = _decodeJson(response.body);
    return RewardAdConfig.fromJson(data);
  }

  /// Claim the reward after the user has successfully watched an advert.
  Future<RewardAdClaimResult> claimReward({
    required RewardAdConfig config,
    Map<String, String>? cookies,
    String? rewardId,
    String? adUnitId,
  }) async {
    final effectiveAdUnit = (adUnitId ?? config.placementId).trim();

    final payload = <String, dynamic>{};
    if (effectiveAdUnit.isNotEmpty) {
      payload['ad_unit_id'] = effectiveAdUnit;
    }
    if (rewardId != null && rewardId.trim().isNotEmpty) {
      payload['reward_id'] = rewardId.trim();
    }

    final response = await _send(
      'POST',
      _claimUri,
      cookies: cookies,
      body: jsonEncode(payload),
      contentType: ContentType.json,
    );

    if (response.isRedirect ||
        response.statusCode == HttpStatus.found ||
        response.statusCode == HttpStatus.seeOther) {
      throw RewardAdsException(
        'Для получения награды необходимо авторизоваться.',
        code: RewardAdsError.notAuthenticated,
      );
    }

    if (response.statusCode == HttpStatus.serviceUnavailable) {
      throw RewardAdsException(
        'Сервис временно недоступен. Повторите попытку позже.',
        code: RewardAdsError.disabled,
      );
    }

    if (response.statusCode == HttpStatus.badRequest) {
      final data = _tryDecodeJson(response.body);
      final serverCode = data['error'] as String?;
      final message = serverCode == 'ad_unit_mismatch'
          ? 'Сервер отклонил запрос: неверный идентификатор рекламного блока.'
          : 'Сервер отклонил запрос — проверьте корректность данных.';
      throw RewardAdsException(
        message,
        code: RewardAdsError.invalidPayload,
      );
    }

    if (response.statusCode >= HttpStatus.badRequest) {
      throw RewardAdsException(
        'Не удалось начислить монеты (HTTP ${response.statusCode}).',
        code: RewardAdsError.network,
      );
    }

    final Map<String, dynamic> data = _decodeJson(response.body);
    return RewardAdClaimResult.fromJson(data);
  }

  Future<_ResponseData> _send(
    String method,
    Uri uri, {
    Map<String, String>? cookies,
    String? body,
    ContentType? contentType,
  }) async {
    final request = await _httpClient.openUrl(method, uri);
    request.followRedirects = false;
    request.headers.set(HttpHeaders.acceptHeader, 'application/json');

    if (_clientHeader.isNotEmpty && _clientId.isNotEmpty) {
      request.headers.set(_clientHeader, _clientId);
    }

    if (cookies != null && cookies.isNotEmpty) {
      final cookieHeader = cookies.entries
          .map((entry) => '${entry.key}=${entry.value}')
          .join('; ');
      request.headers.set(HttpHeaders.cookieHeader, cookieHeader);
    }

    if (body != null && body.isNotEmpty) {
      request.headers.contentType = contentType ?? ContentType.json;
      request.add(utf8.encode(body));
    }

    final response = await request.close();
    final responseBody = await response.transform(utf8.decoder).join();

    return _ResponseData(
      statusCode: response.statusCode,
      body: responseBody,
      isRedirect: response.isRedirect,
    );
  }

  Map<String, dynamic> _decodeJson(String source) {
    try {
      final decoded = jsonDecode(source);
      if (decoded is Map<String, dynamic>) {
        return decoded;
      }
      throw const FormatException('JSON root is not an object.');
    } on FormatException catch (error) {
      throw RewardAdsException(
        'Некорректный ответ сервера: ${error.message}',
        code: RewardAdsError.invalidResponse,
      );
    }
  }

  Map<String, dynamic> _tryDecodeJson(String source) {
    try {
      final decoded = jsonDecode(source);
      if (decoded is Map<String, dynamic>) {
        return decoded;
      }
    } catch (_) {
      // Ignored — fallback to empty map.
    }
    return <String, dynamic>{};
  }

  void dispose() {
    _httpClient.close(force: true);
  }

  static Uri _normaliseOrigin(Uri raw) {
    if (!raw.hasScheme || raw.host.isEmpty) {
      throw ArgumentError.value(raw.toString(), 'siteOrigin', 'URL должен содержать схему и домен');
    }

    return Uri(
      scheme: raw.scheme,
      host: raw.host,
      port: raw.hasPort ? raw.port : null,
    );
  }
}

class _ResponseData {
  const _ResponseData({
    required this.statusCode,
    required this.body,
    required this.isRedirect,
  });

  final int statusCode;
  final String body;
  final bool isRedirect;
}