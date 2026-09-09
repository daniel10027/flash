import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app.dart';
import '../../core/storage/prefs.dart';
import '../../core/theme/tokens.dart';
import '../../l10n/generated/app_localizations.dart';
import '../../shared/format/money_format.dart';
import '../../shared/tutorial/coach_marks.dart';
import '../../shared/widgets/common.dart';
import '../../shared/widgets/money_text.dart';
import '../../shared/widgets/pressable.dart';
import '../wallet/wallet_models.dart';
import '../wallet/wallet_providers.dart';

class HomePage extends ConsumerStatefulWidget {
  const HomePage({super.key});

  @override
  ConsumerState<HomePage> createState() => _HomePageState();
}

class _HomePageState extends ConsumerState<HomePage> {
  final _sendKey = GlobalKey();
  final _payKey = GlobalKey();
  final _actionsKey = GlobalKey();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _maybeTutorial());
  }

  Future<void> _maybeTutorial() async {
    final prefs = ref.read(prefsProvider);
    if (prefs.homeTutorialSeen || !mounted) return;
    await showCoachMarks(
      context,
      steps: [
        CoachStep(
          key: _actionsKey,
          title: 'Vos raccourcis',
          body:
              'Envoyez, payez un marchand, retirez ou rechargez — tout est à un geste.',
        ),
        CoachStep(
          key: _payKey,
          title: 'Payer en scannant',
          body: 'Scannez le QR d\'un commerçant pour régler sans frais.',
        ),
      ],
      onDone: () => prefs.setHomeTutorialSeen(true),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l = L10n.of(context);
    final wallet = ref.watch(primaryWalletProvider);
    final kyc = ref.watch(kycStatusProvider);
    final recent = ref.watch(recentStatementProvider);
    final hidden = ref.watch(hideBalancesProvider);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async => refreshDashboard(ref),
        child: CustomScrollView(
          slivers: [
            SliverAppBar(
              floating: true,
              title: Text(l.appName),
              actions: [
                IconButton(
                  onPressed: () =>
                      ref.read(hideBalancesProvider.notifier).toggle(),
                  icon: Icon(
                    hidden
                        ? Icons.visibility_off_outlined
                        : Icons.visibility_outlined,
                  ),
                ),
                IconButton(
                  onPressed: () => context.go('/profile'),
                  icon: const Icon(Icons.notifications_none),
                ),
              ],
            ),
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
              sliver: SliverList.list(
                children: [
                  _BalanceCard(async: wallet, hidden: hidden)
                      .animate()
                      .fadeIn(duration: 350.ms)
                      .moveY(begin: 12, end: 0),
                  const SizedBox(height: 20),
                  _QuickActions(
                    rootKey: _actionsKey,
                    sendKey: _sendKey,
                    payKey: _payKey,
                  ),
                  const SizedBox(height: 20),
                  kyc.maybeWhen(
                    data: (k) => k.tier == 0
                        ? const _KycBanner().animate().fadeIn(delay: 150.ms)
                        : const SizedBox.shrink(),
                    orElse: () => const SizedBox.shrink(),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    l.navHistory,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 4),
                  recent.when(
                    loading: () => Column(
                      children: List.generate(
                        4,
                        (_) => const Padding(
                          padding: EdgeInsets.symmetric(vertical: 10),
                          child: Skeleton(height: 44),
                        ),
                      ),
                    ),
                    error: (_, __) => EmptyState(
                      icon: Icons.wifi_off,
                      title: l.errorGeneric,
                      action: TextButton(
                        onPressed: () => refreshDashboard(ref),
                        child: Text(l.actionRetry),
                      ),
                    ),
                    data: (lines) => lines.isEmpty
                        ? const EmptyState(
                            icon: Icons.history,
                            title: 'Rien pour l\'instant',
                            message: 'Vos opérations apparaîtront ici.',
                          )
                        : Column(
                            children: [
                              for (final op in lines)
                                _OpRow(op: op, hidden: hidden),
                            ],
                          ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BalanceCard extends StatelessWidget {
  const _BalanceCard({required this.async, required this.hidden});
  final AsyncValue<Wallet?> async;
  final bool hidden;

  @override
  Widget build(BuildContext context) {
    final l = L10n.of(context);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(FlashRadii.xl),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [FlashColors.brand500, FlashColors.brand700],
        ),
        boxShadow: [
          BoxShadow(
            color: FlashColors.brand500.withValues(alpha: 0.35),
            blurRadius: 30,
            offset: const Offset(0, 12),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            l.balanceTitle,
            style: const TextStyle(color: Colors.white70, fontSize: 13),
          ),
          const SizedBox(height: 8),
          async.when(
            loading: () => const Skeleton(width: 180, height: 34),
            error: (_, __) => const Text(
              '—',
              style: TextStyle(color: Colors.white, fontSize: 30),
            ),
            data: (w) => w == null
                ? const Text(
                    '—',
                    style: TextStyle(color: Colors.white, fontSize: 30),
                  )
                : _AnimatedAmount(
                    minor: w.availableMinor,
                    currency: w.currency,
                    hidden: hidden,
                  ),
          ),
          if (async.valueOrNull != null &&
              async.value!.reservedMinor > 0 &&
              !hidden) ...[
            const SizedBox(height: 6),
            Text(
              'dont ${formatMoney(async.value!.reservedMinor, async.value!.currency)} réservés',
              style: const TextStyle(color: Colors.white60, fontSize: 12),
            ),
          ],
        ],
      ),
    );
  }
}

class _AnimatedAmount extends StatelessWidget {
  const _AnimatedAmount({
    required this.minor,
    required this.currency,
    required this.hidden,
  });
  final int minor;
  final String currency;
  final bool hidden;

  @override
  Widget build(BuildContext context) {
    final style = Theme.of(context).textTheme.displaySmall?.copyWith(
          color: Colors.white,
          fontWeight: FontWeight.w800,
        );
    if (hidden) return Text('••••••', style: style);
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: minor.toDouble()),
      duration: const Duration(milliseconds: 700),
      curve: Curves.easeOutCubic,
      builder: (context, v, _) => MoneyText(v.round(), currency, style: style),
    );
  }
}

class _QuickActions extends StatelessWidget {
  const _QuickActions({
    required this.rootKey,
    required this.sendKey,
    required this.payKey,
  });
  final Key rootKey;
  final GlobalKey sendKey;
  final GlobalKey payKey;

  @override
  Widget build(BuildContext context) {
    final l = L10n.of(context);
    return Row(
      key: rootKey,
      children: [
        _Action(
          key: sendKey,
          icon: Icons.north_east,
          label: l.quickSend,
          onTap: () => context.push('/send'),
        ),
        _Action(
          key: payKey,
          icon: Icons.qr_code_scanner,
          label: l.quickPay,
          onTap: () => context.go('/scan'),
        ),
        _Action(
          icon: Icons.south_west,
          label: l.quickWithdraw,
          onTap: () => context.go('/scan'),
        ),
        _Action(
          icon: Icons.add,
          label: l.quickTopUp,
          onTap: () => context.push('/receive'),
        ),
      ],
    );
  }
}

class _Action extends StatelessWidget {
  const _Action({
    required this.icon,
    required this.label,
    required this.onTap,
    super.key,
  });
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Expanded(
      child: Pressable(
        onTap: onTap,
        child: Column(
          children: [
            Container(
              width: 54,
              height: 54,
              decoration: BoxDecoration(
                color: scheme.primary.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(FlashRadii.lg),
              ),
              child: Icon(icon, color: scheme.primary),
            ),
            const SizedBox(height: 6),
            Text(label, style: Theme.of(context).textTheme.labelMedium),
          ],
        ),
      ),
    );
  }
}

class _KycBanner extends StatelessWidget {
  const _KycBanner();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: FlashColors.warningBg,
        borderRadius: BorderRadius.circular(FlashRadii.md),
      ),
      child: Row(
        children: [
          const Icon(Icons.verified_user_outlined,
              color: FlashColors.warningFg),
          const SizedBox(width: 10),
          const Expanded(
            child: Text(
              'Vérifiez votre identité pour débloquer des plafonds plus élevés.',
              style: TextStyle(color: FlashColors.warningFg, fontSize: 13),
            ),
          ),
          TextButton(
            onPressed: () => context.go('/profile'),
            child: const Text('Vérifier'),
          ),
        ],
      ),
    );
  }
}

class _OpRow extends StatelessWidget {
  const _OpRow({required this.op, required this.hidden});
  final StatementLine op;
  final bool hidden;

  @override
  Widget build(BuildContext context) {
    final incoming = op.direction == 'in';
    return ListRow(
      leading: CircleAvatar(
        backgroundColor: Theme.of(context).colorScheme.surfaceContainerHighest,
        child: Icon(
          incoming ? Icons.south_west : Icons.north_east,
          size: 18,
          color: incoming
              ? Theme.of(context).colorScheme.secondary
              : Theme.of(context).colorScheme.onSurface,
        ),
      ),
      title: op.counterparty ?? op.kind,
      subtitle: op.reference,
      trailing: MoneyText(
        op.signedMinor,
        op.currency,
        withSign: true,
        hidden: hidden,
        style: Theme.of(context).textTheme.titleSmall,
      ),
    );
  }
}
