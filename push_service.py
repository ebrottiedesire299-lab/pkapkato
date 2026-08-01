"""
Service de notifications push Pkapkato, via Firebase Cloud Messaging (FCM).

Nécessite en production :
  - un fichier de clé de compte de service Firebase (JSON), généré depuis
    la console Firebase (Paramètres du projet > Comptes de service).
  - la variable d'environnement FIREBASE_CREDENTIALS_PATH pointant vers ce fichier.

Comportement volontaire si Firebase n'est pas configuré : on ne fait PAS
planter le scheduler pour tous les utilisateurs à cause d'un push manquant.
On log un avertissement et on continue (même logique de résilience que
pour les échecs de fetch d'actualités).
"""

import os

import firebase_admin
from firebase_admin import credentials, messaging

_firebase_app = None
_init_attempted = False


def _get_firebase_app():
    global _firebase_app, _init_attempted
    if _firebase_app is not None:
        return _firebase_app
    if _init_attempted:
        return None  # déjà tenté et échoué, inutile de réessayer à chaque appel

    _init_attempted = True
    cred_path = os.environ.get("FIREBASE_CREDENTIALS_PATH")
    if not cred_path or not os.path.exists(cred_path):
        print(
            "[push_service] FIREBASE_CREDENTIALS_PATH non défini ou fichier introuvable. "
            "Les notifications push sont désactivées (mode dégradé)."
        )
        return None

    try:
        cred = credentials.Certificate(cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        return _firebase_app
    except Exception as e:
        print(f"[push_service] Échec d'initialisation Firebase: {e}")
        return None


def send_push_notification(device_token: str, title: str, body: str) -> bool:
    """
    Envoie une notification push à un appareil donné.
    Retourne True si l'envoi a réussi, False sinon (jamais d'exception
    qui remonterait et casserait l'appelant : un échec de notif ne doit
    jamais faire échouer tout le job de notification).
    """
    if not device_token:
        print(f"[push_service] Pas de device_token pour cet utilisateur, notification non envoyée: {title}")
        return False

    app = _get_firebase_app()
    if app is None:
        print(f"[push_service] Firebase non configuré (mode dégradé) -> {title}: {body}")
        return False

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        token=device_token,
    )

    try:
        messaging.send(message, app=app)
        return True
    except Exception as e:
        print(f"[push_service] Échec de l'envoi push: {e}")
        return False
