# Flash — application mobile (Flutter)

Client mobile de Flash : mêmes parcours que le web + scan QR natif, biométrie,
notifications push, mode hors-ligne lecture.

## Démarrer

```sh
flutter pub get
flutter gen-l10n

# émulateur Android — l'API locale est vue via 10.0.2.2
flutter run --flavor dev -t lib/main_dev.dart \
  --dart-define=FLAVOR=dev \
  --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

Flavors : `dev` / `staging` / `prod` (entrypoints `lib/main_<flavor>.dart`,
suffixe d'`applicationId`, libellé distinct). L'URL de l'API vient de
`--dart-define=API_BASE_URL`.

## Architecture

```
lib/
  core/        env, network (dio + interceptors), storage (secure + prefs),
               theme (tokens ⟵ design/tokens.json), router (go_router), push
  shared/      widgets (design system), format, tutorial (coach marks), security
  features/    onboarding, auth, home, transfer, pay, receive, history, cash,
               vault, savings, card, request, operator, profile, settings,
               notifications, agent, wallet
```

État : Riverpod (`StateNotifier` / `FutureProvider` / `StreamProvider`, sans
codegen). i18n : `gen-l10n` (FR par défaut, EN).

## Notifications push (MOB-009)

`firebase_messaging` est intégré mais **tolérant** : sans configuration Firebase,
le push reste inactif et l'app fonctionne. Pour l'activer :

```sh
dart pub global activate flutterfire_cli
flutterfire configure           # génère google-services.json / GoogleService-Info.plist
```

Puis appliquer le plugin Gradle `com.google.gms.google-services` dans
`android/app/build.gradle.kts`. Le flux temps réel in-app (SSE) fonctionne sans
Firebase.

## Build & signature

| | Commande |
|---|---|
| APK debug | `flutter build apk --debug --flavor dev -t lib/main_dev.dart` |
| AAB release | `flutter build appbundle --release --flavor prod -t lib/main_prod.dart` |
| IPA release | `flutter build ipa --release --flavor prod -t lib/main_prod.dart` |

**Android** : copier `android/key.properties.example` → `android/key.properties`
(git-ignoré) ou définir `FLASH_KEYSTORE_PATH/PASSWORD`, `FLASH_KEY_ALIAS/PASSWORD`
en CI. Minification + ProGuard activés en release.

**iOS** : signature via `fastlane match` (certs/profils chiffrés). Capacités
déclarées dans `ios/Runner/Info.plist` (caméra, Face ID, push).

**fastlane** (`fastlane/Fastfile`) : lanes `beta` (Firebase App Distribution /
TestFlight) et `release` (Play Console / App Store) par plateforme.

## Tests

```sh
flutter test                       # widget + provider + golden
flutter test --update-goldens      # régénère test/golden/goldens/*.png
flutter test integration_test      # sur un appareil / émulateur (MOB-T3)
```

CI : `.github/workflows/mobile-ci.yml` (`dart format`, `flutter analyze`,
`flutter test --coverage`, build APK debug flavor `dev`).
