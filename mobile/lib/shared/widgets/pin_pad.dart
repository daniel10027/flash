import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/theme/motion.dart';
import 'pressable.dart';

/// Clavier numérique + rangée de points. Retour haptique à chaque frappe,
/// petite secousse en cas d'erreur (via [errorSignal]).
class PinPad extends StatefulWidget {
  const PinPad({
    required this.length,
    required this.value,
    required this.onChanged,
    this.onCompleted,
    this.errorSignal = 0,
    this.biometricsButton = false,
    this.onBiometrics,
    super.key,
  });

  final int length;
  final String value;
  final ValueChanged<String> onChanged;
  final ValueChanged<String>? onCompleted;

  /// Incrémenter cette valeur déclenche l'animation d'erreur (shake).
  final int errorSignal;
  final bool biometricsButton;
  final VoidCallback? onBiometrics;

  @override
  State<PinPad> createState() => _PinPadState();
}

class _PinPadState extends State<PinPad> with SingleTickerProviderStateMixin {
  late final AnimationController _shake = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 460),
  );

  @override
  void didUpdateWidget(covariant PinPad old) {
    super.didUpdateWidget(old);
    if (widget.errorSignal != old.errorSignal) {
      _shake.forward(from: 0);
      HapticFeedback.heavyImpact();
    }
  }

  @override
  void dispose() {
    _shake.dispose();
    super.dispose();
  }

  void _tap(String d) {
    if (widget.value.length >= widget.length) return;
    HapticFeedback.selectionClick();
    final next = widget.value + d;
    widget.onChanged(next);
    if (next.length == widget.length) widget.onCompleted?.call(next);
  }

  void _back() {
    if (widget.value.isEmpty) return;
    HapticFeedback.selectionClick();
    widget.onChanged(widget.value.substring(0, widget.value.length - 1));
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        AnimatedBuilder(
          animation: _shake,
          builder: (context, child) {
            // 3 oscillations amorties : sin(3·2π·t) · (1 − t).
            final t = _shake.value;
            final dx = math.sin(t * 3 * 2 * math.pi) * 12 * (1 - t);
            return Transform.translate(offset: Offset(dx, 0), child: child);
          },
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: List.generate(widget.length, (i) {
              final filled = i < widget.value.length;
              return AnimatedContainer(
                duration: Motion.fast,
                curve: Motion.emphasized,
                margin: const EdgeInsets.symmetric(horizontal: 9),
                width: filled ? 16 : 12,
                height: filled ? 16 : 12,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: filled ? scheme.primary : scheme.outlineVariant,
                ),
              );
            }),
          ),
        ),
        const SizedBox(height: 28),
        for (final row in const [
          ['1', '2', '3'],
          ['4', '5', '6'],
          ['7', '8', '9'],
        ])
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [for (final d in row) _key(d, onTap: () => _tap(d))],
          ),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            widget.biometricsButton
                ? _key(
                    '',
                    icon: Icons.fingerprint,
                    onTap: widget.onBiometrics,
                  )
                : const SizedBox(width: 84, height: 84),
            _key('0', onTap: () => _tap('0')),
            _key('', icon: Icons.backspace_outlined, onTap: _back),
          ],
        ),
      ],
    );
  }

  Widget _key(String label, {IconData? icon, VoidCallback? onTap}) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.all(6),
      child: Pressable(
        onTap: onTap,
        scale: 0.9,
        child: Container(
          width: 72,
          height: 72,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: scheme.surfaceContainerHighest.withValues(alpha: 0.6),
          ),
          child: icon != null
              ? Icon(icon, size: 24, color: scheme.onSurface)
              : Text(
                  label,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                ),
        ),
      ),
    );
  }
}
