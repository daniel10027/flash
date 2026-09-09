import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/tokens.dart';
import '../../features/auth/auth_controller.dart';

/// MOB-011 — confidentialité :
///  * masque le contenu dans l'aperçu multitâche (overlay opaque quand l'app
///    n'est pas au premier plan) ;
///  * re-verrouille après une inactivité en arrière-plan.
class AppLockGuard extends ConsumerStatefulWidget {
  const AppLockGuard({required this.child, super.key});
  final Widget child;

  static const _lockAfter = Duration(minutes: 2);

  @override
  ConsumerState<AppLockGuard> createState() => _AppLockGuardState();
}

class _AppLockGuardState extends ConsumerState<AppLockGuard>
    with WidgetsBindingObserver {
  bool _covered = false;
  DateTime? _leftAt;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        final away = _leftAt;
        _leftAt = null;
        if (away != null &&
            DateTime.now().difference(away) >= AppLockGuard._lockAfter &&
            ref.read(authControllerProvider).status == AuthStatus.signedIn) {
          ref.read(authControllerProvider.notifier).lock();
        }
        setState(() => _covered = false);
      case AppLifecycleState.inactive:
      case AppLifecycleState.hidden:
      case AppLifecycleState.paused:
        _leftAt ??= DateTime.now();
        setState(() => _covered = true);
      case AppLifecycleState.detached:
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        widget.child,
        if (_covered)
          const ColoredBox(
            color: FlashColors.brand500,
            child: Center(
              child: Icon(Icons.bolt, color: Colors.white, size: 64),
            ),
          ),
      ],
    );
  }
}
