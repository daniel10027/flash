import 'package:flutter/material.dart';

import '../../core/theme/motion.dart';

/// Une étape du didacticiel : une cible à mettre en lumière + un texte.
class CoachStep {
  const CoachStep({
    required this.key,
    required this.title,
    required this.body,
    this.shape = BoxShape.rectangle,
  });

  final GlobalKey key;
  final String title;
  final String body;
  final BoxShape shape;
}

/// Affiche un parcours guidé : voile sombre + trou de lumière autour de chaque
/// cible, carte d'explication, bouton « Suivant » / « Compris ».
Future<void> showCoachMarks(
  BuildContext context, {
  required List<CoachStep> steps,
  VoidCallback? onDone,
}) async {
  final valid = steps
      .where((s) => s.key.currentContext?.findRenderObject() is RenderBox)
      .toList();
  if (valid.isEmpty) {
    onDone?.call();
    return;
  }

  final overlay = Overlay.of(context);
  late OverlayEntry entry;
  var index = 0;

  void close() {
    entry.remove();
    onDone?.call();
  }

  entry = OverlayEntry(
    builder: (context) => _CoachLayer(
      step: valid[index],
      isLast: index == valid.length - 1,
      progress: '${index + 1}/${valid.length}',
      onNext: () {
        if (index == valid.length - 1) {
          close();
        } else {
          index++;
          entry.markNeedsBuild();
        }
      },
      onSkip: close,
    ),
  );
  overlay.insert(entry);
}

class _CoachLayer extends StatelessWidget {
  const _CoachLayer({
    required this.step,
    required this.isLast,
    required this.progress,
    required this.onNext,
    required this.onSkip,
  });

  final CoachStep step;
  final bool isLast;
  final String progress;
  final VoidCallback onNext;
  final VoidCallback onSkip;

  @override
  Widget build(BuildContext context) {
    final box = step.key.currentContext!.findRenderObject()! as RenderBox;
    final topLeft = box.localToGlobal(Offset.zero);
    final rect = topLeft & box.size;
    final inflated = rect.inflate(8);
    final screen = MediaQuery.sizeOf(context);
    final below = inflated.bottom + 180 < screen.height;

    return Material(
      color: Colors.transparent,
      child: Stack(
        children: [
          // Voile percé.
          Positioned.fill(
            child: TweenAnimationBuilder<double>(
              tween: Tween(begin: 0, end: 1),
              duration: Motion.base,
              curve: Motion.standard,
              builder: (context, t, _) => CustomPaint(
                painter: _ScrimPainter(
                  hole: inflated,
                  radius: step.shape == BoxShape.circle
                      ? inflated.longestSide / 2
                      : 16,
                  opacity: 0.78 * t,
                ),
              ),
            ),
          ),
          // Carte d'explication.
          Positioned(
            left: 20,
            right: 20,
            top: below ? inflated.bottom + 16 : null,
            bottom: below ? null : screen.height - inflated.top + 16,
            child: _Bubble(
              title: step.title,
              body: step.body,
              progress: progress,
              isLast: isLast,
              onNext: onNext,
              onSkip: onSkip,
            ),
          ),
        ],
      ),
    );
  }
}

class _ScrimPainter extends CustomPainter {
  _ScrimPainter({
    required this.hole,
    required this.radius,
    required this.opacity,
  });

  final Rect hole;
  final double radius;
  final double opacity;

  @override
  void paint(Canvas canvas, Size size) {
    final scrim = Path()..addRect(Offset.zero & size);
    final cut = Path()
      ..addRRect(RRect.fromRectAndRadius(hole, Radius.circular(radius)));
    canvas.drawPath(
      Path.combine(PathOperation.difference, scrim, cut),
      Paint()..color = Colors.black.withValues(alpha: opacity),
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(hole, Radius.circular(radius)),
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2
        ..color = Colors.white.withValues(alpha: 0.9),
    );
  }

  @override
  bool shouldRepaint(_ScrimPainter old) =>
      old.hole != hole || old.opacity != opacity;
}

class _Bubble extends StatelessWidget {
  const _Bubble({
    required this.title,
    required this.body,
    required this.progress,
    required this.isLast,
    required this.onNext,
    required this.onSkip,
  });

  final String title;
  final String body;
  final String progress;
  final bool isLast;
  final VoidCallback onNext;
  final VoidCallback onSkip;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: Motion.base,
      curve: Motion.emphasized,
      builder: (context, t, child) => Opacity(
        opacity: t.clamp(0, 1),
        child:
            Transform.translate(offset: Offset(0, (1 - t) * 12), child: child),
      ),
      child: Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: scheme.surface,
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.2),
              blurRadius: 24,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    title,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                Text(
                  progress,
                  style: Theme.of(context).textTheme.labelMedium?.copyWith(
                        color: Theme.of(context).hintColor,
                      ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(body, style: Theme.of(context).textTheme.bodyMedium),
            const SizedBox(height: 14),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                if (!isLast)
                  TextButton(onPressed: onSkip, child: const Text('Passer')),
                const SizedBox(width: 8),
                FilledButton(
                  onPressed: onNext,
                  style: FilledButton.styleFrom(
                    minimumSize: const Size(96, 44),
                  ),
                  child: Text(isLast ? 'Compris' : 'Suivant'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
