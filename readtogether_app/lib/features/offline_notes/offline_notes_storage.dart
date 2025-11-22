import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

import 'offline_note_model.dart';

class OfflineNotesStorage {
  Future<File> _notesFile() async {
    final directory = await getApplicationSupportDirectory();
    return File('${directory.path}/offline_notes.json');
  }

  Future<List<OfflineNote>> readNotes() async {
    try {
      final file = await _notesFile();
      if (!await file.exists()) {
        return const [];
      }
      final raw = await file.readAsString();
      if (raw.trim().isEmpty) {
        return const [];
      }
      final List<dynamic> data = jsonDecode(raw) as List<dynamic>;
      return data
          .whereType<Map<String, dynamic>>()
          .map(OfflineNote.fromJson)
          .where((note) => note.text.trim().isNotEmpty)
          .toList();
    } catch (_) {
      return const [];
    }
  }

  Future<void> writeNotes(List<OfflineNote> notes) async {
    final file = await _notesFile();
    final payload = jsonEncode(notes.map((note) => note.toJson()).toList());
    await file.writeAsString(payload);
  }
}