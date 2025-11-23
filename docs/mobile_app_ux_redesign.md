# "Калейдоскоп книг" — новая UX/UI концепция Flutter-приложения

## Краткое резюме
- **Цель**: сделать приложение понятным с первого входа, визуально живым и анимированным, сохранив весь текущий функционал API без изменений на backend.
- **Подход**: ясная пяти-вкладочная навигация, плоская архитектура экранов, приоритет быстрых действий (добавить книгу, обновить прогресс, вступить в клуб).
- **Стиль**: светлый «бумажно-теплый» интерфейс с акцентными цветами, округлыми карточками, micro-interactions и плавными анимациями переходов/героев.

## Навигация и схема экранов
### Основные вкладки (Bottom Navigation)
1. **Дом** — приветствие, рекомендации, быстрые действия, актуальные клубы/марафоны.
2. **Мои книги** — списки по статусам, поиск/фильтры, быстрый прогресс.
3. **Читаю** — текущая книга(и), таймер/быстрый +N страниц/минут, дневник.
4. **Статистика** — графики, календарь чтения, фильтры по периоду/формату.
5. **Профиль** — карточка пользователя, подписка, настройки, печать/экспорт.

### Первые шаги / онбординг
- **Экран приветствия** → 2–3 слайда с основными сценариями (учёт книг, совместные чтения, статистика).
- **CTA**: «Войти» / «Создать аккаунт» + «Продолжить позже» (гостевой режим, если API поддерживает).
- После логина — переход на вкладку **Дом**.

### Переходы и вложенность (дерево)
- **Дом**
  - Быстрые действия: «Добавить книгу», «Начать чтение», «Присоединиться к клубу».
  - Блок «Активные клубы/марафоны» → экран «Совместное чтение» (детали + вступить/выйти + лента активности).
  - Рекомендации/подборки → карточка книги.
- **Мои книги**
  - Таб-контроллер: «Читаю», «Хочу», «Прочитал», «Отложено».
  - Поиск/сканер/ISBN → модальное окно добавления.
  - Карточка книги → детали книги (обложка, прогресс, заметки, статусы, формат).
- **Читаю**
  - Стек: текущая книга (или карусель, если несколько), быстрый прогресс +N страниц/минут, таймер, смена формата (бумага/электронная/аудио).
  - История прогресса (сворачиваемая лента).
- **Статистика**
  - Табы по периоду: День / Неделя / Месяц / Год.
  - Графики страниц/минут/книг, тепловая карта календаря.
  - Кнопка «Печать/Экспорт» (доступна подписчикам; для бесплатных — подсказка).
- **Профиль**
  - Карточка пользователя, уровни приватности, статус подписки.
  - Настройки уведомлений, темы, интеграции.
  - «Мои клубы/марафоны» → список → деталь.

## Описание ключевых экранов
### Дом
- **Блок заголовка**: приветствие, прогресс недели (mini chart).
- **Быстрые действия** (3 кнопки в одну строку с иконками): Добавить книгу, Обновить прогресс, Присоединиться к клубу.
- **Активные совместные чтения**: карусель карточек (обложка, срок, % группы, CTA «Открыть»).
- **Лента активности**: события клубов/друзей; свайпом раскрываются комментарии.

### Мои книги
- **Сегментированный контроллер статусов** (чипы).
- **Список карточек**: обложка, автор, статус, формат, прогресс-бар, кнопка «+» (открывает быстрый диалог прогресса).
- **Поиск/фильтр**: в AppBar с фильтрами по формату/статусу/тегам.
- **Флоат-кнопка**: «Добавить книгу» → модальный выбор «Поиск», «Скан ISBN/штрих-код», «Вручную».

### Деталь книги
- **Hero-анимация обложки** из списка.
- Прогресс-бар с кнопками «+5», «+10», «+20» страниц или «+5 мин» для аудио.
- **Формат**: переключатель (бумага/электронная/аудио).
- **Заметки и цитаты**: свернутый блок, тап — разворачивается.
- **История изменений**: таймлайн с датой/прогрессом/комментарием.
- **CTA**: «Отметить завершение» (открывает праздничный экран/диалог).

### Читаю (Now Reading)
- **Главная карта книги**: обложка + радиальный прогресс + таймер.
- **Кнопка «Старт таймер»** → анимация счетчика, пауза/стоп.
- **Свайп вверх**: история с горизонтальными вкладками (заметки / цитаты / статистика по книге).

### Совместные чтения / Клубы
- Список активных и архивных, фильтр по роли (организую/участвую).
- Карточка клуба: обложка книги, срок, участники-аватары, общий прогресс, кнопка «Вступить/Выйти».
- Деталь клуба: лента активности (чтение, комментарии), блок задач/этапов, чатовый ввод (если реализован через API).

### Статистика
- **Графики**: линии/столбцы для страниц/минут, пай-чарт форматов, тепловая карта календаря.
- **Фильтры**: период, формат, книги/аудио.
- **CTA**: «Печать/Экспорт» (открывает PDF/HTML, доступно подписчикам).
- **Сравнение с целями**: индикатор цели месяца.

### Профиль
- Аватар, имя, email/ник, статус подписки (бейдж).
- **Приватность**: переключатели видимости (книги, цели, клубы).
- **Подписка**: блок преимуществ, кнопка «Улучшить».
- **Настройки**: уведомления, темы, язык.
- **Выход / поддержка**: контакт/FAQ.

## Анимации и micro-interactions
- **Переходы вкладок**: `FadeThroughTransition` (Material 3) или `SharedAxisTransition` (X), с лёгким скейлом.
- **Hero**: обложки книг и аватары клубов между списками и деталями.
- **Добавление книги**: `Scale + Fade` на модальном окне; при успешном добавлении — чип «Добавлена» с пульсацией.
- **Обновление прогресса**: прогресс-бар с `TweenAnimationBuilder`; конфетти/частицы при больших скачках; haptic light.
- **Завершение книги**: полноэкранная карточка с Hero-обложкой, мягкая анимация ленты бумаги/конфетти в верхней части, кнопки «Поделиться»/«Оставить заметку»; авто-свернуть после подтверждения.
- **Вступление в клуб**: `Slide + Fade` баннер «Вы в клубе», аватары добавляются с `Scale` подпрыгиванием.
- **Раскрытие блоков** (история, заметки, фильтры): `AnimatedSize` + `ClipRect` с spring-анимацией.
- **Micro-interactions**:
  - Кнопки: `InkResponse` с волной + лёгкий `scale` при нажатии.
  - Чипы статусов: смена цвета/иконки с анимированным переходом.
  - Тянущийся AppBar при прокрутке (слегка увеличивает обложку).

## UI-гайд и стиль
- **Цвета**: базовый светлый фон `#F9F5EF`, акцент «янтарный» `#F4A261`, вторичный «глубокий синий» `#264653`, успешный `#2A9D8F`, предупреждение `#E76F51`. Темная тема — приглушенные аналоги.
- **Шрифты**: Sans (Inter/Manrope), заголовки — полужирные, текст — средний. Межстрочный > 1.4.
- **Карточки**: радиус 16–20, мягкие тени/подложки, большие поля.
- **Иконки**: понятные Material Symbols, единый стиль контура.
- **Иерархия**: крупный заголовок экрана, подзаголовок/фильтры, затем карточки/контент, CTA снизу.
- **Бейдж подписки**: мягкий градиент, ненавязчивое «PRO», текст подсказок для бесплатных функций.

## Рекомендации по архитектуре Flutter
- **Навигация**: `ShellRoute` (GoRouter) или `Scaffold` с `NavigationBar` (Material 3) для пяти вкладок; вложенные навигаторы для сохранения состояния вкладок.
- **Состояние**: `Riverpod`/`Provider` для зависимостей API; `Freezed`/`json_serializable` для моделей.
- **Темы**: `ThemeData` с `ColorScheme.fromSeed`, поддержка light/dark.
- **Списки**: `SliverAppBar` + `CustomScrollView` для эффекта растяжения, `ListView.separated` для карточек.
- **Графики**: пакет `fl_chart` или `syncfusion_flutter_charts` (если лицензия позволяет).

## Примерные фрагменты кода
### Навигация с сохранением состояния вкладок
```dart
class AppShell extends StatefulWidget {
  const AppShell({super.key});
  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int index = 0;
  final tabs = const [HomeScreen(), LibraryScreen(), NowReadingScreen(), StatsScreen(), ProfileScreen()];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: index, children: tabs),
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (i) => setState(() => index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), label: 'Дом'),
          NavigationDestination(icon: Icon(Icons.menu_book_outlined), label: 'Книги'),
          NavigationDestination(icon: Icon(Icons.auto_stories_outlined), label: 'Читаю'),
          NavigationDestination(icon: Icon(Icons.insights_outlined), label: 'Статистика'),
          NavigationDestination(icon: Icon(Icons.person_outline), label: 'Профиль'),
        ],
      ),
    );
  }
}
```

### Карточка книги с быстрым прогрессом
```dart
class BookCard extends StatelessWidget {
  final Book book;
  const BookCard({super.key, required this.book});

  @override
  Widget build(BuildContext context) {
    return Card(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Hero(
              tag: 'cover-${book.id}',
              child: ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: Image.network(book.coverUrl, width: 60, height: 90, fit: BoxFit.cover),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(book.title, style: Theme.of(context).textTheme.titleMedium),
                  Text(book.author, style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.grey[700])),
                  const SizedBox(height: 8),
                  TweenAnimationBuilder<double>(
                    tween: Tween(begin: 0, end: book.progress),
                    duration: const Duration(milliseconds: 450),
                    builder: (context, value, _) => LinearProgressIndicator(value: value, minHeight: 8),
                  ),
                  const SizedBox(height: 8),
                  Wrap(spacing: 8, children: [5, 10, 20].map((n) {
                    return ActionChip(
                      label: Text('+${n.toString()} стр'),
                      onPressed: () => context.read<ProgressNotifier>().addPages(book.id, n),
                    );
                  }).toList()),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
```

### Завершение книги — мини-праздник
```dart
Future<void> showFinishDialog(BuildContext context, Book book) async {
  return showDialog(
    context: context,
    builder: (_) => Dialog(
      insetPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 40),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
      child: Stack(
        alignment: Alignment.topCenter,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 80, 24, 24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('Книга завершена!', style: Theme.of(context).textTheme.headlineSmall),
                const SizedBox(height: 8),
                Text(book.title, textAlign: TextAlign.center),
                const SizedBox(height: 16),
                ElevatedButton.icon(
                  icon: const Icon(Icons.celebration_outlined),
                  label: const Text('Поделиться'),
                  onPressed: () => shareBook(book),
                ),
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Вернуться'),
                ),
              ],
            ),
          ),
          Positioned(
            top: 12,
            child: Hero(
              tag: 'cover-${book.id}',
              child: ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: Image.network(book.coverUrl, width: 96, height: 144, fit: BoxFit.cover),
              ),
            ),
          ),
          const _ConfettiOverlay(),
        ],
      ),
    ),
  );
}

class _ConfettiOverlay extends StatefulWidget {
  const _ConfettiOverlay();
  @override
  State<_ConfettiOverlay> createState() => _ConfettiOverlayState();
}

class _ConfettiOverlayState extends State<_ConfettiOverlay> with SingleTickerProviderStateMixin {
  late final AnimationController _c;
  @override
  void initState() {
    super.initState();
    _c = AnimationController(vsync: this, duration: const Duration(seconds: 2))..forward();
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: FadeTransition(
        opacity: CurvedAnimation(parent: _c, curve: Curves.easeOut),
        child: CustomPaint(
          painter: ConfettiPainter(animation: _c),
          size: const Size(double.infinity, 220),
        ),
      ),
    );
  }
}
```

## Что ещё может помочь
Если нужны дополнительные уточнения: примеры текущих экранов, брендбук (цвета/логотип), ограничения по библиотекам, политика по гостевому режиму, возможности API для поиска/сканера, статус поддержки Push/Deep Links.