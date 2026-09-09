import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/auth_controller.dart';
import '../../features/auth/pin_lock_page.dart';
import '../../features/auth/register_page.dart';
import '../../features/auth/welcome_page.dart';
import '../../features/card/card_page.dart';
import '../../features/cash/deposit_page.dart';
import '../../features/cash/withdraw_page.dart';
import '../../features/history/history_page.dart';
import '../../features/home/home_page.dart';
import '../../features/home/home_shell.dart';
import '../../features/notifications/notifications_page.dart';
import '../../features/onboarding/onboarding_page.dart';
import '../../features/pay/scan_page.dart';
import '../../features/profile/phones_page.dart';
import '../../features/profile/profile_page.dart';
import '../../features/receive/receive_page.dart';
import '../../features/savings/savings_page.dart';
import '../../features/settings/about_page.dart';
import '../../features/settings/security_page.dart';
import '../../features/settings/settings_page.dart';
import '../../features/transfer/send_page.dart';
import '../../features/vault/vault_page.dart';
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

      const publicRoutes = {'/onboarding', '/welcome', '/lock', '/register'};
      final atGate = publicRoutes.contains(loc);

      return switch (auth) {
        AuthStatus.signedOut =>
          atGate && loc != '/onboarding' ? null : '/welcome',
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
      GoRoute(path: '/register', builder: (_, __) => const RegisterPage()),
      GoRoute(path: '/lock', builder: (_, __) => const PinLockPage()),
      GoRoute(path: '/send', builder: (_, __) => const SendPage()),
      GoRoute(path: '/receive', builder: (_, __) => const ReceivePage()),
      GoRoute(path: '/withdraw', builder: (_, __) => const WithdrawPage()),
      GoRoute(path: '/deposit', builder: (_, __) => const DepositPage()),
      GoRoute(path: '/vault', builder: (_, __) => const VaultPage()),
      GoRoute(path: '/savings', builder: (_, __) => const SavingsPage()),
      GoRoute(
        path: '/profile/security',
        builder: (_, __) => const SecurityPage(),
      ),
      GoRoute(
        path: '/profile/settings',
        builder: (_, __) => const SettingsPage(),
      ),
      GoRoute(path: '/profile/about', builder: (_, __) => const AboutPage()),
      GoRoute(path: '/profile/phones', builder: (_, __) => const PhonesPage()),
      GoRoute(
        path: '/profile/notifications',
        builder: (_, __) => const NotificationsPage(),
      ),
      ShellRoute(
        builder: (_, __, child) => HomeShell(child: child),
        routes: [
          GoRoute(path: '/', builder: (_, __) => const HomePage()),
          GoRoute(path: '/history', builder: (_, __) => const HistoryPage()),
          GoRoute(path: '/scan', builder: (_, __) => const ScanPage()),
          GoRoute(path: '/card', builder: (_, __) => const CardPage()),
          GoRoute(path: '/profile', builder: (_, __) => const ProfilePage()),
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
