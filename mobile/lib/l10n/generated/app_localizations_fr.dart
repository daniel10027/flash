// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for French (`fr`).
class L10nFr extends L10n {
  L10nFr([String locale = 'fr']) : super(locale);

  @override
  String get appName => 'Flash';

  @override
  String get onboardTitle1 => 'Envoyez en un éclair';

  @override
  String get onboardBody1 =>
      'De l\'argent à un proche, à un numéro, à un contact — reçu en quelques secondes.';

  @override
  String get onboardTitle2 => 'Payez sans contact';

  @override
  String get onboardBody2 =>
      'Scannez le QR d\'un marchand, réglez, repartez. Zéro frais pour vous.';

  @override
  String get onboardTitle3 => 'Faites grandir votre argent';

  @override
  String get onboardBody3 =>
      'Coffres, plans d\'épargne, carte virtuelle : tout Flash, dans une seule app.';

  @override
  String get onboardSkip => 'Passer';

  @override
  String get onboardNext => 'Suivant';

  @override
  String get onboardStart => 'Commencer';

  @override
  String get actionContinue => 'Continuer';

  @override
  String get actionBack => 'Retour';

  @override
  String get actionRetry => 'Réessayer';

  @override
  String get actionCancel => 'Annuler';

  @override
  String get navHome => 'Accueil';

  @override
  String get navHistory => 'Historique';

  @override
  String get navScan => 'Payer';

  @override
  String get navCard => 'Carte';

  @override
  String get navProfile => 'Profil';

  @override
  String get lockTitle => 'Déverrouillez Flash';

  @override
  String get lockSubtitle => 'Saisissez votre code secret';

  @override
  String get lockUseBiometrics => 'Utiliser la biométrie';

  @override
  String get lockWrongPin => 'Code incorrect';

  @override
  String get authPhone => 'Numéro de téléphone';

  @override
  String get authCountry => 'Pays';

  @override
  String get authPin => 'Code secret';

  @override
  String get authSignIn => 'Se connecter';

  @override
  String get authCreateAccount => 'Créer un compte';

  @override
  String get authForgotPin => 'Code secret oublié ?';

  @override
  String get authOtp => 'Code de vérification';

  @override
  String get authResendOtp => 'Renvoyer le code';

  @override
  String get balanceTitle => 'Solde disponible';

  @override
  String get balanceHidden => '••••••';

  @override
  String get quickSend => 'Envoyer';

  @override
  String get quickPay => 'Payer';

  @override
  String get quickWithdraw => 'Retirer';

  @override
  String get quickTopUp => 'Ajouter';

  @override
  String get errorOffline => 'Vous êtes hors ligne';

  @override
  String get errorOfflineBody =>
      'Vérifiez votre connexion, les dernières données restent consultables.';

  @override
  String get errorGeneric => 'Une erreur est survenue';

  @override
  String get comingSoon => 'Bientôt disponible';
}
