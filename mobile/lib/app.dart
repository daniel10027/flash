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

/// ThemeMode réactif (lu de Prefs, modifiable via Paramètres — MOB-034).
final themeModeProvider = StateProvider<ThemeMode>((ref) {
  return ref.watch(prefsProvider).themeMode;
});

final localeProvider = StateProvider<Locale?>((ref) {
  return ref.watch(prefsProvider).locale;
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
