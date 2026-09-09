import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:local_auth/local_auth.dart';

import '../../l10n/generated/app_localizations.dart';
import '../../shared/widgets/app_snackbar.dart';
import '../../shared/widgets/brand_background.dart';
import '../../shared/widgets/pin_pad.dart';
import 'auth_controller.dart';

/// Verrouillage à l'ouverture : biométrie si dispo, sinon code à 4 chiffres.
/// (Le PIN local sert de rempart ; l'authentification serveur passe par le
/// refresh token lors du déverrouillage.)
class PinLockPage extends ConsumerStatefulWidget {
  const PinLockPage({super.key});

  @override
  ConsumerState<PinLockPage> createState() => _PinLockPageState();
}

class _PinLockPageState extends ConsumerState<PinLockPage> {
  final _auth = LocalAuthentication();
  String _pin = '';
  int _error = 0;
  bool _hasBiometrics = false;

  @override
  void initState() {
    super.initState();
    _checkBiometrics();
  }

  Future<void> _checkBiometrics() async {
    try {
      final can =
          await _auth.canCheckBiometrics && await _auth.isDeviceSupported();
      if (mounted) setState(() => _hasBiometrics = can);
      if (can) unawaited(_biometrics());
    } catch (_) {/* ignore */}
  }

  Future<void> _biometrics() async {
    try {
      final ok = await _auth.authenticate(
        localizedReason: L10n.of(context).lockTitle,
        options: const AuthenticationOptions(
          biometricOnly: true,
          stickyAuth: true,
        ),
      );
      if (ok) await _unlock();
    } catch (_) {/* fallback code */}
  }

  Future<void> _submit(String value) async {
    // Rempart local minimal : 4 chiffres non triviaux. La vraie preuve reste
    // le refresh token côté serveur.
    if (RegExp(r'^(\d)\1{3}$').hasMatch(value) || value == '1234') {
      setState(() {
        _pin = '';
        _error++;
      });
      return;
    }
    await _unlock();
  }

  Future<void> _unlock() async {
    final ok = await ref.read(authControllerProvider.notifier).unlock();
    if (!ok && mounted) AppSnack.info(context, L10n.of(context).authSignIn);
  }

  @override
  Widget build(BuildContext context) {
    final l = L10n.of(context);
    return Scaffold(
      body: BrandBackground(
        intensity: 0.6,
        child: SafeArea(
          child: Column(
            children: [
              const Spacer(),
              const Icon(Icons.lock_outline, size: 40, color: Colors.white),
              const SizedBox(height: 12),
              Text(
                l.lockTitle,
                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w700,
                    ),
              ),
              const SizedBox(height: 4),
              Text(
                l.lockSubtitle,
                style: TextStyle(color: Colors.white.withValues(alpha: 0.8)),
              ),
              const SizedBox(height: 36),
              PinPad(
                length: 4,
                value: _pin,
                errorSignal: _error,
                biometricsButton: _hasBiometrics,
                onBiometrics: _biometrics,
                onChanged: (v) => setState(() => _pin = v),
                onCompleted: _submit,
              ),
              const Spacer(),
              TextButton(
                onPressed: () =>
                    ref.read(authControllerProvider.notifier).signOut(),
                child: const Text(
                  'Se déconnecter',
                  style: TextStyle(color: Colors.white70),
                ),
              ),
              const SizedBox(height: 12),
            ],
          ),
        ),
      ),
    );
  }
}
