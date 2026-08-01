import os
from unittest.mock import MagicMock, patch

os.environ.pop("ANTHROPIC_API_KEY", None)

from fastapi.testclient import TestClient

import database
database.DATABASE_URL = "sqlite:///./pkapkato_doc_test.db"
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
database.engine = create_engine(database.DATABASE_URL, connect_args={"check_same_thread": False})
database.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=database.engine)
database.init_db()

import news_cache
news_cache.DB_PATH = "pkapkato_news_cache_doc_test.db"
news_cache.init_db()

from main import app

client = TestClient(app)

print("1. Création utilisateur...")
r = client.post("/users", json={"email": "doc@pkapkato.dev", "first_name": "Fatou"})
user_id = r.json()["id"]
print("   OK")

print("2. Upload d'un format non supporté (.docx) -> 415 attendu...")
r = client.post(
    f"/users/{user_id}/documents",
    data={"subject": "Histoire"},
    files={"file": ("cours.docx", b"contenu bidon", "application/octet-stream")},
)
print("   Status:", r.status_code, "-", r.json())
assert r.status_code == 415
print("   OK")

print("3. Upload d'un fichier .txt vide -> 422 attendu...")
r = client.post(
    f"/users/{user_id}/documents",
    data={"subject": "Histoire"},
    files={"file": ("vide.txt", b"   ", "text/plain")},
)
print("   Status:", r.status_code, "-", r.json())
assert r.status_code == 422
print("   OK")

print("4. Upload d'un .txt valide SANS clé API -> 503 attendu...")
content = b"La Revolution francaise a debute en 1789. Elle marque un tournant majeur."
r = client.post(
    f"/users/{user_id}/documents",
    data={"subject": "Histoire"},
    files={"file": ("cours.txt", content, "text/plain")},
)
print("   Status:", r.status_code, "-", r.json())
assert r.status_code == 503
print("   OK")

print("5. Upload d'un .txt valide avec l'API MOCKÉE...")
os.environ["ANTHROPIC_API_KEY"] = "fake-key-for-test"

fake_text_block = MagicMock()
fake_text_block.type = "text"
fake_text_block.text = "Résumé : la Révolution française débute en 1789, tournant historique majeur."

fake_response = MagicMock()
fake_response.content = [fake_text_block]

with patch("document_service.anthropic.Anthropic") as MockAnthropic:
    mock_client_instance = MagicMock()
    mock_client_instance.messages.create.return_value = fake_response
    MockAnthropic.return_value = mock_client_instance

    r = client.post(
        f"/users/{user_id}/documents",
        data={"subject": "Histoire"},
        files={"file": ("cours.txt", content, "text/plain")},
    )
    print("   Status:", r.status_code, "-", r.json())
    assert r.status_code == 200
    assert "1789" in r.json()["summary_text"]

    call_kwargs = mock_client_instance.messages.create.call_args.kwargs
    assert "Histoire" in call_kwargs["system"]
    assert "Revolution francaise" in call_kwargs["messages"][0]["content"]
    print("   OK, prompt de résumé correctement construit")

print("6. Liste des documents de l'utilisateur...")
r = client.get(f"/users/{user_id}/documents")
assert r.status_code == 200
assert len(r.json()) == 1
print("   OK,", len(r.json()), "document(s)")

print("\nTOUS LES TESTS DE DOCUMENTS PASSENT")
