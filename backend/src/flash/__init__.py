"""Flash — plateforme de monnaie électronique.

Architecture hexagonale : ``domain`` (cœur, sans dépendance externe), ``application``
(cas d'usage), ``infrastructure`` (adapters), ``interface`` (Flask, CLI, jobs).
"""

__version__ = "0.1.0"
