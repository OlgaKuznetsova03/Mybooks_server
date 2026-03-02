import 'package:flutter/material.dart';

import '../../../core/models/feed_models.dart';
import '../../../core/repositories/read_together_repository.dart';

class BookDetailPage extends StatefulWidget {
  const BookDetailPage({super.key, required this.repository, required this.bookId});

  final ReadTogetherRepository repository;
  final int bookId;

  @override
  State<BookDetailPage> createState() => _BookDetailPageState();
}

class _BookDetailPageState extends State<BookDetailPage> {
  late Future<BookDetailItem> _detailFuture;

  @override
  void initState() {
    super.initState();
    _detailFuture = widget.repository.fetchBookDetail(widget.bookId);
  }

  Future<void> _reload() async {
    setState(() {
      _detailFuture = widget.repository.fetchBookDetail(widget.bookId);
    });
    await _detailFuture;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Книга')),
      body: FutureBuilder<BookDetailItem>(
        future: _detailFuture,
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
                    const Text('Не удалось загрузить карточку книги.'),
                    const SizedBox(height: 8),
                    FilledButton(onPressed: _reload, child: const Text('Повторить')),
                  ],
                ),
              ),
            );
          }

          final detail = snapshot.data!;
          final book = detail.book;

          return RefreshIndicator(
            onRefresh: _reload,
            child: ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(16),
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _BookCover(coverUrl: book.coverUrl),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(book.title, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
                          const SizedBox(height: 6),
                          Text(book.authors.join(', '), style: const TextStyle(color: Colors.black87)),
                          const SizedBox(height: 6),
                          if (book.averageRating > 0) Text('Рейтинг: ${book.averageRating.toStringAsFixed(1)} ★'),
                          Text(book.totalPages > 0 ? 'Страниц: ${book.totalPages}' : 'Страницы не указаны'),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Жанры', style: TextStyle(fontWeight: FontWeight.w700)),
                        const SizedBox(height: 6),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: (book.genres.isEmpty ? const ['Прочее'] : book.genres)
                              .map((genre) => Chip(label: Text(genre)))
                              .toList(),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 10),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Описание', style: TextStyle(fontWeight: FontWeight.w700)),
                        const SizedBox(height: 6),
                        Text(book.synopsis.isEmpty ? 'Описание пока не добавлено.' : book.synopsis),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 10),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Издание', style: TextStyle(fontWeight: FontWeight.w700)),
                        const SizedBox(height: 6),
                        Text('Язык: ${book.language.isEmpty ? 'не указан' : book.language}'),
                        const SizedBox(height: 8),
                        const Text('ISBN', style: TextStyle(fontWeight: FontWeight.w600)),
                        const SizedBox(height: 6),
                        if (detail.isbn.isEmpty)
                          const Text('ISBN не указаны')
                        else
                          ...detail.isbn.map(
                            (item) => Text(
                              item.isbn13.isNotEmpty ? 'ISBN-13: ${item.isbn13} · ISBN: ${item.isbn}' : 'ISBN: ${item.isbn}',
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          );
        },
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
        width: 96,
        height: 128,
        decoration: BoxDecoration(
          color: const Color(0xFFE7D7C8),
          borderRadius: BorderRadius.circular(12),
        ),
        child: const Icon(Icons.menu_book, size: 40, color: Color(0xFF8A6D52)),
      );
    }

    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: Image.network(
        coverUrl,
        width: 96,
        height: 128,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => Container(
          width: 96,
          height: 128,
          color: const Color(0xFFE7D7C8),
          child: const Icon(Icons.broken_image, size: 40, color: Color(0xFF8A6D52)),
        ),
      ),
    );
  }
}