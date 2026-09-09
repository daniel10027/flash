import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/env/flavor.dart';
import 'core/router/app_router.dart';
import 'core/storage/prefs.dart';
import 'core/theme/app_theme.dart';
import 'features/auth/auth_controller.dart';
import 'l10n/generated/app_localizations.dart';
import 'shared/security/app_lock_guard.dart';

/// ThemeMode réactif (Paramètres — MOB-034), persistant.
class ThemeModeController extends StateNotifier<ThemeMode> {
  ThemeModeController(this._prefs) : super(_prefs.themeMode);
  final Prefs _prefs;

  void set(ThemeMode m) {
    state = m;
    _prefs.setThemeMode(m);
  }
}

final themeModeProvider =
    StateNotifierProvider<ThemeModeController, ThemeMode>((ref) {
  return ThemeModeController(ref.watch(prefsProvider));
});

/// Langue (null = système), persistante.
class LocaleController extends StateNotifier<Locale?> {
  LocaleController(this._prefs) : super(_prefs.locale);
  final Prefs _prefs;

  void set(Locale? l) {
    state = l;
    _prefs.setLocale(l);
  }
}

final localeProvider = StateNotifierProvider<LocaleController, Locale?>((ref) {
  return LocaleController(ref.watch(prefsProvider));
});

/// Masquer les soldes (œil dans l'app bar / Paramètres). Persiste à chaque bascule.
class HideBalances extends StateNotifier<bool> {
  HideBalances(this._prefs) : super(_prefs.hideBalances);
  final Prefs _prefs;

  void toggle() {
    state = !state;
    _prefs.setHideBalances(state);
  }
}

final hideBalancesProvider = StateNotifierProvider<HideBalances, bool>((ref) {
  return HideBalances(ref.watch(prefsProvider));
});

class FlashApp extends ConsumerStatefulWidget {
  const FlashApp({super.key});

  @override
  ConsumerState<FlashApp> createState() => _FlashAppState();
}

class _FlashAppState extends ConsumerState<FlashApp> {
  @override
  void initState() {
    super.initState();
    // Lit le stockage sécurisé -> passe de `unknown` à `locked` / `signedOut`.
    Future.microtask(
      () => ref.read(authControllerProvider.notifier).bootstrap(),
    );
  }

  @override
  Widget build(BuildContext context) {
    final router = ref.watch(routerProvider);
    return MaterialApp.router(
      title: Env.label,
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: ref.watch(themeModeProvider),
      locale: ref.watch(localeProvider),
      localizationsDelegates: const [
        L10n.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: L10n.supportedLocales,
      routerConfig: router,
      builder: (context, child) =>
          AppLockGuard(child: child ?? const SizedBox.shrink()),
    );
  }
}
