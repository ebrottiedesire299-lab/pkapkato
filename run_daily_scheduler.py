#!/usr/bin/env python3
"""
Point d'entrée pour l'exécution automatique quotidienne du scheduler Pkapkato.

Usage en production (exemple crontab, exécution tous les jours à 6h) :
    0 6 * * *  cd /chemin/vers/pkapkato && /usr/bin/python3 run_daily_scheduler.py >> /var/log/pkapkato_scheduler.log 2>&1

Ce script ne dépend pas de l'API FastAPI : il appelle directement les
fonctions Python du scheduler, ce qui est plus robuste qu'un appel HTTP
interne (pas besoin que le serveur web tourne pour que les notifications
partent).

Note sur les fuseaux horaires : ce MVP déclenche un run global unique.
En production avec des utilisateurs dans plusieurs fuseaux horaires,
il faudra soit lancer ce script plusieurs fois par jour en filtrant les
utilisateurs par `user.timezone` (envoyer à chacun vers 6h SA heure locale),
soit accepter un horaire unique pour la V1 si les utilisateurs sont
concentrés dans peu de fuseaux (ex: Côte d'Ivoire uniquement).
"""

import sys
from datetime import datetime, timezone

from database import SessionLocal, init_db
from models import User
import news_cache
import scheduler as scheduler_module


def main():
    print(f"[run_daily_scheduler] Démarrage — {datetime.now(timezone.utc).isoformat()}")

    init_db()
    news_cache.init_db()

    db = SessionLocal()
    try:
        users = db.query(User).all()
        print(f"[run_daily_scheduler] {len(users)} utilisateur(s) à traiter.")

        sent_count = scheduler_module.run_daily_job_for_all_users(db, users)

        print(f"[run_daily_scheduler] Terminé — {sent_count} notification(s) envoyée(s).")
        return 0
    except Exception as e:
        print(f"[run_daily_scheduler] ERREUR FATALE: {e}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
