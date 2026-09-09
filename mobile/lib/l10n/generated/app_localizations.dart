import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_en.dart';
import 'app_localizations_fr.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of L10n
/// returned by `L10n.of(context)`.
///
/// Applications need to include `L10n.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'generated/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: L10n.localizationsDelegates,
///   supportedLocales: L10n.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the L10n.supportedLocales
/// property.
abstract class L10n {
  L10n(String locale)
      : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static L10n of(BuildContext context) {
    return Localizations.of<L10n>(context, L10n)!;
  }

  static const LocalizationsDelegate<L10n> delegate = _L10nDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
    delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
  ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('en'),
    Locale('fr')
  ];

  /// No description provided for @appName.
  ///
  /// In fr, this message translates to:
  /// **'Flash'**
  String get appName;

  /// No description provided for @onboardTitle1.
  ///
  /// In fr, this message translates to:
  /// **'Envoyez en un éclair'**
  String get onboardTitle1;

  /// No description provided for @onboardBody1.
  ///
  /// In fr, this message translates to:
  /// **'De l\'argent à un proche, à un numéro, à un contact — reçu en quelques secondes.'**
  String get onboardBody1;

  /// No description provided for @onboardTitle2.
  ///
  /// In fr, this message translates to:
  /// **'Payez sans contact'**
  String get onboardTitle2;

  /// No description provided for @onboardBody2.
  ///
  /// In fr, this message translates to:
  /// **'Scannez le QR d\'un marchand, réglez, repartez. Zéro frais pour vous.'**
  String get onboardBody2;

  /// No description provided for @onboardTitle3.
  ///
  /// In fr, this message translates to:
  /// **'Faites grandir votre argent'**
  String get onboardTitle3;

  /// No description provided for @onboardBody3.
  ///
  /// In fr, this message translates to:
  /// **'Coffres, plans d\'épargne, carte virtuelle : tout Flash, dans une seule app.'**
  String get onboardBody3;

  /// No description provided for @onboardSkip.
  ///
  /// In fr, this message translates to:
  /// **'Passer'**
  String get onboardSkip;

  /// No description provided for @onboardNext.
  ///
  /// In fr, this message translates to:
  /// **'Suivant'**
  String get onboardNext;

  /// No description provided for @onboardStart.
  ///
  /// In fr, this message translates to:
  /// **'Commencer'**
  String get onboardStart;

  /// No description provided for @actionContinue.
  ///
  /// In fr, this message translates to:
  /// **'Continuer'**
  String get actionContinue;

  /// No description provided for @actionBack.
  ///
  /// In fr, this message translates to:
  /// **'Retour'**
  String get actionBack;

  /// No description provided for @actionRetry.
  ///
  /// In fr, this message translates to:
  /// **'Réessayer'**
  String get actionRetry;

  /// No description provided for @actionCancel.
  ///
  /// In fr, this message translates to:
  /// **'Annuler'**
  String get actionCancel;

  /// No description provided for @navHome.
  ///
  /// In fr, this message translates to:
  /// **'Accueil'**
  String get navHome;

  /// No description provided for @navHistory.
  ///
  /// In fr, this message translates to:
  /// **'Historique'**
  String get navHistory;

  /// No description provided for @navScan.
  ///
  /// In fr, this message translates to:
  /// **'Payer'**
  String get navScan;

  /// No description provided for @navCard.
  ///
  /// In fr, this message translates to:
  /// **'Carte'**
  String get navCard;

  /// No description provided for @navProfile.
  ///
  /// In fr, this message translates to:
  /// **'Profil'**
  String get navProfile;

  /// No description provided for @lockTitle.
  ///
  /// In fr, this message translates to:
  /// **'Déverrouillez Flash'**
  String get lockTitle;

  /// No description provided for @lockSubtitle.
  ///
  /// In fr, this message translates to:
  /// **'Saisissez votre code secret'**
  String get lockSubtitle;

  /// No description provided for @lockUseBiometrics.
  ///
  /// In fr, this message translates to:
  /// **'Utiliser la biométrie'**
  String get lockUseBiometrics;

  /// No description provided for @lockWrongPin.
  ///
  /// In fr, this message translates to:
  /// **'Code incorrect'**
  String get lockWrongPin;

  /// No description provided for @authPhone.
  ///
  /// In fr, this message translates to:
  /// **'Numéro de téléphone'**
  String get authPhone;

  /// No description provided for @authCountry.
  ///
  /// In fr, this message translates to:
  /// **'Pays'**
  String get authCountry;

  /// No description provided for @authPin.
  ///
  /// In fr, this message translates to:
  /// **'Code secret'**
  String get authPin;

  /// No description provided for @authSignIn.
  ///
  /// In fr, this message translates to:
  /// **'Se connecter'**
  String get authSignIn;

  /// No description provided for @authCreateAccount.
  ///
  /// In fr, this message translates to:
  /// **'Créer un compte'**
  String get authCreateAccount;

  /// No description provided for @authForgotPin.
  ///
  /// In fr, this message translates to:
  /// **'Code secret oublié ?'**
  String get authForgotPin;

  /// No description provided for @authOtp.
  ///
  /// In fr, this message translates to:
  /// **'Code de vérification'**
  String get authOtp;

  /// No description provided for @authResendOtp.
  ///
  /// In fr, this message translates to:
  /// **'Renvoyer le code'**
  String get authResendOtp;

  /// No description provided for @balanceTitle.
  ///
  /// In fr, this message translates to:
  /// **'Solde disponible'**
  String get balanceTitle;

  /// No description provided for @balanceHidden.
  ///
  /// In fr, this message translates to:
  /// **'••••••'**
  String get balanceHidden;

  /// No description provided for @quickSend.
  ///
  /// In fr, this message translates to:
  /// **'Envoyer'**
  String get quickSend;

  /// No description provided for @quickPay.
  ///
  /// In fr, this message translates to:
  /// **'Payer'**
  String get quickPay;

  /// No description provided for @quickWithdraw.
  ///
  /// In fr, this message translates to:
  /// **'Retirer'**
  String get quickWithdraw;

  /// No description provided for @quickTopUp.
  ///
  /// In fr, this message translates to:
  /// **'Ajouter'**
  String get quickTopUp;

  /// No description provided for @errorOffline.
  ///
  /// In fr, this message translates to:
  /// **'Vous êtes hors ligne'**
  String get errorOffline;

  /// No description provided for @errorOfflineBody.
  ///
  /// In fr, this message translates to:
  /// **'Vérifiez votre connexion, les dernières données restent consultables.'**
  String get errorOfflineBody;

  /// No description provided for @errorGeneric.
  ///
  /// In fr, this message translates to:
  /// **'Une erreur est survenue'**
  String get errorGeneric;

  /// No description provided for @comingSoon.
  ///
  /// In fr, this message translates to:
  /// **'Bientôt disponible'**
  String get comingSoon;
}

class _L10nDelegate extends LocalizationsDelegate<L10n> {
  const _L10nDelegate();

  @override
  Future<L10n> load(Locale locale) {
    return SynchronousFuture<L10n>(lookupL10n(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en', 'fr'].contains(locale.languageCode);

  @override
  bool shouldReload(_L10nDelegate old) => false;
}

L10n lookupL10n(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return L10nEn();
    case 'fr':
      return L10nFr();
  }

  throw FlutterError(
      'L10n.delegate failed to load unsupported locale "$locale". This is likely '
      'an issue with the localizations generation tool. Please file an issue '
      'on GitHub with a reproducible sample app and the gen-l10n configuration '
      'that was used.');
}
