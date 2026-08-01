"""
Scheduler quotidien Pkapkato.

Règle centrale : UNE SEULE notification par utilisateur par jour.
Priorité : échéance urgente > document en attente de résumé
           > actualité pertinente > encouragement matière négligée.

Ce module ne dépend pas d'un framework de tâches planifiées (cron, Celery...)
en particulier : `run_daily_job_for_user()` est la fonction pure à brancher
sur n'importe quel ordonnanceur (cron système, APScheduler, Celery beat...).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models import Task, Document, NotificationLog
import news_cache
import push_service



URGENT_THRESHOLD_DAYS = 3
INACTIVE_SUBJECT_THRESHOLD_DAYS = 4


def _days_until(due_date: datetime) -> int:
    now = datetime.now(timezone.utc)
    due = due_date if due_date.tzinfo else due_date.replace(tzinfo=timezone.utc)
    return (due - now).days


def _check_urgent_task(db: Session, user):
    candidates = [
        t for t in user.tasks
        if t.status != "terminé" and 0 <= _days_until(t.due_date) <= URGENT_THRESHOLD_DAYS
    ]
    if not candidates:
        return None

    priority_order = {"examen": 0, "projet": 1, "devoir": 2}
    candidates.sort(key=lambda t: (priority_order.get(t.type, 9), t.due_date))
    task = candidates[0]

    days_left = _days_until(task.due_date)
    delay = "aujourd'hui" if days_left == 0 else f"dans {days_left} jour(s)"
    message = f"Ton {task.type} de {task.subject} (« {task.title} ») est {delay}."
    return {"reason": "echeance", "message": message}


def _check_pending_document(db: Session, user):
    pending = [d for d in user.documents if not d.summary_text]
    if not pending:
        return None
    doc = pending[0]
    message = f"J'ai un résumé prêt pour ton document « {doc.original_filename} » ({doc.subject})."
    return {"reason": "document", "message": message}


def _check_news(db: Session, user):
    categories = [i.category for i in user.interests]
    if not categories:
        return None
    if news_cache.was_news_sent_this_week(user.id):
        return None
    article = news_cache.get_unsent_article_for_user(user.id, categories)
    if not article:
        return None
    message = (
        f"Actu qui pourrait t'intéresser : {article['title']} "
        f"(source : {article['source_name']})."
    )
    return {"reason": "actualite", "message": message, "_article": article}


def _check_neglected_subject(db: Session, user):
    """
    Version simplifiée pour le MVP : on regarde si une matière a des tâches
    en cours mais aucune mise à jour de statut récente (proxy simple,
    faute d'un vrai tracking d'activité par matière en V1).
    """
    now = datetime.now(timezone.utc)
    subjects_with_open_tasks = {t.subject for t in user.tasks if t.status == "à faire"}
    for subject in subjects_with_open_tasks:
        subject_tasks = [t for t in user.tasks if t.subject == subject]
        most_recent = max(t.created_at for t in subject_tasks)
        most_recent = most_recent if most_recent.tzinfo else most_recent.replace(tzinfo=timezone.utc)
        if (now - most_recent).days >= INACTIVE_SUBJECT_THRESHOLD_DAYS:
            message = f"Ça fait un moment que tu n'as pas avancé en {subject}. Une petite session ?"
            return {"reason": "encouragement", "message": message}
    return None


def run_daily_job_for_user(db: Session, user):
    """
    Retourne UNE décision de notification (dict) pour cet utilisateur, ou None
    si rien à envoyer aujourd'hui. Applique la priorité définie dans la conception.
    """
    for check in (_check_urgent_task, _check_pending_document, _check_news, _check_neglected_subject):
        result = check(db, user)
        if result:
            return result
    return None


def send_notification(db: Session, user, decision: dict):
    """
    Enregistre la notification dans notifications_log et, si c'est une actualité,
    marque l'article comme envoyé dans news_sent_log pour ne pas le répéter.
    L'envoi push réel (Firebase Cloud Messaging) est un point d'intégration
    séparé, volontairement isolé ici derrière une fonction à brancher plus tard.
    """
    log_entry = NotificationLog(
        user_id=user.id,
        message_sent=decision["message"],
        reason=decision["reason"],
    )
    db.add(log_entry)

    if decision["reason"] == "actualite" and "_article" in decision:
        news_cache.log_news_sent(user.id, decision["_article"]["source_url"])

    db.commit()
    _push_to_device(user, decision["message"])  # point d'intégration FCM


def _push_to_device(user, message: str):
    push_service.send_push_notification(
        device_token=user.device_token,
        title=user.ia_name,
        body=message,
    )


def run_daily_job_for_all_users(db: Session, users: list):
    """
    A brancher sur un cron quotidien (ex: 6h locale, ou par lot selon fuseau horaire).
    D'abord on rafraîchit le cache actu pour toutes les catégories actives (une fois),
    puis on arbitre par utilisateur.
    """
    all_categories = {i.category for u in users for i in u.interests}
    if all_categories:
        news_cache.refresh_all_active_categories(list(all_categories))

    sent_count = 0
    for user in users:
        decision = run_daily_job_for_user(db, user)
        if decision:
            send_notification(db, user, decision)
            sent_count += 1
    return sent_count
