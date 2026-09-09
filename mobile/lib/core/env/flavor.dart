/// Flavors dev / staging / prod. Sélectionnés par `--dart-define`.
///
///   flutter run --dart-define=FLAVOR=dev \
///     --dart-define=API_BASE_URL=http://10.0.2.2:8000
enum Flavor { dev, staging, prod }

abstract final class Env {
  static const _rawFlavor =
      String.fromEnvironment('FLAVOR', defaultValue: 'dev');

  static Flavor get flavor => switch (_rawFlavor) {
        'prod' => Flavor.prod,
        'staging' => Flavor.staging,
        _ => Flavor.dev,
      };

  /// Base de l'API. En dev Android l'émulateur voit l'hôte via 10.0.2.2.
  static const apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  static bool get isProd => flavor == Flavor.prod;
  static bool get isDev => flavor == Flavor.dev;

  static String get label => switch (flavor) {
        Flavor.prod => 'Flash',
        Flavor.staging => 'Flash · staging',
        Flavor.dev => 'Flash · dev',
      };
}
