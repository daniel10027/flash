import 'package:flutter/material.dart';

import '../../core/theme/motion.dart';
import 'pressable.dart';

/// Bouton principal : plein, hauteur fixe, état `loading` intégré, léger
/// enfoncement au toucher.
class PrimaryButton extends StatelessWidget {
  const PrimaryButton({
    required this.label,
    this.onPressed,
    this.loading = false,
    this.icon,
    this.expand = true,
    super.key,
  });

  final String label;
  final VoidCallback? onPressed;
  final bool loading;
  final IconData? icon;
  final bool expand;

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null && !loading;
    final child = FilledButton(
      onPressed: enabled ? onPressed : null,
      child: AnimatedSwitcher(
        duration: Motion.base,
        child: loading
            ? const SizedBox(
                key: ValueKey('spin'),
                width: 22,
                height: 22,
                child: CircularProgressIndicator(
                  strokeWidth: 2.4,
                  color: Colors.white,
                ),
              )
            : Row(
                key: const ValueKey('label'),
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (icon != null) ...[Icon(icon, size: 20), const SizedBox(width: 8)],
                  Text(label),
                ],
              ),
      ),
    );

    final wrapped = Pressable(
      onTap: enabled ? onPressed : null,
      child: AbsorbPointer(child: child),
    );

    return expand ? SizedBox(width: double.infinity, child: wrapped) : wrapped;
  }
}
