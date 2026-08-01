"""
Service de chat Pkapkato.

Relie le system prompt dynamique (prompt_builder) � l'API Google Gemini,
et met � jour la m�moire de conversation apr�s chaque �change.

Utilise Gemini plut�t que Claude car Google propose un vrai palier gratuit
et permanent (sans carte bancaire), suffisant pour un MVP en phase de test.
N�cessite la variable d'environnement GOOGLE_API_KEY en production
(cl� obtenue gratuitement sur https://aistudio.google.com).
"""

import os

from google import genai
from sqlalchemy.orm import Session

from models import ConversationMemory
from prompt_builder import build_system_prompt

MODEL_NAME = "gemini-3-flash-preview"

MEMORY_SUMMARY_MAX_CHARS = 1500


def _get_client():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY n'est pas d�finie. "
            "Cr�ez une cl� gratuite sur https://aistudio.google.com et "
            "ajoutez-la � votre environnement avant de lancer le serveur."
        )
    return genai.Client(api_key=api_key)


def send_message(db: Session, user, user_message: str, news_article: dict = None) -> str:
    system_prompt = build_system_prompt(user, news_article=news_article)
    client = _get_client()

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=user_message,
        config={"system_instruction": system_prompt},
    )

    assistant_reply = response.text

    _update_memory(db, user, user_message, assistant_reply)
    return assistant_reply


def _update_memory(db: Session, user, user_message: str, assistant_reply: str):
    memory = user.memory
    if memory is None:
        memory = ConversationMemory(user_id=user.id, summary="")
        db.add(memory)

    new_fragment = f" {user.first_name} a dit : � {user_message[:200]} �."
    updated_summary = (memory.summary or "") + new_fragment

    if len(updated_summary) > MEMORY_SUMMARY_MAX_CHARS:
        updated_summary = updated_summary[-MEMORY_SUMMARY_MAX_CHARS:]

    memory.summary = updated_summary.strip()
    db.commit()
