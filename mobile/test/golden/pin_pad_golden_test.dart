import 'package:flash_app/core/theme/app_theme.dart';
import 'package:flash_app/shared/widgets/pin_pad.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// MOB-T2 — golden d'un écran clé (le pavé numérique) en clair et en sombre.
/// Régénérer : `flutter test --update-goldens`.
void main() {
  for (final name in ['light', 'dark']) {
    testWidgets('PinPad golden $name', (tester) async {
      final theme = name == 'light' ? AppTheme.light() : AppTheme.dark();
      await tester.pumpWidget(
        MaterialApp(
          theme: theme,
          home: const Scaffold(
            body: Center(
              child: SizedBox(
                width: 320,
                child: PinPad(length: 4, value: '24', onChanged: _noop),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await expectLater(
        find.byType(PinPad),
        matchesGoldenFile('goldens/pin_pad_$name.png'),
      );
    });
  }
}

void _noop(String _) {}
