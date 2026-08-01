import os
from unittest.mock import MagicMock, patch

os.environ.pop("ANTHROPIC_API_KEY", None)

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import database
database.DATABASE_URL = "sqlite:///./pkapkato_chat_test.db"
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
database.engine = create_engine(database.DATABASE_URL, connect_args={"check_same_thread": False})
database.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=database.engine)
database.init_db()

import news_cache
news_cache.DB_PATH = "pkapkato_news_cache_chat_test.db"
news_cache.init_db()

from main import app

client = TestClient(app)

print("1. Création utilisateur...")
r = client.post("/users", json={"email": "chat@pkapkato.dev", "first_name": "Karim"})
user_id = r.json()["id"]
print("   OK")

print("2. Chat SANS clé API -> doit renvoyer 503 proprement...")
r = client.post(f"/users/{user_id}/chat", json={"message": "Salut !"})
print("   Status:", r.status_code, "-", r.json())
assert r.status_code == 503
print("   OK, erreur gérée proprement")

print("3. Chat avec l'API Claude MOCKÉE (validation de la logique)...")

fake_text_block = MagicMock()
fake_text_block.type = "text"
fake_text_block.text = "Salut Karim ! Comment puis-je t'aider aujourd'hui ?"

fake_response = MagicMock()
fake_response.content = [fake_text_block]

os.environ["ANTHROPIC_API_KEY"] = "fake-key-for-test"

with patch("chat_service.anthropic.Anthropic") as MockAnthropic:
    mock_client_instance = MagicMock()
    mock_client_instance.messages.create.return_value = fake_response
    MockAnthropic.return_value = mock_client_instance

    r = client.post(f"/users/{user_id}/chat", json={"message": "Salut !"})
    print("   Status:", r.status_code, "-", r.json())
    assert r.status_code == 200
    assert "Karim" in r.json()["reply"]

    # Vérifie que le system prompt a bien été transmis à l'appel API
    call_kwargs = mock_client_instance.messages.create.call_args.kwargs
    assert "Karim" in call_kwargs["system"]
    assert call_kwargs["messages"][0]["content"] == "Salut !"
    print("   OK, system prompt correctement transmis à l'API")

print("4. Vérification que la mémoire de conversation a été mise à jour...")
r = client.get(f"/users/{user_id}/system-prompt")
prompt = r.json()["system_prompt"]
assert "Salut !" in prompt
print("   OK, la mémoire inclut le message précédent")

print("\nTOUS LES TESTS DU CHAT PASSENT")
