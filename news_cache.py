"""
Couche de cache pour le service d'actualités Pkapkato.

Objectif : éviter de refaire un fetch RSS par utilisateur alors que
plusieurs utilisateurs peuvent partager les mêmes centres d'intérêt.
Le scheduler quotidien doit :
  1. Rafraîchir le cache une seule fois par catégorie active (pas par utilisateur).
  2. Piocher dedans pour chaque utilisateur, en excluant ce qu'il a déjà reçu.

Pour le MVP, on utilise SQLite (fichier local, zéro configuration).
En production, ce sera la même logique mais sur PostgreSQL
(cf. schéma news_feed_cache / news_sent_log défini plus tôt).
"""

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

from news_service import fetch_news_for_category, NewsArticle


DB_PATH = "pkapkato_news_cache.db"

# Au-delà de cette durée, une entrée de cache est considérée périmée
# et doit être rafraîchie au prochain passage du scheduler.
CACHE_TTL_HOURS = 6


def init_db(db_path: str = DB_PATH):
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS news_feed_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_url TEXT NOT NULL UNIQUE,
                published_at TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS news_sent_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                source_url TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                opened INTEGER DEFAULT 0
            )
        """)
        conn.commit()


def _category_needs_refresh(conn, category: str) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=CACHE_TTL_HOURS)).isoformat()
    row = conn.execute(
        "SELECT MAX(fetched_at) FROM news_feed_cache WHERE category = ?",
        (category,),
    ).fetchone()
    last_fetch = row[0]
    return last_fetch is None or last_fetch < cutoff


def refresh_category_cache(category: str, db_path: str = DB_PATH):
    """
    Rafraîchit le cache pour UNE catégorie, si besoin.
    A appeler une fois par catégorie active dans le job quotidien,
    jamais une fois par utilisateur.
    """
    with closing(sqlite3.connect(db_path)) as conn:
        if not _category_needs_refresh(conn, category):
            return 0  # cache encore valide, rien à faire

        try:
            articles = fetch_news_for_category(category, limit=5)
        except Exception as e:
            # Une source d'actualité indisponible ne doit jamais faire
            # échouer tout le job du scheduler pour tous les utilisateurs.
            print(f"[news_cache] Échec du rafraîchissement pour '{category}': {e}")
            return 0

        now_iso = datetime.now(timezone.utc).isoformat()

        inserted = 0
        for a in articles:
            try:
                conn.execute(
                    """
                    INSERT INTO news_feed_cache
                        (category, title, source_name, source_url, published_at, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (a.category, a.title, a.source_name, a.source_url,
                     a.published_at.isoformat(), now_iso),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                # source_url déjà en cache (UNIQUE) : on ignore, pas une erreur.
                continue

        conn.commit()
        return inserted


def refresh_all_active_categories(active_categories: list[str], db_path: str = DB_PATH):
    """
    A appeler une fois par jour par le scheduler, avec la liste de TOUTES
    les catégories suivies par au moins un utilisateur (dédupliquée en amont).
    """
    results = {}
    for category in active_categories:
        results[category] = refresh_category_cache(category, db_path=db_path)
    return results


def get_unsent_article_for_user(user_id: str, categories: list[str], db_path: str = DB_PATH):
    """
    Pioche dans le cache un article correspondant aux centres d'intérêt
    de l'utilisateur, pas encore envoyé, le plus récent en premier.
    Retourne un dict (ou None si rien de disponible).
    """
    if not categories:
        return None

    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" * len(categories))

        rows = conn.execute(
            f"""
            SELECT * FROM news_feed_cache
            WHERE category IN ({placeholders})
              AND source_url NOT IN (
                  SELECT source_url FROM news_sent_log WHERE user_id = ?
              )
            ORDER BY published_at DESC
            """,
            (*categories, user_id),
        ).fetchall()

        return dict(rows[0]) if rows else None


def log_news_sent(user_id: str, source_url: str, db_path: str = DB_PATH):
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            "INSERT INTO news_sent_log (user_id, source_url, sent_at) VALUES (?, ?, ?)",
            (user_id, source_url, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def was_news_sent_this_week(user_id: str, db_path: str = DB_PATH, max_per_week: int = 2) -> bool:
    """
    Applique la règle produit : max 2 actualités envoyées par semaine et par utilisateur.
    Retourne True si la limite est déjà atteinte (donc: ne pas envoyer aujourd'hui).
    """
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    with closing(sqlite3.connect(db_path)) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM news_sent_log WHERE user_id = ? AND sent_at >= ?",
            (user_id, week_ago),
        ).fetchone()[0]
    return count >= max_per_week


if __name__ == "__main__":
    # Démo bout-en-bout (nécessite un accès réseau à news.google.com,
    # indisponible dans ce sandbox mais fonctionnel en environnement normal).
    init_db()

    demo_user_id = "user_123"
    demo_categories = ["technologie", "basketball"]

    print("1. Rafraîchissement du cache (une fois par catégorie)...")
    refresh_all_active_categories(demo_categories)

    print("2. Vérification de la limite hebdomadaire...")
    if was_news_sent_this_week(demo_user_id):
        print("   Limite déjà atteinte cette semaine, on n'envoie rien.")
    else:
        article = get_unsent_article_for_user(demo_user_id, demo_categories)
        if article:
            print(f"3. Article sélectionné : {article['title']} ({article['source_name']})")
            log_news_sent(demo_user_id, article["source_url"])
        else:
            print("3. Aucun article disponible pour le moment.")
