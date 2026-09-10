import 'package:flash_app/core/network/api_client.dart';
import 'package:flash_app/core/storage/prefs.dart';
import 'package:flash_app/features/home/home_page.dart';
import 'package:flash_app/l10n/generated/app_localizations.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'support/fake_api.dart';

void main() {
  testWidgets('le tableau de bord affiche le solde disponible', (tester) async {
    SharedPreferences.setMockInitialValues({'flash.homeTutorial': true});
    final prefs = Prefs(await SharedPreferences.getInstance());
    final api = FakeApiClient()
      ..route('/v1/wallets', {
        'wallets': [
          {
            'id': 'w1',
            'currency': 'XOF',
            'available_minor': 125000,
            'reserved_minor': 0,
            'status': 'ACTIVE',
          },
        ],
      })
      ..route('/v1/kyc/status', {'tier': 1, 'status': 'VERIFIED'})
      ..route('/v1/statement', {'lines': [], 'next_cursor': null})
      ..route('/v1/notifications', {'notifications': [], 'unread': 0});

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          prefsProvider.overrideWithValue(prefs),
          apiClientProvider.overrideWithValue(api),
        ],
        child: const MaterialApp(
          locale: Locale('fr'),
          localizationsDelegates: [
            L10n.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: L10n.supportedLocales,
          home: HomePage(),
        ),
      ),
    );
    await tester.pumpAndSettle(const Duration(seconds: 2));

    expect(find.text('Solde disponible'), findsOneWidget);
    expect(
      find.byWidgetPredicate(
        (w) =>
            w is Text &&
            (w.data ?? '').replaceAll(RegExp(r'\D'), '') == '125000',
      ),
      findsWidgets,
    );
  });
}
