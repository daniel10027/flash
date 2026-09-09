import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:liquid_swipe/liquid_swipe.dart';

import '../../core/storage/prefs.dart';
import '../../core/theme/motion.dart';
import '../../l10n/generated/app_localizations.dart';
import '../../shared/widgets/primary_button.dart';
import 'onboarding_slides.dart';

/// Onboarding « liquid swipe » : 3 pages plein écran, transition fluide en
/// goutte d'eau, illustrations animées, textes en cascade.
class OnboardingPage extends ConsumerStatefulWidget {
  const OnboardingPage({super.key});

  @override
  ConsumerState<OnboardingPage> createState() => _OnboardingPageState();
}

class _OnboardingPageState extends ConsumerState<OnboardingPage> {
  final _controller = LiquidController();
  int _page = 0;

  Future<void> _finish() async {
    await ref.read(prefsProvider).setOnboarded(true);
    if (mounted) context.go('/welcome');
  }

  @override
  Widget build(BuildContext context) {
    final l = L10n.of(context);
    final last = _page == onboardSlides.length - 1;

    return Scaffold(
      body: Stack(
        children: [
          LiquidSwipe(
            liquidController: _controller,
            slideIconWidget: const Icon(Icons.chevron_right, color: Colors.white),
            positionSlideIcon: 0.7,
            onPageChangeCallback: (i) => setState(() => _page = i),
            pages: [
              for (var i = 0; i < onboardSlides.length; i++)
                _Slide(
                  slide: onboardSlides[i],
                  title: switch (i) {
                    0 => l.onboardTitle1,
                    1 => l.onboardTitle2,
                    _ => l.onboardTitle3,
                  },
                  body: switch (i) {
                    0 => l.onboardBody1,
                    1 => l.onboardBody2,
                    _ => l.onboardBody3,
                  },
                ),
            ],
          ),

          // Bouton « Passer »
          Positioned(
            top: MediaQuery.paddingOf(context).top + 8,
            right: 12,
            child: AnimatedOpacity(
              opacity: last ? 0 : 1,
              duration: Motion.base,
              child: TextButton(
                onPressed: last ? null : _finish,
                child: Text(
                  l.onboardSkip,
                  style: const TextStyle(color: Colors.white),
                ),
              ),
            ),
          ),

          // Indicateurs + CTA
          Positioned(
            left: 24,
            right: 24,
            bottom: MediaQuery.paddingOf(context).bottom + 24,
            child: Column(
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    for (var i = 0; i < onboardSlides.length; i++)
                      AnimatedContainer(
                        duration: Motion.base,
                        curve: Motion.standard,
                        margin: const EdgeInsets.symmetric(horizontal: 4),
                        width: i == _page ? 22 : 8,
                        height: 8,
                        decoration: BoxDecoration(
                          color: Colors.white
                              .withValues(alpha: i == _page ? 1 : 0.4),
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 20),
                AnimatedSwitcher(
                  duration: Motion.base,
                  child: last
                      ? _WhiteButton(
                          key: const ValueKey('start'),
                          label: l.onboardStart,
                          onPressed: _finish,
                        )
                      : _WhiteButton(
                          key: const ValueKey('next'),
                          label: l.onboardNext,
                          onPressed: () =>
                              _controller.animateToPage(page: _page + 1),
                        ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Slide extends StatelessWidget {
  const _Slide({required this.slide, required this.title, required this.body});
  final OnboardSlide slide;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [slide.color, slide.color.withValues(alpha: 0.82)],
        ),
      ),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(32, 40, 32, 160),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(child: SparkIllustration(icon: slide.icon))
                  .animate()
                  .fadeIn(duration: 500.ms)
                  .scale(begin: const Offset(0.85, 0.85), curve: Curves.easeOut),
              const SizedBox(height: 48),
              Text(
                title,
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w800,
                    ),
              ).animate().fadeIn(delay: 120.ms, duration: 400.ms).moveY(
                    begin: 16,
                    end: 0,
                    curve: Curves.easeOut,
                  ),
              const SizedBox(height: 12),
              Text(
                body,
                style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                      color: Colors.white.withValues(alpha: 0.9),
                      height: 1.5,
                    ),
              ).animate().fadeIn(delay: 240.ms, duration: 400.ms).moveY(
                    begin: 16,
                    end: 0,
                    curve: Curves.easeOut,
                  ),
            ],
          ),
        ),
      ),
    );
  }
}

class _WhiteButton extends StatelessWidget {
  const _WhiteButton({required this.label, required this.onPressed, super.key});
  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: Theme.of(context).copyWith(
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            backgroundColor: Colors.white,
            foregroundColor: Theme.of(context).colorScheme.primary,
            minimumSize: const Size.fromHeight(54),
          ),
        ),
      ),
      child: PrimaryButton(label: label, onPressed: onPressed),
    );
  }
}
