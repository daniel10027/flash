import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';

import '../../l10n/generated/app_localizations.dart';
import '../../shared/widgets/common.dart';

/// Écran d'onglet provisoire — remplacé par les vrais écrans (MOB-017…).
class PlaceholderPage extends StatelessWidget {
  const PlaceholderPage({required this.title, super.key});
  final String title;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: EmptyState(
        icon: Icons.auto_awesome,
        title: title,
        message: L10n.of(context).comingSoon,
      ).animate().fadeIn(duration: 300.ms),
    );
  }
}
