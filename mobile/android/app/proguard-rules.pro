# Flutter + plugins : règles conservatrices (MOB-038).
-keep class io.flutter.** { *; }
-keep class io.flutter.plugins.** { *; }
-dontwarn io.flutter.embedding.**
# mobile_scanner (ML Kit)
-keep class com.google.mlkit.** { *; }
-dontwarn com.google.mlkit.**
# local_auth
-keep class androidx.biometric.** { *; }
