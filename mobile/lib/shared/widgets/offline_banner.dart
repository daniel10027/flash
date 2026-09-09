import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';

import '../../core/theme/motion.dart';
import '../../core/theme/tokens.dart';
import '../../l10n/generated/app_localizations.dart';

/// Bandeau discret quand l'appareil perd le réseau (MOB-008).
class OfflineBanner extends StatefulWidget {
  const OfflineBanner({super.key});

  @override
  State<OfflineBanner> createState() => _OfflineBannerState();
}

class _OfflineBannerState extends State<OfflineBanner> {
  bool _offline = false;

  @override
  void initState() {
    super.initState();
    Connectivity().checkConnectivity().then(_apply);
    Connectivity().onConnectivityChanged.listen(_apply);
  }

  void _apply(List<ConnectivityResult> r) {
    final off = r.isEmpty || r.every((x) => x == ConnectivityResult.none);
    if (mounted && off != _offline) setState(() => _offline = off);
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedSize(
      duration: Motion.base,
      curve: Motion.standard,
      child: _offline
          ? Container(
              width: double.infinity,
              color: FlashColors.warningBg,
              padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 12),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(
                    Icons.cloud_off,
                    size: 16,
                    color: FlashColors.warningFg,
                  ),
                  const SizedBox(width: 8),
                  Text(
                    L10n.of(context).errorOffline,
                    style: const TextStyle(
                      color: FlashColors.warningFg,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            )
          : const SizedBox.shrink(),
    );
  }
}
