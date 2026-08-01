import os

# Base de test isolée pour ne pas polluer la vraie DB de dev
os.environ["PKAPKATO_TEST"] = "1"

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import database
database.DATABASE_URL = "sqlite:///./pkapkato_test.db"
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
database.engine = create_engine(database.DATABASE_URL, connect_args={"check_same_thread": False})
database.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=database.engine)

database.init_db()

import news_cache
news_cache.DB_PATH = "pkapkato_news_cache_test.db"
news_cache.init_db()

from main import app


client = TestClient(app)


print("1. Vérification santé de l'API...")
r = client.get("/health")
assert r.status_code == 200
print("   OK")

print("2. Création d'un utilisateur (onboarding)...")
r = client.post("/users", json={
    "email": "aicha@pkapkato.dev",
    "first_name": "Aïcha",
    "ia_name": "Nova",
    "ia_tone": "motivant",
    "interests": [
        {"category": "sport", "label": "basketball", "weight": 5},
        {"category": "technologie", "label": "développement web", "weight": 4},
    ],
})
print("   Status:", r.status_code, "-", r.json())
assert r.status_code == 200
user = r.json()
user_id = user["id"]
assert user["ia_name"] == "Nova"

print("3. Rejet d'un doublon d'email...")
r = client.post("/users", json={"email": "aicha@pkapkato.dev", "first_name": "Aïcha"})
assert r.status_code == 400
print("   OK, doublon bien rejeté")

print("4. Ajout d'une tâche urgente...")
due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
r = client.post(f"/users/{user_id}/tasks", json={
    "title": "Devoir de statistiques",
    "type": "devoir",
    "subject": "Statistiques",
    "due_date": due,
})
assert r.status_code == 200
print("   Tâche créée:", r.json()["title"])

print("5. Liste des tâches...")
r = client.get(f"/users/{user_id}/tasks")
assert r.status_code == 200
assert len(r.json()) == 1
print("   OK,", len(r.json()), "tâche(s)")

print("6. Génération du system prompt...")
r = client.get(f"/users/{user_id}/system-prompt")
assert r.status_code == 200
prompt = r.json()["system_prompt"]
assert "Nova" in prompt and "Aïcha" in prompt and "Statistiques" in prompt
print("   OK, prompt généré (", len(prompt), "caractères )")

print("7. Déclenchement du scheduler (doit détecter l'échéance urgente)...")
r = client.post("/scheduler/run")
assert r.status_code == 200
result = r.json()
print("   Résultat:", result)
assert result["notifications_sent"] == 1
assert result["users_checked"] == 1

print("8. Utilisateur introuvable -> 404 attendu...")
r = client.get("/users/inexistant/tasks")
assert r.status_code == 404
print("   OK")

print("\nTOUS LES TESTS DE BOUT EN BOUT PASSENT")
