import 'dart:math' as math;

import 'package:flutter/material.dart';

class FinishCelebrationData {
  FinishCelebrationData({
    required this.title,
    required this.rewardText,
    this.coverUrl,
  });

  final String title;
  final String rewardText;
  final String? coverUrl;
}

class FinishBookCelebration extends StatefulWidget {
  const FinishBookCelebration({
    super.key,
    required this.data,
    required this.onClose,
  });

  final FinishCelebrationData data;
  final VoidCallback onClose;

  @override
  State<FinishBookCelebration> createState() => _FinishBookCelebrationState();
}

class _FinishBookCelebrationState extends State<FinishBookCelebration>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _overlay;
  late final Animation<double> _glow;
  late final Animation<double> _edge;
  late final Animation<double> _trophyScale;
  late final Animation<Offset> _textSlide;
  late final List<_StarSpec> _stars;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 6000),
    )..forward();

    _overlay = CurvedAnimation(
      parent: _controller,
      curve: const Interval(0, 0.25, curve: Curves.easeOut),
    );
    _glow = CurvedAnimation(
      parent: _controller,
      curve: const Interval(0.1, 0.45, curve: Curves.easeOut),
    );
    _edge = CurvedAnimation(
      parent: _controller,
      curve: const Interval(0.2, 0.7, curve: Curves.easeInOut),
    );
    _trophyScale = CurvedAnimation(
      parent: _controller,
      curve: const Interval(0.55, 0.95, curve: Curves.elasticOut),
    );
    _textSlide = Tween(begin: const Offset(0, 0.25), end: Offset.zero).animate(
      CurvedAnimation(
        parent: _controller,
        curve: const Interval(0.65, 1, curve: Curves.easeOut),
      ),
    );

    _stars = [
      const _StarSpec(alignment: Alignment(-0.8, -0.05), start: 0.08, end: 0.9, size: 18, rotation: -0.35, horizontalDrift: 12, verticalLift: -36, wobbleTurns: 1.4),
      const _StarSpec(alignment: Alignment(0.85, 0.05), start: 0.06, end: 0.92, size: 18, rotation: 0.4, horizontalDrift: 10, verticalLift: -34, wobbleTurns: 1.6),
      const _StarSpec(alignment: Alignment(-0.5, -0.35), start: 0.12, end: 0.94, size: 22, rotation: 0.2, horizontalDrift: 8, verticalLift: -42, wobbleTurns: 1.2),
      const _StarSpec(alignment: Alignment(0.55, -0.3), start: 0.14, end: 0.96, size: 22, rotation: -0.15, horizontalDrift: 14, verticalLift: -40, wobbleTurns: 1.35),
      const _StarSpec(alignment: Alignment(-0.15, -0.55), start: 0.18, end: 0.98, size: 26, rotation: 0.1, horizontalDrift: 6, verticalLift: -44, wobbleTurns: 1.1),
      const _StarSpec(alignment: Alignment(0.2, 0.0), start: 0.22, end: 0.94, size: 16, rotation: -0.25, horizontalDrift: 10, verticalLift: -32, wobbleTurns: 1.8),
      const _StarSpec(alignment: Alignment(-0.1, 0.3), start: 0.24, end: 0.98, size: 14, rotation: 0.3, horizontalDrift: 12, verticalLift: -28, wobbleTurns: 2.0),
      const _StarSpec(alignment: Alignment(0.35, 0.25), start: 0.28, end: 1.0, size: 16, rotation: -0.4, horizontalDrift: 9, verticalLift: -30, wobbleTurns: 1.6),
      const _StarSpec(alignment: Alignment(0.0, -0.1), start: 0.1, end: 0.95, size: 20, rotation: 0.18, horizontalDrift: 16, verticalLift: -38, wobbleTurns: 1.75),
      const _StarSpec(alignment: Alignment(-0.65, 0.15), start: 0.32, end: 0.98, size: 17, rotation: -0.2, horizontalDrift: 11, verticalLift: -33, wobbleTurns: 1.5),
      const _StarSpec(alignment: Alignment(0.7, -0.55), start: 0.36, end: 1.0, size: 19, rotation: 0.28, horizontalDrift: 15, verticalLift: -46, wobbleTurns: 1.4),
      const _StarSpec(alignment: Alignment(-0.35, -0.75), start: 0.2, end: 0.88, size: 18, rotation: -0.22, horizontalDrift: 7, verticalLift: -48, wobbleTurns: 1.25),
      const _StarSpec(alignment: Alignment(0.6, 0.45), start: 0.42, end: 1.0, size: 15, rotation: 0.35, horizontalDrift: 10, verticalLift: -26, wobbleTurns: 1.9),
      const _StarSpec(alignment: Alignment(-0.45, 0.55), start: 0.46, end: 1.0, size: 15, rotation: -0.3, horizontalDrift: 10, verticalLift: -24, wobbleTurns: 1.65),
    ];
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Material(
      color: Colors.black54,
      child: SafeArea(
        child: Stack(
          alignment: Alignment.center,
          children: [
            FadeTransition(
              opacity: _overlay,
              child: Container(color: Colors.black.withOpacity(0.65)),
            ),
            ScaleTransition(
              scale: _trophyScale,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Stack(
                    clipBehavior: Clip.none,
                    children: [
                      Container(
                        width: 260,
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(24),
                          boxShadow: const [
                            BoxShadow(
                              color: Colors.black26,
                              blurRadius: 24,
                              offset: Offset(0, 16),
                            ),
                          ],
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            ClipRRect(
                              borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
                              child: SizedBox(
                                height: 220,
                                child: widget.data.coverUrl != null
                                    ? Image.network(
                                        widget.data.coverUrl!,
                                        fit: BoxFit.cover,
                                        errorBuilder: (_, __, ___) => _buildCoverFallback(),
                                      )
                                    : _buildCoverFallback(),
                              ),
                            ),
                            const SizedBox(height: 16),
                            Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 18),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Icon(Icons.auto_awesome_rounded, color: Colors.amber.shade600),
                                      const SizedBox(width: 8),
                                      Text(
                                        'Отличная работа!',
                                        style: theme.textTheme.titleSmall?.copyWith(
                                          color: const Color(0xFF23353D),
                                          fontWeight: FontWeight.bold,
                                        ),
                                      ),
                                    ],
                                  ),
                                  const SizedBox(height: 10),
                                  Text(
                                    widget.data.title,
                                    style: theme.textTheme.titleMedium?.copyWith(
                                      color: const Color(0xFF1F2F35),
                                      fontWeight: FontWeight.w800,
                                    ),
                                  ),
                                  const SizedBox(height: 8),
                                  Text(
                                    widget.data.rewardText,
                                    style: theme.textTheme.bodyMedium?.copyWith(
                                      color: const Color(0xFF42535B),
                                    ),
                                  ),
                                  const SizedBox(height: 18),
                                  Row(
                                    children: [
                                      _buildTrophy(theme),
                                      const Spacer(),
                                      FilledButton.icon(
                                        style: FilledButton.styleFrom(
                                          backgroundColor: const Color(0xFF23353D),
                                          foregroundColor: Colors.white,
                                          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
                                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                                        ),
                                        onPressed: widget.onClose,
                                        icon: const Icon(Icons.close),
                                        label: const Text('Закрыть'),
                                      ),
                                    ],
                                  ),
                                  const SizedBox(height: 18),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                      Positioned(
                        top: -42,
                        left: 0,
                        right: 0,
                        child: FadeTransition(
                          opacity: _glow,
                          child: Align(
                            alignment: Alignment.center,
                            child: Container(
                              width: 120,
                              height: 120,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: const Color(0xFFF8D775).withOpacity(0.4),
                                boxShadow: const [
                                  BoxShadow(
                                    color: Color(0xFFFFE9A5),
                                    blurRadius: 18,
                                    spreadRadius: 2,
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),
                      Positioned(
                        top: -32,
                        left: 0,
                        right: 0,
                        child: ScaleTransition(
                          scale: _trophyScale,
                          child: const Icon(
                            Icons.emoji_events,
                            size: 72,
                            color: Color(0xFFF4C430),
                          ),
                        ),
                      ),
                      Positioned.fill(child: _buildStarConfetti()),
                    ],
                  ),
                  const SizedBox(height: 28),
                  SlideTransition(
                    position: _textSlide,
                    child: AnimatedBuilder(
                      animation: _edge,
                      builder: (context, child) {
                        return Opacity(
                          opacity: _edge.value,
                          child: child,
                        );
                      },
                      child: Column(
                        children: [
                          Text(
                            'Книга прочитана! 🎉',
                            style: theme.textTheme.titleMedium?.copyWith(
                              color: Colors.white,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                          const SizedBox(height: 6),
                          Text(
                            'Достижение сохранено, продолжайте в том же духе!',
                            style: theme.textTheme.bodyMedium?.copyWith(color: Colors.white70),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCoverFallback() {
    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF23353D),
        gradient: LinearGradient(
          colors: [Color(0xFF263A42), Color(0xFF3F535F)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      alignment: Alignment.center,
      child: const Icon(Icons.auto_stories, color: Colors.white70, size: 42),
    );
  }

  Widget _buildTrophy(ThemeData theme) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: const [
          BoxShadow(color: Colors.black26, blurRadius: 16, offset: Offset(0, 8)),
        ],
        border: Border.all(color: Colors.amber.shade200, width: 2),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.emoji_events, color: Colors.amber.shade600, size: 26),
          const SizedBox(width: 8),
          Text(
            'Книга прочитана',
            style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
          ),
        ],
      ),
    );
  }

  Widget _buildStarConfetti() {
    return Positioned.fill(
      child: IgnorePointer(
        child: Stack(
          children: _stars.map(_buildStar).toList(),
        ),
      ),
    );
  }

  Widget _buildStar(_StarSpec spec) {
    final animation = CurvedAnimation(
      parent: _controller,
      curve: Interval(spec.start, spec.end, curve: Curves.easeOut),
    );

    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        final progress = animation.value;
        final opacity = Curves.easeIn.transform(progress.clamp(0.0, 1.0));
        final eased = Curves.easeOutCubic.transform(progress);
        final scale = Tween<double>(begin: 0.35, end: 1.05).transform(eased);
        final verticalShift = Tween<double>(begin: 12, end: spec.verticalLift)
            .transform(eased);
        final wobble =
            math.sin(progress * math.pi * spec.wobbleTurns) * spec.horizontalDrift;
        final rotation =
            spec.rotation + math.sin(progress * math.pi * 1.1) * 0.28;

        return Align(
          alignment: spec.alignment,
          child: Opacity(
            opacity: opacity,
            child: Transform.translate(
              offset: Offset(wobble, verticalShift),
              child: Transform.scale(
                scale: scale,
                child: Transform.rotate(
                  angle: rotation,
                  child: Container(
                    decoration: BoxDecoration(
                      boxShadow: [
                        BoxShadow(
                          color: Colors.amber.withOpacity(0.55 * opacity),
                          blurRadius: 12,
                          spreadRadius: 1,
                        ),
                      ],
                    ),
                    child: Icon(
                      Icons.star_rounded,
                      color: Colors.amber.shade300,
                      size: spec.size,
                    ),
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class _StarSpec {
  const _StarSpec({
    required this.alignment,
    required this.start,
    required this.end,
    required this.size,
    required this.rotation,
    this.horizontalDrift = 0,
    this.verticalLift = -26,
    this.wobbleTurns = 1.0,
  });

  final Alignment alignment;
  final double start;
  final double end;
  final double size;
  final double rotation;
  final double horizontalDrift;
  final double verticalLift;
  final double wobbleTurns;
}