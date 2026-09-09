import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../../core/theme/tokens.dart';
import '../../shared/widgets/app_snackbar.dart';
import '../../shared/widgets/common.dart';

final _cardsProvider = FutureProvider.autoDispose((ref) async {
  final r = await ref.watch(apiClientProvider).getJson('/v1/cards');
  return ((r['cards'] as List?) ?? const [])
      .cast<Map<String, dynamic>>()
      .toList();
});

/// MOB-029 — carte virtuelle : visuel, révéler PAN/CVV (30 s), geler/dégeler.
class CardPage extends ConsumerWidget {
  const CardPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cards = ref.watch(_cardsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Carte')),
      body: cards.when(
        loading: () => const Padding(
          padding: EdgeInsets.all(20),
          child: Skeleton(height: 200, radius: 18),
        ),
        error: (_, __) =>
            const EmptyState(icon: Icons.wifi_off, title: 'Indisponible'),
        data: (list) {
          if (list.isEmpty) {
            return EmptyState(
              icon: Icons.credit_card,
              title: 'Aucune carte',
              message: 'Émettez une carte virtuelle pour payer en ligne.',
              action: FilledButton(
                onPressed: () async {
                  try {
                    await ref
                        .read(apiClientProvider)
                        .postJson('/v1/cards', body: {'network': 'VISA'});
                    ref.invalidate(_cardsProvider);
                  } catch (e) {
                    if (context.mounted) AppSnack.error(context, e);
                  }
                },
                child: const Text('Émettre une carte'),
              ),
            );
          }
          return ListView(
            padding: const EdgeInsets.all(20),
            children: [
              for (final c in list) _CardTile(card: c),
            ],
          );
        },
      ),
    );
  }
}

class _CardTile extends ConsumerStatefulWidget {
  const _CardTile({required this.card});
  final Map<String, dynamic> card;

  @override
  ConsumerState<_CardTile> createState() => _CardTileState();
}

class _CardTileState extends ConsumerState<_CardTile> {
  String? _pan;
  String? _cvv;
  Timer? _hideTimer;
  int _secondsLeft = 0;

  bool get _frozen => widget.card['status'] == 'FROZEN';

  @override
  void dispose() {
    _hideTimer?.cancel();
    super.dispose();
  }

  Future<void> _reveal() async {
    try {
      final r = await ref.read(apiClientProvider).postJson(
            '/v1/cards/${widget.card['id']}/sensitive',
          );
      setState(() {
        _pan = r['pan'] as String?;
        _cvv = r['cvv'] as String?;
        _secondsLeft = 30;
      });
      _hideTimer?.cancel();
      _hideTimer = Timer.periodic(const Duration(seconds: 1), (t) {
        setState(() => _secondsLeft--);
        if (_secondsLeft <= 0) {
          t.cancel();
          setState(() {
            _pan = null;
            _cvv = null;
          });
        }
      });
    } catch (e) {
      if (mounted) AppSnack.error(context, e);
    }
  }

  Future<void> _toggleFreeze() async {
    try {
      await ref.read(apiClientProvider).postJson(
            '/v1/cards/${widget.card['id']}/${_frozen ? 'unfreeze' : 'freeze'}',
          );
      ref.invalidate(_cardsProvider);
    } catch (e) {
      if (mounted) AppSnack.error(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final network = widget.card['network'] as String? ?? 'VISA';
    final last4 = widget.card['pan_last4'] as String? ?? '••••';
    return Column(
      children: [
        AspectRatio(
          aspectRatio: 1.586,
          child: Container(
            padding: const EdgeInsets.all(22),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(18),
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: _frozen
                    ? [FlashColors.neutral500, FlashColors.neutral700]
                    : [FlashColors.brand500, FlashColors.brand800],
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Icon(Icons.bolt, color: Colors.white),
                    Text(
                      network,
                      style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 2,
                      ),
                    ),
                  ],
                ),
                const Spacer(),
                GestureDetector(
                  onLongPress: _pan == null
                      ? null
                      : () => Clipboard.setData(ClipboardData(text: _pan!)),
                  child: Text(
                    _pan ?? '••••  ••••  ••••  $last4',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      letterSpacing: 2,
                      fontFeatures: [FontFeature.tabularFigures()],
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Text(
                      _cvv == null ? 'CVV •••' : 'CVV $_cvv',
                      style: const TextStyle(color: Colors.white70),
                    ),
                    const Spacer(),
                    if (_secondsLeft > 0)
                      Text(
                        'masqué dans ${_secondsLeft}s',
                        style: const TextStyle(
                          color: Colors.white70,
                          fontSize: 12,
                        ),
                      ),
                  ],
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: _frozen ? null : _reveal,
                icon: const Icon(Icons.visibility_outlined),
                label: const Text('Révéler'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: _toggleFreeze,
                icon: Icon(_frozen ? Icons.lock_open : Icons.ac_unit),
                label: Text(_frozen ? 'Dégeler' : 'Geler'),
              ),
            ),
          ],
        ),
      ],
    );
  }
}
