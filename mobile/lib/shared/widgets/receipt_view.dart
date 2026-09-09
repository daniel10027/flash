import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';

import '../../core/theme/tokens.dart';

/// Reçu générique : succès animé + paires clé/valeur issues d'une map JSON.
class ReceiptView extends StatelessWidget {
  const ReceiptView({required this.data, this.title = 'Reçu', super.key});

  final Map<String, dynamic> data;
  final String title;

  @override
  Widget build(BuildContext context) {
    final rows = data.entries
        .where((e) => e.value != null && e.value is! Map && e.value is! List)
        .toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.check_circle, size: 64, color: FlashColors.successFg)
            .animate()
            .scale(
              begin: const Offset(0.4, 0.4),
              curve: Curves.elasticOut,
              duration: 650.ms,
            ),
        const SizedBox(height: 12),
        Text(
          title,
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.titleLarge,
        ),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.surfaceContainerHighest,
            borderRadius: BorderRadius.circular(FlashRadii.md),
          ),
          child: Column(
            children: [
              for (final r in rows)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Text(
                          r.key.replaceAll('_', ' '),
                          style: TextStyle(color: Theme.of(context).hintColor),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Flexible(
                        child: Text(
                          '${r.value}',
                          textAlign: TextAlign.right,
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ).animate().fadeIn(delay: 200.ms),
      ],
    );
  }
}
