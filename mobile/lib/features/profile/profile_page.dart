import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../../core/network/api_client.dart';
import '../../l10n/generated/app_localizations.dart';
import '../../shared/widgets/app_snackbar.dart';
import '../../shared/widgets/common.dart';
import '../agent/agent_page.dart';
import '../auth/auth_controller.dart';
import '../wallet/wallet_providers.dart';

class ProfilePage extends ConsumerStatefulWidget {
  const ProfilePage({super.key});

  @override
  ConsumerState<ProfilePage> createState() => _ProfilePageState();
}

class _ProfilePageState extends ConsumerState<ProfilePage> {
  bool _uploading = false;

  Future<void> _submitKyc(int targetTier) async {
    final picker = ImagePicker();
    final id = await picker.pickImage(
      source: ImageSource.camera,
      imageQuality: 70,
    );
    if (id == null) return;
    final selfie = await picker.pickImage(
      source: ImageSource.camera,
      imageQuality: 70,
      preferredCameraDevice: CameraDevice.front,
    );
    if (selfie == null) return;

    setState(() => _uploading = true);
    try {
      final docs = [
        for (final (kind, file) in [('ID_DOCUMENT', id), ('SELFIE', selfie)])
          {
            'kind': kind,
            'content_base64': base64Encode(await file.readAsBytes()),
            'content_type': 'image/jpeg',
          },
      ];
      await ref.read(apiClientProvider).postJson(
        '/v1/kyc/submissions',
        body: {'target_tier': targetTier, 'documents': docs},
      );
      ref.invalidate(kycStatusProvider);
      if (mounted) {
        AppSnack.success(context, 'Dossier envoyé. Vérification en cours.');
      }
    } catch (e) {
      if (mounted) AppSnack.error(context, e);
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = L10n.of(context);
    final userId = ref.watch(authControllerProvider).userId ?? '—';
    final kyc = ref.watch(kycStatusProvider);

    return Scaffold(
      appBar: AppBar(title: Text(l.navProfile)),
      body: ListView(
        children: [
          const SizedBox(height: 12),
          Center(child: Avatar(label: userId, size: 72)),
          const SizedBox(height: 12),
          Center(
            child: Text(
              'ID $userId',
              style: TextStyle(color: Theme.of(context).hintColor),
            ),
          ),
          const SizedBox(height: 24),

          // ---- KYC
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: kyc.when(
                  loading: () => const Skeleton(height: 60),
                  error: (_, __) => const Text('Statut KYC indisponible'),
                  data: (k) => Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const Icon(Icons.verified_user_outlined),
                          const SizedBox(width: 8),
                          Text('Palier de vérification : ${k.tier}'),
                          const Spacer(),
                          Chip(label: Text(k.label)),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Un palier supérieur augmente vos plafonds de transfert et de retrait.',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                      const SizedBox(height: 12),
                      if (k.tier < 2)
                        FilledButton.icon(
                          onPressed:
                              _uploading ? null : () => _submitKyc(k.tier + 1),
                          icon: _uploading
                              ? const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : const Icon(Icons.photo_camera_outlined),
                          label: const Text('Pièce d\'identité + selfie'),
                        ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 8),

          if (ref.watch(isAgentProvider).valueOrNull ?? false)
            _NavTile(
              icon: Icons.badge_outlined,
              label: 'Espace agent',
              onTap: () => context.push('/agent'),
            ),
          _NavTile(
            icon: Icons.phone_iphone,
            label: 'Mes numéros',
            onTap: () => context.push('/profile/phones'),
          ),
          _NavTile(
            icon: Icons.notifications_none,
            label: 'Notifications',
            onTap: () => context.push('/profile/notifications'),
          ),
          _NavTile(
            icon: Icons.shield_outlined,
            label: 'Sécurité',
            onTap: () => context.push('/profile/security'),
          ),
          _NavTile(
            icon: Icons.settings_outlined,
            label: 'Paramètres',
            onTap: () => context.push('/profile/settings'),
          ),
          _NavTile(
            icon: Icons.info_outline,
            label: 'À propos',
            onTap: () => context.push('/profile/about'),
          ),
          const SizedBox(height: 12),
          Padding(
            padding: const EdgeInsets.all(16),
            child: OutlinedButton.icon(
              onPressed: () =>
                  ref.read(authControllerProvider.notifier).signOut(),
              icon: const Icon(Icons.logout),
              label: const Text('Se déconnecter'),
            ),
          ),
        ],
      ),
    );
  }
}

class _NavTile extends StatelessWidget {
  const _NavTile({
    required this.icon,
    required this.label,
    required this.onTap,
  });
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(icon),
      title: Text(label),
      trailing: const Icon(Icons.chevron_right),
      onTap: onTap,
    );
  }
}
