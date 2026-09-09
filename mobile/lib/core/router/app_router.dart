import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/auth_controller.dart';
import '../../features/auth/pin_lock_page.dart';
import '../../features/auth/welcome_page.dart';
import '../../features/home/home_shell.dart';
import '../../features/home/placeholder_page.dart';
import '../../features/onboarding/onboarding_page.dart';
import '../../l10n/generated/app_localizations.dart';
import '../storage/prefs.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final notifier = _AuthListenable(ref);

  return GoRouter(
    initialLocation: '/',
    refreshListenable: notifier,
    redirect: (context, state) {
      final onboarded = ref.read(prefsProvider).onboarded;
      final auth = ref.read(authControllerProvider).status;
      final loc = state.matchedLocation;

      if (!onboarded) {
        return loc == '/onboarding' ? null : '/onboarding';
      }
      if (auth == AuthStatus.unknown) return null;

      final atGate = loc == '/onboarding' || loc == '/welcome' || loc == '/lock';

      return switch (auth) {
        AuthStatus.signedOut => atGate && loc != '/onboarding' ? null : '/welcome',
        AuthStatus.locked => loc == '/lock' ? null : '/lock',
        AuthStatus.signedIn => atGate ? '/' : null,
        AuthStatus.unknown => null,
      };
    },
    routes: [
      GoRoute(
        path: '/onboarding',
        builder: (_, __) => const OnboardingPage(),
      ),
      GoRoute(path: '/welcome', builder: (_, __) => const WelcomePage()),
      GoRoute(path: '/lock', builder: (_, __) => const PinLockPage()),
      ShellRoute(
        builder: (_, __, child) => HomeShell(child: child),
        routes: [
          GoRoute(path: '/', builder: (_, __) => const _Tab('navHome')),
          GoRoute(path: '/history', builder: (_, __) => const _Tab('navHistory')),
          GoRoute(path: '/scan', builder: (_, __) => const _Tab('navScan')),
          GoRoute(path: '/card', builder: (_, __) => const _Tab('navCard')),
          GoRoute(path: '/profile', builder: (_, __) => const _Tab('navProfile')),
        ],
      ),
    ],
  );
});

/// Passerelle Riverpod → go_router : notifie à chaque changement d'auth.
class _AuthListenable extends ChangeNotifier {
  _AuthListenable(Ref ref) {
    ref.listen(authControllerProvider, (_, __) => notifyListeners());
  }
}

class _Tab extends StatelessWidget {
  const _Tab(this.key_);
  final String key_;

  @override
  Widget build(BuildContext context) {
    final l = L10n.of(context);
    final title = switch (key_) {
      'navHistory' => l.navHistory,
      'navScan' => l.navScan,
      'navCard' => l.navCard,
      'navProfile' => l.navProfile,
      _ => l.navHome,
    };
    return PlaceholderPage(title: title);
  }
}
