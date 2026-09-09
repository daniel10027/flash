import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app.dart';
import '../../l10n/generated/app_localizations.dart';

class SettingsPage extends ConsumerWidget {
  const SettingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final mode = ref.watch(themeModeProvider);
    final locale = ref.watch(localeProvider);
    final hidden = ref.watch(hideBalancesProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Paramètres')),
      body: ListView(
        children: [
          const _SectionLabel('Apparence'),
          RadioGroup<ThemeMode>(
            groupValue: mode,
            onChanged: (m) =>
                ref.read(themeModeProvider.notifier).set(m ?? ThemeMode.system),
            child: const Column(
              children: [
                RadioListTile(
                  value: ThemeMode.system,
                  title: Text('Automatique (système)'),
                ),
                RadioListTile(value: ThemeMode.light, title: Text('Clair')),
                RadioListTile(value: ThemeMode.dark, title: Text('Sombre')),
              ],
            ),
          ),
          const Divider(),
          const _SectionLabel('Langue'),
          RadioGroup<String>(
            groupValue: locale?.languageCode ?? 'system',
            onChanged: (v) => ref.read(localeProvider.notifier).set(
                  v == 'system' ? null : Locale(v!),
                ),
            child: const Column(
              children: [
                RadioListTile(value: 'system', title: Text('Automatique')),
                RadioListTile(value: 'fr', title: Text('Français')),
                RadioListTile(value: 'en', title: Text('English')),
              ],
            ),
          ),
          const Divider(),
          const _SectionLabel('Confidentialité'),
          SwitchListTile(
            value: hidden,
            onChanged: (_) => ref.read(hideBalancesProvider.notifier).toggle(),
            title: const Text('Masquer les soldes par défaut'),
            secondary: const Icon(Icons.visibility_off_outlined),
          ),
          const Divider(),
          ListTile(
            leading: const Icon(Icons.description_outlined),
            title: const Text('Mentions légales'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () {},
          ),
          ListTile(
            leading: const Icon(Icons.privacy_tip_outlined),
            title: Text(L10n.of(context).comingSoon),
            enabled: false,
          ),
        ],
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 20, 16, 4),
      child: Text(
        text.toUpperCase(),
        style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: Theme.of(context).colorScheme.primary,
              letterSpacing: 1,
            ),
      ),
    );
  }
}
