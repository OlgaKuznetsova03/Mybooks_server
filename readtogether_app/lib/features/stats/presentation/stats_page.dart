import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../../../core/models/feed_models.dart';
import '../../../core/repositories/read_together_repository.dart';

class StatsPage extends StatelessWidget {
  const StatsPage({super.key, required this.repository});

  final ReadTogetherRepository repository;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: FutureBuilder<StatsPayload>(
        future: repository.fetchStats(),
        builder: (context, snapshot) {
          if (!snapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final stats = snapshot.data!;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text('Статистика чтения', style: Theme.of(context).textTheme.headlineSmall),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Книжный вызов'),
                      const SizedBox(height: 8),
                      LinearProgressIndicator(value: stats.challengeProgress / 100),
                      const SizedBox(height: 6),
                      Text('${stats.challengeProgress}% выполнено'),
                    ],
                  ),
                ),
              ),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: SizedBox(
                    height: 220,
                    child: BarChart(
                      BarChartData(
                        borderData: FlBorderData(show: false),
                        gridData: const FlGridData(show: false),
                        titlesData: const FlTitlesData(show: false),
                        barGroups: [
                          for (var i = 0; i < stats.booksPerMonth.length; i++)
                            BarChartGroupData(x: i, barRods: [BarChartRodData(toY: stats.booksPerMonth[i].toDouble())]),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Календарь чтения'),
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: stats.readingCalendar
                            .map(
                              (value) => Container(
                                width: 36,
                                height: 36,
                                decoration: BoxDecoration(
                                  color: value == 1 ? Colors.green : Colors.grey.shade300,
                                  borderRadius: BorderRadius.circular(8),
                                ),
                              ),
                            )
                            .toList(),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}