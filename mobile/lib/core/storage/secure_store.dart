import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Petit wrapper typé sur `flutter_secure_storage` (Keychain / Keystore).
class SecureStore {
  SecureStore(this._raw);

  final FlutterSecureStorage _raw;

  static const _kRefresh = 'flash.refresh';
  static const _kDeviceId = 'flash.device';
  static const _kPinHash = 'flash.pin'; // hash local du PIN de verrouillage

  Future<String?> readRefreshToken() => _raw.read(key: _kRefresh);
  Future<void> writeRefreshToken(String value) =>
      _raw.write(key: _kRefresh, value: value);
  Future<void> clearRefreshToken() => _raw.delete(key: _kRefresh);

  Future<String?> readDeviceId() => _raw.read(key: _kDeviceId);
  Future<void> writeDeviceId(String value) =>
      _raw.write(key: _kDeviceId, value: value);

  Future<String?> readPinHash() => _raw.read(key: _kPinHash);
  Future<void> writePinHash(String value) =>
      _raw.write(key: _kPinHash, value: value);

  Future<void> wipe() => _raw.deleteAll();
}

final secureStoreProvider = Provider<SecureStore>((ref) {
  return SecureStore(
    const FlutterSecureStorage(
      aOptions: AndroidOptions(encryptedSharedPreferences: true),
      iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock),
    ),
  );
});
