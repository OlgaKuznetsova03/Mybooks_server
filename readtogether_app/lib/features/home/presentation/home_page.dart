import 'package:flutter/material.dart';

import '../../../core/models/feed_models.dart';
import '../../../core/repositories/read_together_repository.dart';

class HomePage extends StatelessWidget {
  const HomePage({super.key, required this.repository});

  final ReadTogetherRepository repository;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: FutureBuilder<HomePayload>(
        future: repository.fetchHome(),
        builder: (context, snapshot) {
          if (!snapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final data = snapshot.data!;
          return RefreshIndicator(
            onRefresh: () => repository.fetchHome(),
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text('Вы читаете сейчас', style: Theme.of(context).textTheme.titleLarge),
                Card(
                  child: ListTile(
                    title: Text(data.currentBook.title),
                    subtitle: Text('${data.currentBook.author} · ${data.currentBook.progress}%'),
                    trailing: const Icon(Icons.arrow_forward_ios, size: 16),
                  ),
                ),
                const SizedBox(height: 8),
                Text('Лента актуальных чтений', style: Theme.of(context).textTheme.titleLarge),
                ...data.readingFeed.map(
                  (item) => Card(
                    child: ListTile(
                      leading: CircleAvatar(child: Text(item.userName.characters.first)),
                      title: Text(item.userName),
                      subtitle: Text('${item.bookTitle} · ${item.pagesRead} стр.'),
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                _offersSection(context, 'Предложения авторов', data.authorOffers),
                _offersSection(context, 'Предложения блогеров', data.bloggerOffers),
                Text('Марафоны и совместные чтения', style: Theme.of(context).textTheme.titleLarge),
                ...data.marathons.map((m) => Card(child: ListTile(title: Text(m.name), subtitle: Text('Участников: ${m.participants}')))),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _offersSection(BuildContext context, String title, List<CollaborationOffer> offers) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: Theme.of(context).textTheme.titleLarge),
        ...offers.map((offer) => Card(child: ListTile(title: Text(offer.title), subtitle: Text(offer.subtitle)))),
      ],
    );
  }
}