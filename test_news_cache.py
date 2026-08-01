import sqlite3
from datetime import datetime, timezone

import news_cache as nc
from news_service import NewsArticle

nc.init_db()

fake_articles = [
    NewsArticle("Nouvelle avancée en IA", "Le Monde", "https://example.com/a1",
                datetime.now(timezone.utc), "technologie"),
    NewsArticle("Match de basket historique", "L'Equipe", "https://example.com/a2",
                datetime.now(timezone.utc), "basketball"),
]

with sqlite3.connect(nc.DB_PATH) as conn:
    for a in fake_articles:
        conn.execute(
            "INSERT INTO news_feed_cache "
            "(category, title, source_name, source_url, published_at, fetched_at) "
            "VALUES (?,?,?,?,?,?)",
            (a.category, a.title, a.source_name, a.source_url,
             a.published_at.isoformat(), datetime.now(timezone.utc).isoformat()),
        )
    conn.commit()

user = "user_123"
cats = ["technologie", "basketball"]

art = nc.get_unsent_article_for_user(user, cats)
print("Test 1 - article recupere:", art["title"] if art else None)
assert art is not None

nc.log_news_sent(user, art["source_url"])
art2 = nc.get_unsent_article_for_user(user, cats)
print("Test 2 - prochain article (doit etre different):", art2["title"] if art2 else None)
assert art2["source_url"] != art["source_url"]

nc.log_news_sent(user, art2["source_url"])
limit_reached = nc.was_news_sent_this_week(user, max_per_week=2)
print("Test 3 - limite atteinte apres 2 envois:", limit_reached)
assert limit_reached is True

print("TOUS LES TESTS PASSENT")
