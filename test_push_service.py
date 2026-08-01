import os
from datetime import datetime, timedelta, timezone

os.environ.pop("FIREBASE_CREDENTIALS_PATH", None)

from fastapi.testclient import TestClient

import database
database.DATABASE_URL = "sqlite:///./pkapkato_push_test.db"
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
database.engine = create_engine(database.DATABASE_URL, connect_args={"check_same_thread": False})
database.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=database.engine)
database.init_db()

import news_cache
news_cache.DB_PATH = "pkapkato_news_cache_push_test.db"
news_cache.init_db()

from main import app

client = TestClient(app)

print("1. Création utilisateur...")
r = client.post("/users", json={"email": "push@pkapkato.dev", "first_name": "Yao"})
user_id = r.json()["id"]
print("   OK")

print("2. Enregistrement du device_token...")
r = client.put(f"/users/{user_id}/device-token", json={"device_token": "fake-fcm-token-123"})
assert r.status_code == 200
print("   OK")

print("3. Utilisateur inexistant -> 404...")
r = client.put("/users/inexistant/device-token", json={"device_token": "x"})
assert r.status_code == 404
print("   OK")

print("4. Ajout d'une tâche urgente + déclenchement scheduler "
      "(Firebase NON configuré -> doit rester en mode dégradé, sans planter)...")
due = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
client.post(f"/users/{user_id}/tasks", json={
    "title": "Examen de chimie", "type": "examen", "subject": "Chimie", "due_date": due,
})
r = client.post("/scheduler/run")
print("   Status:", r.status_code, "-", r.json())
assert r.status_code == 200
assert r.json()["notifications_sent"] == 1
print("   OK, le scheduler fonctionne malgré l'absence de Firebase configuré")

print("\nTOUS LES TESTS PUSH/DEVICE-TOKEN PASSENT")
