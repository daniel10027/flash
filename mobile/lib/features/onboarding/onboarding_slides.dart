import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../core/theme/tokens.dart';

class OnboardSlide {
  const OnboardSlide({
    required this.color,
    required this.icon,
  });

  final Color color;
  final IconData icon;
}

const onboardSlides = <OnboardSlide>[
  OnboardSlide(color: FlashColors.brand500, icon: Icons.bolt),
  OnboardSlide(color: FlashColors.brand700, icon: Icons.qr_code_scanner),
  OnboardSlide(color: FlashColors.accent700, icon: Icons.savings_outlined),
];

/// Illustration animée : anneaux pulsés + particules en orbite autour d'une
/// icône. Légère (CustomPaint), zéro asset.
class SparkIllustration extends StatefulWidget {
  const SparkIllustration({required this.icon, super.key});
  final IconData icon;

  @override
  State<SparkIllustration> createState() => _SparkIllustrationState();
}

class _SparkIllustrationState extends State<SparkIllustration>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 6),
  )..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 240,
      height: 240,
      child: AnimatedBuilder(
        animation: _c,
        builder: (context, _) => CustomPaint(
          painter: _SparkPainter(_c.value),
          child: Center(
            child: Container(
              width: 96,
              height: 96,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white.withValues(alpha: 0.16),
                border: Border.all(color: Colors.white.withValues(alpha: 0.4)),
              ),
              child: Icon(widget.icon, size: 44, color: Colors.white),
            ),
          ),
        ),
      ),
    );
  }
}

class _SparkPainter extends CustomPainter {
  _SparkPainter(this.t);
  final double t;

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final ring = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4
      ..color = Colors.white.withValues(alpha: 0.25);
    for (var i = 0; i < 3; i++) {
      final r = 60.0 + i * 26 + math.sin((t + i / 3) * 2 * math.pi) * 6;
      canvas.drawCircle(center, r, ring);
    }

    final dot = Paint()..color = Colors.white.withValues(alpha: 0.9);
    for (var i = 0; i < 14; i++) {
      final a = (i / 14) * 2 * math.pi + t * 2 * math.pi;
      final pulse = (math.sin((t * 2 + i) * math.pi) + 1) / 2;
      final radius = 70 + pulse * 42;
      final p = center + Offset(math.cos(a), math.sin(a)) * radius;
      canvas.drawCircle(p, 2.4 + pulse * 2, dot);
    }
  }

  @override
  bool shouldRepaint(_SparkPainter old) => old.t != t;
}
