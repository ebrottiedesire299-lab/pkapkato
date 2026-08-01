"""
Service de veille actualités pour Pkapkato.

Principe : on ne demande JAMAIS au LLM de "connaître" l'actualité.
On récupère des articles réels via Google News RSS (gratuit, illimité,
pas de clé API), et le LLM se contente ensuite de choisir/reformuler
à partir de ces données réelles, avec source et date citées.

Flux :
  1. Pour chaque catégorie d'intérêt active (table interests), on interroge
     le flux RSS correspondant.
  2. On parse les articles (titre, lien, source, date de publication).
  3. On filtre les articles déjà envoyés (news_sent_log) et les doublons.
  4. On stocke le résultat dans news_feed_cache pour que le scheduler
     puisse piocher dedans sans re-fetcher à chaque utilisateur.
"""

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


GOOGLE_NEWS_RSS_BASE = "https://news.google.com/rss/search"

# Mapping entre nos catégories internes (table interests.category)
# et les requêtes de recherche envoyées à Google News.
# A ajuster/enrichir au fil du temps selon les retours utilisateurs.
CATEGORY_QUERY_MAP = {
    "sport": "sport",
    "basketball": "basketball",
    "musique": "musique",
    "cinema": "cinéma",
    "jeux_video": "jeux vidéo",
    "technologie": "intelligence artificielle OR technologie",
    "lecture": "littérature OR livres",
    "voyage": "voyage",
    "cuisine": "gastronomie",
    "bien_etre": "bien-être OR santé mentale",
}


@dataclass
class NewsArticle:
    title: str
    source_name: str
    source_url: str
    published_at: datetime
    category: str


def fetch_news_for_category(category: str, lang: str = "fr", country: str = "FR", limit: int = 5):
    """
    Interroge le flux RSS Google News pour une catégorie donnée.
    Retourne une liste de NewsArticle (non filtrée, non dédupliquée).
    """
    query = CATEGORY_QUERY_MAP.get(category)
    if not query:
        return []

    params = {
        "q": query,
        "hl": lang,
        "gl": country,
        "ceid": f"{country}:{lang}",
    }
    url = f"{GOOGLE_NEWS_RSS_BASE}?{urllib.parse.urlencode(params)}"

    req = urllib.request.Request(url, headers={"User-Agent": "Pkapkato-NewsService/1.0"})
    with urllib.request.urlopen(req, timeout=10) as response:
        raw_xml = response.read()

    root = ET.fromstring(raw_xml)
    articles = []

    for item in root.findall(".//item")[:limit]:
        title = _safe_text(item, "title")
        link = _safe_text(item, "link")
        pub_date_raw = _safe_text(item, "pubDate")
        source_el = item.find("source")
        source_name = source_el.text if source_el is not None else "Source inconnue"

        try:
            published_at = parsedate_to_datetime(pub_date_raw) if pub_date_raw else datetime.now(timezone.utc)
        except (TypeError, ValueError):
            published_at = datetime.now(timezone.utc)

        if not title or not link:
            continue

        articles.append(
            NewsArticle(
                title=title.strip(),
                source_name=source_name.strip(),
                source_url=link.strip(),
                published_at=published_at,
                category=category,
            )
        )

    return articles


def _safe_text(item, tag):
    el = item.find(tag)
    return el.text if el is not None else None


def fetch_news_for_user_interests(interest_categories, max_articles_per_category=3):
    """
    Point d'entrée principal pour le scheduler quotidien.
    interest_categories : liste des catégories déclarées par l'utilisateur
                          (ex: ["basketball", "technologie"])
    Retourne une liste plate d'articles, triée par date de publication (plus récent d'abord).
    """
    all_articles = []
    for category in interest_categories:
        try:
            articles = fetch_news_for_category(category, limit=max_articles_per_category)
            all_articles.extend(articles)
        except Exception as e:
            # Ne jamais faire planter tout le job pour une seule catégorie en échec.
            print(f"[news_service] Erreur lors de la récupération pour '{category}': {e}")
            continue

    all_articles.sort(key=lambda a: a.published_at, reverse=True)
    return all_articles


def select_article_to_send(candidate_articles, already_sent_urls):
    """
    Sélectionne le premier article non déjà envoyé.
    already_sent_urls : ensemble des source_url déjà présentes dans news_sent_log
                        pour cet utilisateur (pour éviter les doublons).
    Retourne un NewsArticle ou None si rien de nouveau à proposer.
    """
    for article in candidate_articles:
        if article.source_url not in already_sent_urls:
            return article
    return None


if __name__ == "__main__":
    # Exemple d'utilisation manuelle pour tester le service.
    test_categories = ["technologie", "basketball"]
    articles = fetch_news_for_user_interests(test_categories)
    for a in articles[:5]:
        print(f"- [{a.category}] {a.title} ({a.source_name}, {a.published_at.date()})")
        print(f"  {a.source_url}")
