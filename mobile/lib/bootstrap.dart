import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app.dart';
import 'core/storage/prefs.dart';

/// Point d'entrée commun aux flavors (`main_dev` / `main_staging` / `main_prod`).
/// Le flavor effectif est porté par `--dart-define=FLAVOR=` (voir `core/env`).
Future<void> bootstrap() async {
  WidgetsFlutterBinding.ensureInitialized();
  final sp = await SharedPreferences.getInstance();
  runApp(
    ProviderScope(
      overrides: [prefsProvider.overrideWithValue(Prefs(sp))],
      child: const FlashApp(),
    ),
  );
}
