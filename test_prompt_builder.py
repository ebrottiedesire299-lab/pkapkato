from datetime import datetime, timedelta, timezone

from database import init_db, SessionLocal
from models import User, Task, Interest, ConversationMemory
from prompt_builder import build_system_prompt

init_db()
db = SessionLocal()

# Nettoyage si le test a déjà tourné avant
existing = db.query(User).filter(User.email == "test@pkapkato.dev").first()
if existing:
    db.delete(existing)
    db.commit()

user = User(
    email="test@pkapkato.dev",
    first_name="Aïcha",
    ia_name="Nova",
    ia_tone="motivant",
)
db.add(user)
db.commit()
db.refresh(user)

now = datetime.now(timezone.utc)
db.add_all([
    Task(user_id=user.id, title="Examen d'économie", type="examen",
         subject="Économie", due_date=now + timedelta(days=10), status="à faire"),
    Task(user_id=user.id, title="Devoir de statistiques", type="devoir",
         subject="Statistiques", due_date=now + timedelta(days=2), status="à faire"),
    Task(user_id=user.id, title="Projet terminé", type="projet",
         subject="Informatique", due_date=now - timedelta(days=1), status="terminé"),
])
db.add(Interest(user_id=user.id, category="sport", label="basketball", weight=5))
db.add(Interest(user_id=user.id, category="technologie", label="développement web", weight=4))
db.add(ConversationMemory(
    user_id=user.id,
    summary="Aïcha révise pour ses partiels, a mentionné être stressée par l'examen d'économie."
))
db.commit()
db.refresh(user)

news_example = {
    "title": "Une nouvelle avancée en intelligence artificielle annoncée",
    "source_name": "Le Monde",
    "published_at": "2026-07-10",
}

prompt = build_system_prompt(user, news_article=news_example)
print(prompt)
print("\n--- Longueur du prompt:", len(prompt), "caractères ---")

assert user.ia_name in prompt
assert "Aïcha" in prompt
assert "basketball" in prompt
assert "Examen d'économie" in prompt
assert "Projet terminé" not in prompt  # tâche terminée, ne doit pas apparaître
assert "Le Monde" in prompt
print("\nTOUS LES TESTS PASSENT")

db.close()
