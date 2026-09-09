import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Préférences non sensibles (onboarding vu, thème, langue, masquer soldes).
class Prefs {
  Prefs(this._sp);
  final SharedPreferences _sp;

  static const _kOnboarded = 'flash.onboarded';
  static const _kHomeTutorial = 'flash.homeTutorial';
  static const _kThemeMode = 'flash.themeMode';
  static const _kLocale = 'flash.locale';
  static const _kHideBalances = 'flash.hideBalances';

  bool get onboarded => _sp.getBool(_kOnboarded) ?? false;
  Future<void> setOnboarded(bool v) => _sp.setBool(_kOnboarded, v);

  bool get homeTutorialSeen => _sp.getBool(_kHomeTutorial) ?? false;
  Future<void> setHomeTutorialSeen(bool v) => _sp.setBool(_kHomeTutorial, v);

  ThemeMode get themeMode => switch (_sp.getString(_kThemeMode)) {
        'light' => ThemeMode.light,
        'dark' => ThemeMode.dark,
        _ => ThemeMode.system,
      };
  Future<void> setThemeMode(ThemeMode m) => _sp.setString(_kThemeMode, m.name);

  Locale? get locale {
    final code = _sp.getString(_kLocale);
    return code == null ? null : Locale(code);
  }

  Future<void> setLocale(Locale? l) => l == null
      ? _sp.remove(_kLocale)
      : _sp.setString(_kLocale, l.languageCode);

  bool get hideBalances => _sp.getBool(_kHideBalances) ?? false;
  Future<void> setHideBalances(bool v) => _sp.setBool(_kHideBalances, v);
}

/// Résolu au démarrage dans `bootstrap.dart` puis injecté par override.
final prefsProvider = Provider<Prefs>((ref) {
  throw StateError('prefsProvider doit être surchargé au bootstrap');
});
