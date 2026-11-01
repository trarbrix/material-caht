"""Material Chat FastAPI server with persistent message reactions.

This file can replace the existing main.py in material-caht. Install dependencies:
    pip install fastapi uvicorn sqlalchemy requests python-multipart

Set TELEGRAM_BOT_TOKEN in the environment. Do not publish your bot token in Git.
"""

import os
import re
import secrets
import shutil
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import requests
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import declarative_base, sessionmaker

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
UPLOADS = Path("uploads")
UPLOADS.mkdir(exist_ok=True)

SQLALCHEMY_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./material_chat.db")
connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    phone = Column(String, unique=True, index=True, nullable=True)
    tg_username = Column(String, unique=True, index=True)
    password = Column(String)


class MessageDB(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(String, index=True)
    sender = Column(String)
    text = Column(Text, nullable=True)
    media_url = Column(String, nullable=True)
    msg_type = Column(String)
    time = Column(String)


class ReactionDB(Base):
    __tablename__ = "reactions"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False, index=True)
    chat_id = Column(String, nullable=False, index=True)
    sender = Column(String(100), nullable=False)
    emoji = Column(String(32), nullable=False)
    created_at = Column(String(32), nullable=False, default=lambda: datetime.utcnow().isoformat())
    __table_args__ = (
        UniqueConstraint("message_id", "sender", "emoji", name="uq_reactions_message_sender_emoji"),
    )


# Existing users/messages are untouched; only the new reactions table is created.
Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/uploads", StaticFiles(directory=str(UPLOADS)), name="uploads")

tg_codes = {}


@app.get("/api/health")
def health():
    return {"ok": True}


class AuthData(BaseModel):
    username: str
    email: str = None
    phone: str = None
    tg_username: str
    password: str


class TGReq(BaseModel):
    tg_username: str


class VerifyReq(BaseModel):
    tg_username: str
    code: str


class MessageData(BaseModel):
    chat_id: str
    sender: str
    text: str = None
    media_url: str = None
    msg_type: str = "text"


class ReactionData(BaseModel):
    # The old Python server has integer message IDs; the browser may send a string.
    message_id: int | str
    chat_id: str = "global"
    sender: str
    emoji: str


def grouped_reactions(rows):
    """{message id as string: [{emoji, count, senders}]} for the frontend."""
    result = defaultdict(dict)
    for row in rows:
        key = str(row.message_id)
        group = result[key].setdefault(row.emoji, {"emoji": row.emoji, "count": 0, "senders": []})
        group["count"] += 1
        group["senders"].append(row.sender)
    return {message_id: list(groups.values()) for message_id, groups in result.items()}


def get_chat_id_by_username(username):
    if not BOT_TOKEN:
        return None
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates", timeout=10
        ).json()
        for update in reversed(response.get("result", [])):
            message = update.get("message") or {}
            sender = message.get("from", {})
            if sender.get("username", "").lower() == username.lower():
                return message.get("chat", {}).get("id")
    except (requests.RequestException, ValueError):
        pass
    return None


@app.post("/api/send_code")
def send_code(data: TGReq):
    tg_name = data.tg_username.replace("@", "").strip()
    if not BOT_TOKEN:
        return {"status": "error", "detail": "TELEGRAM_BOT_TOKEN не настроен"}
    chat_id = get_chat_id_by_username(tg_name)
    if not chat_id and tg_name.isdigit():
        chat_id = tg_name
    if not chat_id:
        return {"status": "error", "detail": "Нажми /start в боте"}

    code = str(secrets.randbelow(9000) + 1000)
    tg_codes[tg_name] = code
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": f"Твой код: {code}"},
            timeout=10,
        )
        if response.ok:
            return {"status": "ok"}
        return {"status": "error", "detail": "Telegram не принял сообщение"}
    except requests.RequestException:
        return {"status": "error", "detail": "Telegram недоступен"}


@app.post("/api/verify_code")
def verify_code(data: VerifyReq):
    tg_name = data.tg_username.replace("@", "").strip()
    if tg_codes.get(tg_name) == data.code:
        return {"status": "ok"}
    raise HTTPException(status_code=400, detail="Неверный код")


@app.post("/api/auth")
def auth(data: AuthData):
    db = SessionLocal()
    try:
        user = db.query(UserDB).filter(
            (UserDB.username == data.username) | (UserDB.tg_username == data.tg_username)
        ).first()
        if user:
            if user.password != data.password:
                raise HTTPException(status_code=400, detail="Неверный пароль")
            return {"status": "ok"}
        new_user = UserDB(
            username=data.username,
            email=data.email,
            phone=data.phone,
            tg_username=data.tg_username,
            password=data.password,
        )
        db.add(new_user)
        db.commit()
        return {"status": "ok"}
    finally:
        db.close()


@app.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    # Never use a client-supplied path as a filename on disk.
    filename = f"{int(time.time())}_{uuid4().hex}_{Path(file.filename or 'file').name}"
    location = UPLOADS / filename
    with location.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    base_url = str(request.base_url).rstrip("/")
    return {"url": f"{base_url}/uploads/{filename}"}


@app.get("/api/messages/{chat_id}")
def get_messages(chat_id: str):
    db = SessionLocal()
    try:
        msgs = db.query(MessageDB).filter(
            MessageDB.chat_id == chat_id
        ).order_by(MessageDB.id).all()
        ids = [m.id for m in msgs]
        reactions_by_message = {}
        if ids:
            rows = db.query(ReactionDB).filter(
                ReactionDB.message_id.in_(ids)
            ).order_by(ReactionDB.id).all()
            reactions_by_message = grouped_reactions(rows)
        return [
            {
                "id": m.id,
                "sender": m.sender,
                "text": m.text,
                "media_url": m.media_url,
                "type": m.msg_type,
                "time": m.time,
                "reactions": reactions_by_message.get(str(m.id), []),
            }
            for m in msgs
        ]
    finally:
        db.close()


@app.post("/api/messages")
def send_message(data: MessageData):
    db = SessionLocal()
    try:
        new_msg = MessageDB(
            chat_id=data.chat_id,
            sender=data.sender,
            text=data.text,
            media_url=data.media_url,
            msg_type=data.msg_type,
            time=time.strftime("%H:%M"),
        )
        db.add(new_msg)
        db.commit()
        return {"status": "ok"}
    finally:
        db.close()


@app.get("/api/reactions")
def get_reactions(chat_id: str = "global"):
    """Optional endpoint used by clients that load reactions separately."""
    db = SessionLocal()
    try:
        msgs = db.query(MessageDB.id).filter(MessageDB.chat_id == chat_id).all()
        ids = [m.id for m in msgs]
        if not ids:
            return {}
        rows = db.query(ReactionDB).filter(
            ReactionDB.message_id.in_(ids)
        ).order_by(ReactionDB.id).all()
        return grouped_reactions(rows)
    finally:
        db.close()


@app.post("/api/reactions")
def toggle_reaction(data: ReactionData):
    """Set or remove one emoji from this sender on this message."""
    try:
        message_id = int(data.message_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Неверный message_id")

    sender = data.sender.strip().lstrip("@").lower()
    chat_id = data.chat_id.strip()
    emoji = data.emoji.strip()
    if not sender or len(sender) > 100 or not chat_id or len(chat_id) > 100:
        raise HTTPException(status_code=400, detail="Проверь sender и chat_id")
    if (
        not emoji
        or len(emoji) > 8
        or any(char.isspace() for char in emoji)
        or any(char in emoji for char in "<>\"'\\")
    ):
        raise HTTPException(status_code=400, detail="Неверная реакция")

    db = SessionLocal()
    try:
        message = db.query(MessageDB).filter(
            MessageDB.id == message_id, MessageDB.chat_id == chat_id
        ).first()
        if not message:
            raise HTTPException(status_code=404, detail="Сообщение не найдено в этом чате")

        previous = db.query(ReactionDB).filter(
            ReactionDB.message_id == message_id,
            ReactionDB.sender == sender,
            ReactionDB.emoji == emoji,
        ).first()
        if previous:
            db.delete(previous)
            added = False
        else:
            db.add(ReactionDB(
                message_id=message_id,
                chat_id=chat_id,
                sender=sender,
                emoji=emoji,
            ))
            added = True
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            # Two requests from the same user at once: the unique constraint
            # prevents a duplicate reaction even if both saw it as absent.
            raise HTTPException(status_code=409, detail="Реакция уже существует")

        rows = db.query(ReactionDB).filter(
            ReactionDB.message_id == message_id
        ).order_by(ReactionDB.id).all()
        return {
            "ok": True,
            "added": added,
            "reactions": grouped_reactions(rows).get(str(message_id), []),
        }
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
