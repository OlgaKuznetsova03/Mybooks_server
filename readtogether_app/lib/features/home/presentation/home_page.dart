import 'package:flutter/material.dart';

import '../../../core/models/feed_models.dart';
import '../../../core/repositories/read_together_repository.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key, required this.repository});

  final ReadTogetherRepository repository;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  late Future<HomePayload> _homeFuture;

  @override
  void initState() {
    super.initState();
    _homeFuture = widget.repository.fetchHome();
  }

  Future<void> _reload() async {
    setState(() {
      _homeFuture = widget.repository.fetchHome();
    });
    await _homeFuture;
  }

  @override
  Widget build(BuildContext context) {
    const pageBackground = Color(0xFFF2E7DC);
    const panelBackground = Color(0xFFE9D8C7);

    return ColoredBox(
      color: pageBackground,
      child: SafeArea(
        child: FutureBuilder<HomePayload>(
          future: _homeFuture,
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
                      const Text('Не удалось загрузить главную страницу.'),
                      const SizedBox(height: 8),
                      FilledButton(
                        onPressed: _reload,
                        child: const Text('Повторить'),
                      ),
                    ],
                  ),
                ),
              );
            }

            final data = snapshot.data!;

            return RefreshIndicator(
              onRefresh: _reload,
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.fromLTRB(12, 8, 12, 24),
                children: [
                  _HomeTopBar(title: data.headline),
                  const SizedBox(height: 12),
                  Container(
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: panelBackground,
                      borderRadius: BorderRadius.circular(24),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        if ((data.greeting ?? '').isNotEmpty)
                          Text(
                            data.greeting!,
                            style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
                          ),
                        Text('Читаю сейчас', style: Theme.of(context).textTheme.labelLarge),
                        const SizedBox(height: 4),
                        Text(
                          'Продолжайте книги, которые у вас на полке',
                          style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
                        ),
                        const SizedBox(height: 12),
                        if (data.currentReading.isEmpty)
                          const Card(child: ListTile(title: Text('Пока нет книг в разделе «Читаю»')))
                        else
                          ...data.currentReading.map(_buildCurrentBookCard),
                      ],
                    ),
                  ),
                  const SizedBox(height: 18),
                  _sectionTitle(context, 'Актуальные совместные чтения'),
                  const SizedBox(height: 6),
                  if (data.readingFeed.isEmpty)
                    const Text('Сейчас нет активных совместных чтений, но вы можете создать своё!')
                  else
                    ...data.readingFeed.map(_buildReadingFeedCard),
                  const SizedBox(height: 16),
                  _sectionTitle(context, 'Актуальные марафоны'),
                  const SizedBox(height: 6),
                  if (data.marathons.isEmpty)
                    const Text('Нет активных марафонов')
                  else
                    SizedBox(
                      height: 190,
                      child: ListView.separated(
                        scrollDirection: Axis.horizontal,
                        itemBuilder: (context, index) => SizedBox(width: 220, child: _buildMarathonCard(data.marathons[index])),
                        separatorBuilder: (_, __) => const SizedBox(width: 10),
                        itemCount: data.marathons.length,
                      ),
                    ),
                  const SizedBox(height: 16),
                  if (data.readingMetrics != null) ...[
                    _sectionTitle(context, 'Прогресс за неделю'),
                    const SizedBox(height: 8),
                    Card(
                      child: ListTile(
                        leading: const Icon(Icons.insights_outlined),
                        title: Text('Прочитано ${data.readingMetrics!.totalPages} страниц'),
                        subtitle: Text('В среднем ${data.readingMetrics!.averagePagesPerDay} стр./день'),
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],
                  _sectionTitle(context, 'Добавить книгу через API'),
                  const SizedBox(height: 8),
                  Card(
                    child: ListTile(
                      title: const Text('Отправить новую книгу на сервер'),
                      subtitle: const Text('Проверьте передачу введённых данных через API /books/.'),
                      trailing: const Icon(Icons.send),
                      onTap: _showQuickAddBookDialog,
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _sectionTitle(BuildContext context, String title) {
    return Text(
      title,
      style: Theme.of(context).textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.w700,
            color: const Color(0xFF2A3644),
          ),
    );
  }

  Widget _buildCurrentBookCard(CurrentBook book) {
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _BookCover(coverUrl: book.coverUrl, size: 54),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(book.title, style: const TextStyle(fontWeight: FontWeight.w700)),
                      const SizedBox(height: 2),
                      Text(book.author, style: const TextStyle(color: Colors.black54)),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(999),
              child: LinearProgressIndicator(
                minHeight: 6,
                value: (book.progress / 100).clamp(0, 1).toDouble(),
                backgroundColor: const Color(0xFFE3DED8),
              ),
            ),
            const SizedBox(height: 6),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('${book.progress}%'),
                Text(book.totalPages > 0 ? '${book.totalPages} стр.' : '— стр.'),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildReadingFeedCard(ReadingUpdate item) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: const Color(0xFFD3B08A),
          child: Text(_firstLetter(item.userName)),
        ),
        title: Text(item.userName, style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text('${item.bookTitle}\nУчастников: ${item.pagesRead}'),
        isThreeLine: true,
      ),
    );
  }

  Widget _buildMarathonCard(MarathonItem item) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(
                color: const Color(0xFFD1AB7F),
                borderRadius: BorderRadius.circular(999),
              ),
              child: Text(item.status, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700)),
            ),
            const SizedBox(height: 8),
            Text(item.name, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
            const Spacer(),
            Text('👥 ${item.participants} участников'),
            Text('📚 ${item.themeCount} тем'),
          ],
        ),
      ),
    );
  }

  Future<void> _showQuickAddBookDialog() async {
    final titleController = TextEditingController();
    final authorController = TextEditingController();
    final genreController = TextEditingController();

    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Новая книга'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: titleController, decoration: const InputDecoration(labelText: 'Название')),
            const SizedBox(height: 8),
            TextField(controller: authorController, decoration: const InputDecoration(labelText: 'Автор')),
            const SizedBox(height: 8),
            TextField(controller: genreController, decoration: const InputDecoration(labelText: 'Жанр')),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Отмена')),
          FilledButton(
            onPressed: () async {
              try {
                await widget.repository.submitBookSuggestion(
                  title: titleController.text,
                  author: authorController.text,
                  genre: genreController.text,
                );
                if (!context.mounted) {
                  return;
                }
                Navigator.pop(context);
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Книга отправлена на сервер')),
                );
                await _reload();
              } catch (_) {
                if (!context.mounted) {
                  return;
                }
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Ошибка отправки. Проверьте API и повторите.')),
                );
              }
            },
            child: const Text('Отправить'),
          ),
        ],
      ),
    );
  }
}

class _HomeTopBar extends StatelessWidget {
  const _HomeTopBar({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        _HeaderButton(icon: Icons.menu),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            title,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
          ),
        ),
        const SizedBox(width: 10),
        _HeaderButton(icon: Icons.notifications_none),
      ],
    );
  }
}

class _HeaderButton extends StatelessWidget {
  const _HeaderButton({required this.icon});

  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 40,
      height: 40,
      decoration: BoxDecoration(
        color: const Color(0xFFE8D6C4),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Icon(icon, size: 20),
    );
  }
}

class _BookCover extends StatelessWidget {
  const _BookCover({required this.coverUrl, required this.size});

  final String coverUrl;
  final double size;

  @override
  Widget build(BuildContext context) {
    if (coverUrl.isEmpty) {
      return _placeholder();
    }

    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: Image.network(
        coverUrl,
        width: size,
        height: size,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => _placeholder(),
      ),
    );
  }

  Widget _placeholder() {
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: const Color(0xFFE9E3DC),
        borderRadius: BorderRadius.circular(8),
      ),
      child: const Icon(Icons.menu_book_outlined),
    );
  }
}

String _firstLetter(String text) {
  final value = text.trim();
  if (value.isEmpty) {
    return '•';
  }
  return value.characters.first;
}