import 'package:flash_app/features/auth/register_page.dart';
import 'package:flash_app/l10n/generated/app_localizations.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('l\'inscription démarre sur la saisie du numéro', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(
          locale: Locale('fr'),
          localizationsDelegates: [
            L10n.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: L10n.supportedLocales,
          home: RegisterPage(),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 400));

    expect(find.text('Numéro de téléphone'), findsOneWidget);
    expect(find.text('Continuer'), findsOneWidget);

    // Passe à l'étape du code secret.
    await tester.tap(find.text('Continuer'), warnIfMissed: false);
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('Choisissez un code secret'), findsOneWidget);
    expect(find.text('1'), findsOneWidget); // pavé numérique
  });
}
