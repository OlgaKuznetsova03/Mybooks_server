import 'package:flutter/material.dart';

import '../../../core/models/feed_models.dart';
import '../../../core/repositories/read_together_repository.dart';

class BooksPage extends StatefulWidget {
  const BooksPage({super.key, required this.repository});

  final ReadTogetherRepository repository;

  @override
  State<BooksPage> createState() => _BooksPageState();
}

class _BooksPageState extends State<BooksPage> {
  final _searchController = TextEditingController();
  final _titleController = TextEditingController();
  final _authorController = TextEditingController();
  final _genreController = TextEditingController();
  String _genreFilter = 'Все';

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: FutureBuilder<List<BookItem>>(
        future: widget.repository.fetchBooks(query: _searchController.text),
        builder: (context, snapshot) {
          final books = snapshot.data ?? const <BookItem>[];
          final genres = {'Все', ...books.map((e) => e.genre)};
          final filtered = _genreFilter == 'Все' ? books : books.where((e) => e.genre == _genreFilter).toList();

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              TextField(
                controller: _searchController,
                decoration: InputDecoration(
                  hintText: 'Поиск по БД книг',
                  prefixIcon: const Icon(Icons.search),
                  suffixIcon: IconButton(
                    onPressed: () => setState(() {}),
                    icon: const Icon(Icons.tune),
                  ),
                ),
                onSubmitted: (_) => setState(() {}),
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                children: genres
                    .map(
                      (genre) => ChoiceChip(
                        label: Text(genre),
                        selected: _genreFilter == genre,
                        onSelected: (_) => setState(() => _genreFilter = genre),
                      ),
                    )
                    .toList(),
              ),
              const SizedBox(height: 12),
              Text('Все книги', style: Theme.of(context).textTheme.titleLarge),
              ...filtered.map(
                (book) => Card(
                  child: ListTile(
                    title: Text(book.title),
                    subtitle: Text('${book.author} · ${book.genre}'),
                    trailing: const Icon(Icons.chevron_right),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: _showAddBookDialog,
                icon: const Icon(Icons.add),
                label: const Text('Добавить новую книгу в БД'),
              ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _showAddBookDialog() async {
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Новая книга'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: _titleController, decoration: const InputDecoration(labelText: 'Название')),
            const SizedBox(height: 8),
            TextField(controller: _authorController, decoration: const InputDecoration(labelText: 'Автор')),
            const SizedBox(height: 8),
            TextField(controller: _genreController, decoration: const InputDecoration(labelText: 'Жанр')),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Отмена')),
          FilledButton(
            onPressed: () async {
              await widget.repository.addBook(
                title: _titleController.text,
                author: _authorController.text,
                genre: _genreController.text,
              );
              if (mounted) {
                Navigator.pop(context);
                setState(() {});
              }
            },
            child: const Text('Сохранить'),
          ),
        ],
      ),
    );
  }
}