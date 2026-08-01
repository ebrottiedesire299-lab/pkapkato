"""
Modèles de données Pkapkato.
SQLite pour le développement, migrable vers PostgreSQL en production
(SQLAlchemy abstrait la différence, aucun changement de code métier requis).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Boolean, Text, Integer
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def gen_id():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_id)
    email = Column(String, unique=True, nullable=False)
    first_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=now)

    ia_name = Column(String, default="Nova")
    ia_tone = Column(String, default="motivant")  # calme, motivant, humoristique, professionnel
    ia_avatar_url = Column(String, nullable=True)
    timezone = Column(String, default="Africa/Abidjan")
    device_token = Column(String, nullable=True)  # token FCM de l'appareil mobile


    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan")
    interests = relationship("Interest", back_populates="user", cascade="all, delete-orphan")
    memory = relationship("ConversationMemory", back_populates="user", uselist=False,
                           cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    type = Column(String, nullable=False)  # devoir, examen, projet
    subject = Column(String, nullable=False)
    due_date = Column(DateTime, nullable=False)
    status = Column(String, default="à faire")  # à faire, en cours, terminé
    created_at = Column(DateTime, default=now)

    user = relationship("User", back_populates="tasks")


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    subject = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    summary_text = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=now)

    user = relationship("User", back_populates="documents")


class Interest(Base):
    __tablename__ = "interests"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    category = Column(String, nullable=False)  # sport, technologie, musique, etc.
    label = Column(String, nullable=False)     # ex: "basketball"
    weight = Column(Integer, default=3)
    added_at = Column(DateTime, default=now)

    user = relationship("User", back_populates="interests")


class ConversationMemory(Base):
    __tablename__ = "conversation_memory"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    summary = Column(Text, default="")
    last_updated = Column(DateTime, default=now)

    user = relationship("User", back_populates="memory")


class NotificationLog(Base):
    __tablename__ = "notifications_log"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    message_sent = Column(Text, nullable=False)
    reason = Column(String, nullable=False)  # echeance, document, actualite, encouragement
    sent_at = Column(DateTime, default=now)
    opened = Column(Boolean, default=False)
