"""
API Pkapkato — MVP backend.

Endpoints principaux :
- POST /users                  -> onboarding (créer un utilisateur + centres d'intérêt)
- POST /users/{id}/tasks       -> ajouter une tâche (devoir/examen/projet)
- GET  /users/{id}/tasks       -> lister les tâches
- GET  /users/{id}/system-prompt -> générer le system prompt actuel (pour debug / intégration LLM)
- POST /scheduler/run          -> déclenche manuellement le job quotidien (pour tests ; en prod, un cron l'appelle)
"""

from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import init_db, get_db
from models import User, Task, Interest, Document
from prompt_builder import build_system_prompt
import scheduler as scheduler_module
import news_cache
import chat_service
import document_service

app = FastAPI(title="Pkapkato API", version="0.1.0")



@app.on_event("startup")
def on_startup():
    init_db()
    news_cache.init_db()


# ---------- Schémas Pydantic ----------

class InterestIn(BaseModel):
    category: str
    label: str
    weight: int = 3


class UserCreate(BaseModel):
    email: str
    first_name: str
    ia_name: str = "Nova"
    ia_tone: str = "motivant"
    timezone: str = "Africa/Abidjan"
    interests: List[InterestIn] = []


class UserOut(BaseModel):
    id: str
    email: str
    first_name: str
    ia_name: str
    ia_tone: str

    class Config:
        from_attributes = True


class ChatIn(BaseModel):
    message: str


class ChatOut(BaseModel):
    reply: str


class TaskCreate(BaseModel):
    title: str
    type: str  # devoir, examen, projet
    subject: str
    due_date: datetime


class TaskOut(BaseModel):
    id: str
    title: str
    type: str
    subject: str
    due_date: datetime
    status: str

    class Config:
        from_attributes = True


# ---------- Endpoints ----------

@app.post("/users", response_model=UserOut)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Un utilisateur avec cet email existe déjà.")

    user = User(
        email=payload.email,
        first_name=payload.first_name,
        ia_name=payload.ia_name,
        ia_tone=payload.ia_tone,
        timezone=payload.timezone,
    )
    db.add(user)
    db.flush()  # pour obtenir user.id avant les interests

    for interest in payload.interests:
        db.add(Interest(user_id=user.id, category=interest.category,
                         label=interest.label, weight=interest.weight))

    db.commit()
    db.refresh(user)
    return user


@app.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    return user


@app.post("/users/{user_id}/tasks", response_model=TaskOut)
def create_task(user_id: str, payload: TaskCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    task = Task(user_id=user_id, title=payload.title, type=payload.type,
                subject=payload.subject, due_date=payload.due_date)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@app.get("/users/{user_id}/tasks", response_model=List[TaskOut])
def list_tasks(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    return user.tasks


@app.get("/users/{user_id}/system-prompt")
def get_system_prompt(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    return {"system_prompt": build_system_prompt(user)}


class DocumentOut(BaseModel):
    id: str
    subject: str
    original_filename: str
    summary_text: Optional[str] = None

    class Config:
        from_attributes = True


@app.post("/users/{user_id}/chat", response_model=ChatOut)
def chat(user_id: str, payload: ChatIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    try:
        reply = chat_service.send_message(db, user, payload.message)
    except RuntimeError as e:
        # Cas où ANTHROPIC_API_KEY n'est pas configurée sur le serveur.
        raise HTTPException(status_code=503, detail=str(e))

    return {"reply": reply}


class DeviceTokenIn(BaseModel):
    device_token: str


@app.post("/users/{user_id}/documents", response_model=DocumentOut)

async def upload_document(
    user_id: str,
    subject: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    file_bytes = await file.read()

    try:
        text = document_service.extract_text(file.filename, file_bytes)
    except document_service.UnsupportedFileType as e:
        raise HTTPException(status_code=415, detail=str(e))
    except document_service.EmptyDocumentError as e:
        raise HTTPException(status_code=422, detail=str(e))

    try:
        summary = document_service.summarize_document(subject, text)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    document = Document(
        user_id=user_id,
        subject=subject,
        original_filename=file.filename,
        summary_text=summary,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


@app.get("/users/{user_id}/documents", response_model=List[DocumentOut])
def list_documents(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    return user.documents


@app.post("/scheduler/run")
def run_scheduler(db: Session = Depends(get_db)):
    """
    Déclenche manuellement le job quotidien pour tous les utilisateurs.
    En production, cet endpoint n'est pas exposé publiquement : un cron
    (ou un scheduler côté infra) l'appelle en interne (ou appelle directement
    la fonction Python équivalente sans passer par HTTP).
    """
    users = db.query(User).all()
    sent_count = scheduler_module.run_daily_job_for_all_users(db, users)
    return {"notifications_sent": sent_count, "users_checked": len(users)}


@app.put("/users/{user_id}/device-token")
def register_device_token(user_id: str, payload: DeviceTokenIn, db: Session = Depends(get_db)):
    """
    Appelé par l'app mobile après obtention du token FCM (au démarrage,
    ou quand Firebase le renouvelle). Sans ce token, aucune notification
    push ne peut être envoyée à cet utilisateur.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")

    user.device_token = payload.device_token
    db.commit()
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}
