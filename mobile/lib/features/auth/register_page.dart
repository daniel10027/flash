import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/network/api_client.dart';
import '../../core/theme/motion.dart';
import '../../l10n/generated/app_localizations.dart';
import '../../shared/widgets/app_snackbar.dart';
import '../../shared/widgets/brand_background.dart';
import '../../shared/widgets/glass_card.dart';
import '../../shared/widgets/pin_pad.dart';
import '../../shared/widgets/primary_button.dart';
import 'auth_controller.dart';

enum _Step { phone, pin, confirm, otp, done }

class RegisterPage extends ConsumerStatefulWidget {
  const RegisterPage({super.key});

  @override
  ConsumerState<RegisterPage> createState() => _RegisterPageState();
}

class _RegisterPageState extends ConsumerState<RegisterPage> {
  final _phone = TextEditingController();
  final _country = TextEditingController(text: 'CI');
  _Step _step = _Step.phone;
  String _pin = '';
  String _pin2 = '';
  String _code = '';
  int _err = 0;
  bool _busy = false;

  @override
  void dispose() {
    _phone.dispose();
    _country.dispose();
    super.dispose();
  }

  double get _progress => switch (_step) {
        _Step.phone => 0.2,
        _Step.pin => 0.4,
        _Step.confirm => 0.6,
        _Step.otp => 0.85,
        _Step.done => 1,
      };

  Future<void> _register() async {
    setState(() => _busy = true);
    try {
      await ref.read(apiClientProvider).postJson(
        '/v1/auth/register',
        body: {
          'phone_number': _phone.text.trim(),
          'country': _country.text.trim().toUpperCase(),
          'pin': _pin,
        },
      );
      setState(() => _step = _Step.otp);
    } catch (e) {
      setState(() {
        _pin = '';
        _pin2 = '';
        _step = _Step.pin;
        _err++;
      });
      if (mounted) AppSnack.error(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _verify() async {
    setState(() => _busy = true);
    try {
      final r = await ref.read(apiClientProvider).postJson(
        '/v1/auth/verify-otp',
        body: {
          'phone_number': _phone.text.trim(),
          'country': _country.text.trim().toUpperCase(),
          'code': _code,
          'device_id': 'flutter-dev',
        },
      );
      if (!mounted) return;
      setState(() => _step = _Step.done);
      await Future<void>.delayed(const Duration(milliseconds: 900));
      await ref.read(authControllerProvider.notifier).onSession(
            accessToken: r['access_token'] as String,
            refreshToken: r['refresh_token'] as String,
            userId: r['user_id'] as String?,
          );
    } catch (e) {
      setState(() {
        _code = '';
        _err++;
      });
      if (mounted) AppSnack.error(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = L10n.of(context);
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        foregroundColor: Colors.white,
        title: Text(l.authCreateAccount),
        leading: BackButton(onPressed: () => context.pop()),
      ),
      extendBodyBehindAppBar: true,
      body: BrandBackground(
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(999),
                  child: LinearProgressIndicator(
                    value: _progress,
                    minHeight: 6,
                    backgroundColor: Colors.white24,
                    color: Colors.white,
                  ),
                ),
                const SizedBox(height: 28),
                Expanded(
                  child: AnimatedSwitcher(
                    duration: Motion.base,
                    transitionBuilder: (child, anim) => FadeTransition(
                      opacity: anim,
                      child: SlideTransition(
                        position: Tween(
                          begin: const Offset(0.06, 0),
                          end: Offset.zero,
                        ).animate(anim),
                        child: child,
                      ),
                    ),
                    child: KeyedSubtree(
                      key: ValueKey(_step),
                      child: _body(l),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _body(L10n l) {
    switch (_step) {
      case _Step.phone:
        return GlassCard(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: _phone,
                keyboardType: TextInputType.phone,
                decoration: InputDecoration(
                  labelText: l.authPhone,
                  hintText: '+225…',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _country,
                maxLength: 2,
                decoration:
                    InputDecoration(labelText: l.authCountry, counterText: ''),
              ),
              const SizedBox(height: 16),
              PrimaryButton(
                label: l.actionContinue,
                onPressed: () => setState(() => _step = _Step.pin),
              ),
            ],
          ),
        );
      case _Step.pin:
        return _PinStep(
          title: 'Choisissez un code secret',
          value: _pin,
          err: _err,
          onChanged: (v) => setState(() => _pin = v),
          onDone: (v) => setState(() {
            _pin = v;
            _step = _Step.confirm;
          }),
        );
      case _Step.confirm:
        return _PinStep(
          title: 'Confirmez votre code',
          value: _pin2,
          err: _err,
          onChanged: (v) => setState(() => _pin2 = v),
          onDone: (v) {
            if (v != _pin) {
              setState(() {
                _pin2 = '';
                _err++;
              });
              AppSnack.error(context, 'Les codes ne correspondent pas.');
            } else {
              _register();
            }
          },
        );
      case _Step.otp:
        return _PinStep(
          title: l.authOtp,
          length: 6,
          value: _code,
          err: _err,
          busy: _busy,
          onChanged: (v) => setState(() => _code = v),
          onDone: (v) {
            _code = v;
            _verify();
          },
        );
      case _Step.done:
        return const _DoneStep();
    }
  }
}

class _PinStep extends StatelessWidget {
  const _PinStep({
    required this.title,
    required this.value,
    required this.err,
    required this.onChanged,
    required this.onDone,
    this.length = 4,
    this.busy = false,
  });

  final String title;
  final String value;
  final int err;
  final int length;
  final bool busy;
  final ValueChanged<String> onChanged;
  final ValueChanged<String> onDone;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          title,
          style: Theme.of(context)
              .textTheme
              .titleLarge
              ?.copyWith(color: Colors.white, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 28),
        PinPad(
          length: length,
          value: value,
          errorSignal: err,
          onChanged: onChanged,
          onCompleted: onDone,
        ),
        if (busy) ...[
          const SizedBox(height: 16),
          const CircularProgressIndicator(color: Colors.white),
        ],
      ],
    );
  }
}

class _DoneStep extends StatelessWidget {
  const _DoneStep();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.check_circle, color: Colors.white, size: 88)
              .animate()
              .scale(
                begin: const Offset(0.4, 0.4),
                curve: Curves.elasticOut,
                duration: 700.ms,
              ),
          const SizedBox(height: 16),
          const Text(
            'Votre compte est prêt.',
            style: TextStyle(
              color: Colors.white,
              fontSize: 20,
              fontWeight: FontWeight.w700,
            ),
          ).animate().fadeIn(delay: 200.ms),
        ],
      ),
    );
  }
}
