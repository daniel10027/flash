import 'package:flash_app/bootstrap.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// MOB-T3 — parcours de bout en bout. À lancer sur un appareil / émulateur :
///   flutter test integration_test/app_test.dart
///
/// Le scénario complet (onboarding → transfert → retrait → historique) suppose
/// une API de test joignable via `--dart-define=API_BASE_URL=…`. Ici on vérifie
/// le démarrage à froid et l'arrivée sur l'onboarding.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('démarrage à froid → onboarding', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await bootstrap();
    await tester.pumpAndSettle(const Duration(seconds: 2));

    expect(find.textContaining('éclair'), findsWidgets);
    expect(find.text('Passer'), findsOneWidget);
  });
}
