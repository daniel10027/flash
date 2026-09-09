import 'package:flutter/material.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../../core/env/flavor.dart';
import '../../core/theme/tokens.dart';

/// MOB-044 — « À propos » : version + build + liens légaux.
class AboutPage extends StatelessWidget {
  const AboutPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('À propos')),
      body: FutureBuilder<PackageInfo>(
        future: PackageInfo.fromPlatform(),
        builder: (context, snap) {
          final info = snap.data;
          return ListView(
            padding: const EdgeInsets.all(24),
            children: [
              const SizedBox(height: 12),
              Center(
                child: Container(
                  width: 84,
                  height: 84,
                  decoration: BoxDecoration(
                    color: FlashColors.brand500,
                    borderRadius: BorderRadius.circular(FlashRadii.xl),
                  ),
                  child: const Icon(Icons.bolt, color: Colors.white, size: 44),
                ),
              ),
              const SizedBox(height: 16),
              Center(
                child: Text(
                  Env.label,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              Center(
                child: Text(
                  info == null
                      ? '…'
                      : 'Version ${info.version} (${info.buildNumber})',
                  style: TextStyle(color: Theme.of(context).hintColor),
                ),
              ),
              const SizedBox(height: 28),
              const ListTile(
                leading: Icon(Icons.description_outlined),
                title: Text('Conditions générales d\'utilisation'),
                trailing: Icon(Icons.open_in_new, size: 18),
              ),
              const ListTile(
                leading: Icon(Icons.privacy_tip_outlined),
                title: Text('Politique de confidentialité'),
                trailing: Icon(Icons.open_in_new, size: 18),
              ),
              const ListTile(
                leading: Icon(Icons.gavel_outlined),
                title: Text('Licences open source'),
                trailing: Icon(Icons.chevron_right),
              ),
              const SizedBox(height: 24),
              Center(
                child: Text(
                  '© ${DateTime.now().year} Flash',
                  style: TextStyle(color: Theme.of(context).hintColor),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
