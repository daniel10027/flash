import 'package:flash_app/app.dart';
import 'package:flash_app/core/storage/prefs.dart';
import 'package:flash_app/features/settings/settings_page.dart';
import 'package:flash_app/l10n/generated/app_localizations.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('Paramètres : bascule le thème et persiste', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final sp = await SharedPreferences.getInstance();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [prefsProvider.overrideWithValue(Prefs(sp))],
        child: const MaterialApp(
          locale: Locale('fr'),
          localizationsDelegates: [
            L10n.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: L10n.supportedLocales,
          home: SettingsPage(),
        ),
      ),
    );

    expect(find.text('Sombre'), findsOneWidget);
    await tester.tap(find.text('Sombre'));
    await tester.pump();
    expect(sp.getString('flash.themeMode'), 'dark');
  });

  test('ThemeModeController lit et écrit Prefs', () async {
    SharedPreferences.setMockInitialValues({'flash.themeMode': 'light'});
    final prefs = Prefs(await SharedPreferences.getInstance());
    final c = ThemeModeController(prefs);
    expect(c.state, ThemeMode.light);
    c.set(ThemeMode.dark);
    expect(prefs.themeMode, ThemeMode.dark);
  });
}
