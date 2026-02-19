import 'package:flutter/material.dart';

import 'offline_note_model.dart';

class OfflineNotesPanel extends StatelessWidget {
  const OfflineNotesPanel({
    super.key,
    required this.noteController,
    required this.offlineNotes,
    required this.savingNote,
    required this.onSave,
    required this.onDelete,
  });

  final TextEditingController noteController;
  final List<OfflineNote> offlineNotes;
  final bool savingNote;
  final VoidCallback onSave;
  final ValueChanged<String> onDelete;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final recentNotes = offlineNotes.take(3).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Запишите идею', style: theme.textTheme.titleMedium),
        const SizedBox(height: 8),
        Text(
          'Последние действия уже сохранены на устройстве. '
          'Добавьте заметку — мы подскажем, когда её можно синхронизировать.',
          style: theme.textTheme.bodySmall,
        ),
        const SizedBox(height: 12),
        TextField(
          controller: noteController,
          minLines: 2,
          maxLines: 4,
          decoration: InputDecoration(
            hintText: 'Напишите короткую заметку о чтении или идею для марафона',
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(16)),
          ),
        ),
        const SizedBox(height: 8),
        FilledButton.icon(
          onPressed: savingNote ? null : onSave,
          icon: savingNote
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                )
              : const Icon(Icons.edit_note),
          label: Text(savingNote ? 'Сохраняем…' : 'Сохранить заметку'),
        ),
        const SizedBox(height: 16),
        Text('Сохранённые заметки', style: theme.textTheme.titleSmall),
        const SizedBox(height: 8),
        if (recentNotes.isEmpty)
          Text(
            'Здесь появятся ваши заметки. Они будут синхронизирваны, когда связь восстановится.',
            style: theme.textTheme.bodySmall,
          )
        else
          ...recentNotes.map(
            (note) => Card(
              margin: const EdgeInsets.only(bottom: 8),
              child: ListTile(
                title: Text(note.text),
                subtitle: Text(_formatNoteDate(note.createdAt)),
                trailing: IconButton(
                  icon: const Icon(Icons.delete_outline),
                  onPressed: () => onDelete(note.id),
                  tooltip: 'Удалить',
                ),
              ),
            ),
          ),
      ],
    );
  }

  String _formatNoteDate(DateTime date) {
    String twoDigits(int value) => value.toString().padLeft(2, '0');
    final day = twoDigits(date.day);
    final month = twoDigits(date.month);
    final hours = twoDigits(date.hour);
    final minutes = twoDigits(date.minute);
    return '$day.$month.${date.year} · $hours:$minutes';
  }
}