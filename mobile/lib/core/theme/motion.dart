import 'package:flutter/animation.dart';

/// Vocabulaire d'animation partagé : des durées courtes, des courbes douces.
/// Un mouvement cohérent = une app qui « respire » au lieu de scintiller.
abstract final class Motion {
  static const fast = Duration(milliseconds: 150);
  static const base = Duration(milliseconds: 260);
  static const slow = Duration(milliseconds: 420);
  static const page = Duration(milliseconds: 340);

  /// Sortie douce, sans rebond — pour l'entrée d'éléments.
  static const enter = Curves.easeOutCubic;

  /// Accélère puis décélère — pour les transitions d'état.
  static const standard = Curves.easeInOutCubic;

  /// Léger dépassement — pour les confirmations / succès.
  static const emphasized = Cubic(0.2, 0.0, 0.0, 1.1);
}
