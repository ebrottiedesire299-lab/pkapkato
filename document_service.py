"""
Service de résumé de documents Pkapkato.

Flux :
  1. Extraire le texte brut du fichier uploadé (.txt ou .pdf pour le MVP).
  2. Envoyer ce texte à Gemini avec un prompt de résumé dédié
     (distinct du system prompt conversationnel, car la tâche est différente :
     ici on veut un résumé structuré, pas une réponse conversationnelle).
  3. Retourner le résumé pour stockage dans Document.summary_text.

Utilise Gemini (comme chat_service.py) car Google propose un vrai palier
gratuit et permanent (sans carte bancaire), suffisant pour un MVP en phase de test.
Nécessite la variable d'environnement GOOGLE_API_KEY en production
(clé obtenue gratuitement sur https://aistudio.google.com).

Limites volontaires du MVP :
  - Formats supportés : .txt, .pdf uniquement (pas de .docx/.pptx pour l'instant).
  - Pas d'OCR : un PDF scanné (image) ne donnera pas de texte exploitable.
  - Taille de texte envoyée au LLM plafonnée pour maîtriser le coût par appel.
"""

import io
import os

from google import genai
from pypdf import PdfReader

MODEL_NAME = "gemini-3-flash-preview"

# Sécurité coût/contexte : on tronque le texte source avant de l'envoyer au LLM.
MAX_SOURCE_CHARS = 15000

SUPPORTED_EXTENSIONS = {".txt", ".pdf"}


class UnsupportedFileType(Exception):
    pass


class EmptyDocumentError(Exception):
    pass


def _get_client():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY n'est pas définie. "
            "Créez une clé gratuite sur https://aistudio.google.com et "
            "ajoutez-la à votre environnement avant de lancer le serveur."
        )
    return genai.Client(api_key=api_key)


def extract_text(filename: str, file_bytes: bytes) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileType(
            f"Format '{ext}' non supporté pour le moment. "
            f"Formats acceptés : {', '.join(sorted(SUPPORTED_EXTENSIONS))}."
        )

    if ext == ".txt":
        text = file_bytes.decode("utf-8", errors="ignore")
    else:  # .pdf
        reader = PdfReader(io.BytesIO(file_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)

    text = text.strip()
    if not text:
        raise EmptyDocumentError(
            "Aucun texte exploitable trouvé dans ce document "
            "(peut-être un PDF scanné sans OCR)."
        )
    return text


def summarize_document(subject: str, text: str) -> str:
    """
    Résume un document de cours. Utilise un prompt dédié, indépendant
    du system prompt conversationnel de l'utilisateur : c'est une tâche
    ponctuelle de traitement de texte, pas un échange avec la mini IA.
    """
    truncated_text = text[:MAX_SOURCE_CHARS]

    system_prompt = (
        "Tu es un assistant qui aide des étudiants à résumer leurs documents de cours. "
        f"Le document concerne la matière : {subject}. "
        "Produis un résumé clair et structuré (points clés, définitions importantes, "
        "à retenir pour un examen), en français, sans reformuler l'intégralité du texte. "
        "Le résumé doit faire environ 150 à 250 mots."
    )

    client = _get_client()
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=truncated_text,
        config={"system_instruction": system_prompt},
    )

    return response.text
