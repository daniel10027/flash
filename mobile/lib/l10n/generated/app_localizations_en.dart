// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class L10nEn extends L10n {
  L10nEn([String locale = 'en']) : super(locale);

  @override
  String get appName => 'Flash';

  @override
  String get onboardTitle1 => 'Send in a flash';

  @override
  String get onboardBody1 =>
      'Money to a friend, a number, a contact — received in seconds.';

  @override
  String get onboardTitle2 => 'Pay contactless';

  @override
  String get onboardBody2 =>
      'Scan a merchant QR, pay, walk away. Zero fees for you.';

  @override
  String get onboardTitle3 => 'Grow your money';

  @override
  String get onboardBody3 =>
      'Vaults, savings plans, a virtual card: all of Flash, in one app.';

  @override
  String get onboardSkip => 'Skip';

  @override
  String get onboardNext => 'Next';

  @override
  String get onboardStart => 'Get started';

  @override
  String get actionContinue => 'Continue';

  @override
  String get actionBack => 'Back';

  @override
  String get actionRetry => 'Retry';

  @override
  String get actionCancel => 'Cancel';

  @override
  String get navHome => 'Home';

  @override
  String get navHistory => 'History';

  @override
  String get navScan => 'Pay';

  @override
  String get navCard => 'Card';

  @override
  String get navProfile => 'Profile';

  @override
  String get lockTitle => 'Unlock Flash';

  @override
  String get lockSubtitle => 'Enter your secret code';

  @override
  String get lockUseBiometrics => 'Use biometrics';

  @override
  String get lockWrongPin => 'Wrong code';

  @override
  String get authPhone => 'Phone number';

  @override
  String get authCountry => 'Country';

  @override
  String get authPin => 'Secret code';

  @override
  String get authSignIn => 'Sign in';

  @override
  String get authCreateAccount => 'Create account';

  @override
  String get authForgotPin => 'Forgot your code?';

  @override
  String get authOtp => 'Verification code';

  @override
  String get authResendOtp => 'Resend code';

  @override
  String get balanceTitle => 'Available balance';

  @override
  String get balanceHidden => '••••••';

  @override
  String get quickSend => 'Send';

  @override
  String get quickPay => 'Pay';

  @override
  String get quickWithdraw => 'Withdraw';

  @override
  String get quickTopUp => 'Top up';

  @override
  String get errorOffline => 'You are offline';

  @override
  String get errorOfflineBody =>
      'Check your connection; your latest data stays available.';

  @override
  String get errorGeneric => 'Something went wrong';

  @override
  String get comingSoon => 'Coming soon';
}
