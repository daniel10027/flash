import 'dart:ui';

import 'package:flutter/material.dart';

import '../../core/theme/tokens.dart';

/// Carte translucide (effet verre dépoli). Sur fond animé, elle « flotte ».
class GlassCard extends StatelessWidget {
  const GlassCard({
    required this.child,
    this.padding = const EdgeInsets.all(20),
    this.radius = FlashRadii.lg,
    super.key,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final double radius;

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
        child: Container(
          padding: padding,
          decoration: BoxDecoration(
            color: (dark ? Colors.white : Colors.white).withValues(
              alpha: dark ? 0.06 : 0.7,
            ),
            borderRadius: BorderRadius.circular(radius),
            border: Border.all(
              color: Colors.white.withValues(alpha: dark ? 0.12 : 0.6),
            ),
          ),
          child: child,
        ),
      ),
    );
  }
}
