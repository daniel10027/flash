import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/network/api_client.dart';
import '../../l10n/generated/app_localizations.dart';
import '../../shared/widgets/app_snackbar.dart';
import '../../shared/widgets/brand_background.dart';
import '../../shared/widgets/glass_card.dart';
import '../../shared/widgets/pin_pad.dart';
import '../../shared/widgets/primary_button.dart';
import 'auth_controller.dart';

/// Écran d'accueil non authentifié : marque + connexion rapide.
/// (L'inscription complète = MOB-015 ; ici, connexion numéro + code.)
class WelcomePage extends ConsumerStatefulWidget {
  const WelcomePage({super.key});

  @override
  ConsumerState<WelcomePage> createState() => _WelcomePageState();
}

class _WelcomePageState extends ConsumerState<WelcomePage> {
  final _phone = TextEditingController();
  final _country = TextEditingController(text: 'CI');
  String _pin = '';
  int _pinError = 0;
  bool _busy = false;

  @override
  void dispose() {
    _phone.dispose();
    _country.dispose();
    super.dispose();
  }

  Future<void> _signIn() async {
    setState(() => _busy = true);
    try {
      final api = ref.read(apiClientProvider);
      final r = await api.postJson(
        '/v1/auth/login',
        body: {
          'phone_number': _phone.text.trim(),
          'country': _country.text.trim().toUpperCase(),
          'pin': _pin,
          'device_id': 'flutter-dev',
        },
      );
      final access = r['access_token'] as String?;
      if (access == null) {
        if (mounted) AppSnack.info(context, 'Vérification requise (OTP).');
        return;
      }
      await ref.read(authControllerProvider.notifier).onSession(
            accessToken: access,
            refreshToken: r['refresh_token'] as String,
            userId: r['user_id'] as String?,
          );
    } catch (e) {
      setState(() {
        _pin = '';
        _pinError++;
      });
      if (mounted) AppSnack.error(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _openLogin() {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => Padding(
        padding: EdgeInsets.only(
          left: 20,
          right: 20,
          bottom: MediaQuery.viewInsetsOf(context).bottom + 20,
          top: 8,
        ),
        child: StatefulBuilder(
          builder: (context, setSheet) => Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: _phone,
                keyboardType: TextInputType.phone,
                decoration: InputDecoration(
                  labelText: L10n.of(context).authPhone,
                  hintText: '+225…',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _country,
                maxLength: 2,
                decoration: InputDecoration(
                  labelText: L10n.of(context).authCountry,
                  counterText: '',
                ),
              ),
              const SizedBox(height: 20),
              PinPad(
                length: 4,
                value: _pin,
                errorSignal: _pinError,
                onChanged: (v) => setSheet(() => _pin = v),
                onCompleted: (_) => _signIn(),
              ),
              const SizedBox(height: 12),
              PrimaryButton(
                label: L10n.of(context).authSignIn,
                loading: _busy,
                onPressed:
                    _pin.length == 4 && _phone.text.isNotEmpty ? _signIn : null,
              ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l = L10n.of(context);
    return Scaffold(
      body: BrandBackground(
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              children: [
                const Spacer(),
                const Icon(Icons.bolt, size: 64, color: Colors.white)
                    .animate()
                    .fadeIn()
                    .scale(begin: const Offset(0.7, 0.7)),
                const SizedBox(height: 12),
                Text(
                  l.appName,
                  style: Theme.of(context).textTheme.displaySmall?.copyWith(
                        color: Colors.white,
                        fontWeight: FontWeight.w800,
                        letterSpacing: -1,
                      ),
                ),
                const SizedBox(height: 6),
                Text(
                  l.onboardBody1,
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.white.withValues(alpha: 0.85)),
                ),
                const Spacer(),
                GlassCard(
                  child: Column(
                    children: [
                      PrimaryButton(
                        label: l.authSignIn,
                        icon: Icons.login,
                        onPressed: _openLogin,
                      ),
                      const SizedBox(height: 10),
                      TextButton(
                        onPressed: () => context.push('/register'),
                        child: Text(l.authCreateAccount),
                      ),
                    ],
                  ),
                ).animate().fadeIn(delay: 200.ms).moveY(begin: 24, end: 0),
                const SizedBox(height: 12),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
