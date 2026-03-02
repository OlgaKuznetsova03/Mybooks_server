import 'package:flutter/material.dart';

import '../../../core/models/feed_models.dart';
import '../../../core/repositories/read_together_repository.dart';
import 'book_detail_page.dart';

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
  late Future<List<BookItem>> _booksFuture;

  @override
  void initState() {
    super.initState();
    _booksFuture = widget.repository.fetchBooks();
  }

  @override
  void dispose() {
    _searchController.dispose();
    _titleController.dispose();
    _authorController.dispose();
    _genreController.dispose();
    super.dispose();
  }

  Future<void> _reloadBooks() async {
    setState(() {
      _booksFuture = widget.repository.fetchBooks(query: _searchController.text);
    });
    await _booksFuture;
  }

  void _performSearch() {
    setState(() {
      _genreFilter = 'Все';
      _booksFuture = widget.repository.fetchBooks(query: _searchController.text);
    });
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: FutureBuilder<List<BookItem>>(
        future: _booksFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }

          if (snapshot.hasError) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Text('Не удалось загрузить книги из API.'),
                    const SizedBox(height: 8),
                    FilledButton(
                      onPressed: _reloadBooks,
                      child: const Text('Повторить'),
                    ),
                  ],
                ),
              ),
            );
          }

          final books = snapshot.data ?? const <BookItem>[];
          final genres = {'Все', ...books.expand((e) => e.genres.isEmpty ? <String>[e.genre] : e.genres)};
          final filtered = _genreFilter == 'Все'
              ? books
              : books.where((book) => (book.genres.isEmpty ? [book.genre] : book.genres).contains(_genreFilter)).toList();

          return RefreshIndicator(
            onRefresh: _reloadBooks,
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(16),
              children: [
                TextField(
                  controller: _searchController,
                  decoration: InputDecoration(
                    hintText: 'Название, автор, жанр или ISBN',
                    prefixIcon: const Icon(Icons.search),
                    suffixIcon: IconButton(
                      onPressed: _performSearch,
                      icon: const Icon(Icons.send),
                    ),
                  ),
                  onSubmitted: (_) => _performSearch(),
                ),
                const SizedBox(height: 12),
                Text(
                  'Найдено книг: ${filtered.length}',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.black54),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
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
                const SizedBox(height: 8),
                if (filtered.isEmpty)
                  const Card(
                    child: ListTile(
                      title: Text('Ничего не найдено'),
                      subtitle: Text('Измените запрос и попробуйте снова.'),
                    ),
                  )
                else
                  ...filtered.map(
                    (book) => Card(
                      child: ListTile(
                        contentPadding: const EdgeInsets.all(12),
                        leading: _BookCover(coverUrl: book.coverUrl),
                        title: Text(book.title, maxLines: 2, overflow: TextOverflow.ellipsis),
                        subtitle: Padding(
                          padding: const EdgeInsets.only(top: 6),
                          child: Text(
                            '${book.authors.join(', ')}\nЖанр: ${book.genres.join(', ')}\n${book.totalPages > 0 ? '${book.totalPages} стр.' : 'Страницы не указаны'}',
                          ),
                        ),
                        isThreeLine: true,
                        trailing: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const Icon(Icons.chevron_right),
                            if (book.averageRating > 0)
                              Text(
                                '★ ${book.averageRating.toStringAsFixed(1)}',
                                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                              ),
                          ],
                        ),
                        onTap: () {
                          Navigator.of(context).push(
                            MaterialPageRoute<void>(
                              builder: (_) => BookDetailPage(repository: widget.repository, bookId: book.id),
                            ),
                          );
                        },
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
            ),
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
                _titleController.clear();
                _authorController.clear();
                _genreController.clear();
                _performSearch();
              }
            },
            child: const Text('Сохранить'),
          ),
        ],
      ),
    );
  }
}

class _BookCover extends StatelessWidget {
  const _BookCover({required this.coverUrl});

  final String coverUrl;

  @override
  Widget build(BuildContext context) {
    final hasCover = coverUrl.trim().isNotEmpty;
    if (!hasCover) {
      return Container(
        width: 48,
        height: 64,
        decoration: BoxDecoration(
          color: const Color(0xFFE7D7C8),
          borderRadius: BorderRadius.circular(8),
        ),
        child: const Icon(Icons.menu_book, color: Color(0xFF8A6D52)),
      );
    }

    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: Image.network(
        coverUrl,
        width: 48,
        height: 64,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => Container(
          width: 48,
          height: 64,
          color: const Color(0xFFE7D7C8),
          child: const Icon(Icons.broken_image, color: Color(0xFF8A6D52)),
        ),
      ),
    );
  }
}