import 'package:flutter/material.dart';

import '../../core/network/api_exception.dart';
import '../../core/theme/tokens.dart';

enum _Kind { info, success, error }

/// Toasts cohérents. `AppSnack.error(context, e)` sait afficher une
/// [ApiException] / [NetworkException] proprement.
abstract final class AppSnack {
  static void info(BuildContext context, String message) =>
      _show(context, message, _Kind.info);

  static void success(BuildContext context, String message) =>
      _show(context, message, _Kind.success);

  static void error(BuildContext context, Object error) {
    final message = switch (error) {
      ApiException e => e.friendly,
      NetworkException _ => 'Pas de connexion. Réessayez.',
      _ => 'Une erreur est survenue.',
    };
    _show(context, message, _Kind.error);
  }

  static void _show(BuildContext context, String message, _Kind kind) {
    final scheme = Theme.of(context).colorScheme;
    final (bg, fg, icon) = switch (kind) {
      _Kind.success => (
          FlashColors.successBg,
          FlashColors.successFg,
          Icons.check_circle
        ),
      _Kind.error => (
          FlashColors.dangerBg,
          FlashColors.dangerFg,
          Icons.error_outline
        ),
      _Kind.info => (
          scheme.surfaceContainerHighest,
          scheme.onSurface,
          Icons.info_outline
        ),
    };
    ScaffoldMessenger.of(context)
      ..clearSnackBars()
      ..showSnackBar(
        SnackBar(
          backgroundColor: bg,
          content: Row(
            children: [
              Icon(icon, color: fg, size: 20),
              const SizedBox(width: 10),
              Expanded(child: Text(message, style: TextStyle(color: fg))),
            ],
          ),
        ),
      );
  }
}
