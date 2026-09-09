import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../core/theme/tokens.dart';

/// Fond animé « aurore » : deux halos bordeaux qui dérivent lentement.
/// Utilisé sous l'onboarding et les écrans d'authentification.
class BrandBackground extends StatefulWidget {
  const BrandBackground({this.child, this.intensity = 1.0, super.key});

  final Widget? child;
  final double intensity;

  @override
  State<BrandBackground> createState() => _BrandBackgroundState();
}

class _BrandBackgroundState extends State<BrandBackground>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 18),
  )..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    return AnimatedBuilder(
      animation: _c,
      builder: (context, child) {
        return CustomPaint(
          painter: _AuroraPainter(
            t: _c.value,
            dark: dark,
            intensity: widget.intensity,
          ),
          child: child,
        );
      },
      child: widget.child,
    );
  }
}

class _AuroraPainter extends CustomPainter {
  _AuroraPainter(
      {required this.t, required this.dark, required this.intensity});

  final double t;
  final bool dark;
  final double intensity;

  @override
  void paint(Canvas canvas, Size size) {
    final bg = Paint()
      ..color = dark ? FlashColors.neutral900 : FlashColors.neutral0;
    canvas.drawRect(Offset.zero & size, bg);

    void halo(Offset base, Color color, double radius, double phase) {
      final dx = math.sin((t + phase) * 2 * math.pi) * 60;
      final dy = math.cos((t + phase) * 2 * math.pi) * 40;
      final center = base + Offset(dx, dy);
      final paint = Paint()
        ..shader = RadialGradient(
          colors: [
            color.withValues(alpha: 0.55 * intensity),
            color.withValues(alpha: 0),
          ],
        ).createShader(Rect.fromCircle(center: center, radius: radius))
        ..blendMode = BlendMode.plus;
      canvas.drawCircle(center, radius, paint);
    }

    halo(
      Offset(size.width * 0.22, size.height * 0.18),
      dark ? FlashColors.brand400 : FlashColors.brand300,
      size.width * 0.7,
      0,
    );
    halo(
      Offset(size.width * 0.85, size.height * 0.5),
      dark ? FlashColors.brand600 : FlashColors.brand200,
      size.width * 0.8,
      0.4,
    );
    halo(
      Offset(size.width * 0.5, size.height * 0.95),
      FlashColors.accent500,
      size.width * 0.6,
      0.75,
    );
  }

  @override
  bool shouldRepaint(_AuroraPainter old) =>
      old.t != t || old.dark != dark || old.intensity != intensity;
}
