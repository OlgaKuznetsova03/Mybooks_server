class OfflineNote {
  OfflineNote({
    required this.id,
    required this.text,
    required this.createdAt,
  });

  final String id;
  final String text;
  final DateTime createdAt;

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'text': text,
      'created_at': createdAt.toIso8601String(),
    };
  }

  factory OfflineNote.fromJson(Map<String, dynamic> json) {
    return OfflineNote(
      id: (json['id'] as String?) ?? '',
      text: (json['text'] as String?) ?? '',
      createdAt:
          DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
    );
  }
}