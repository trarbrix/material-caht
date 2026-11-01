from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import declarative_base, sessionmaker
import time, random, requests, os, shutil

# Скопируй сюда строку BOT_TOKEN из своего существующего server/main.py.
BOT_TOKEN = "ВСТАВЬ_СТАРЫЙ_ТОКЕН"
os.makedirs("uploads", exist_ok=True)

SQLALCHEMY_DATABASE_URL = "sqlite:///./material_chat.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
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

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

tg_codes = {}

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

def get_chat_id_by_username(username):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    try:
        response = requests.get(url).json()
        if "result" in response:
            for update in response["result"]:
                if "message" in update and "from" in update["message"]:
                    sender = update["message"]["from"]
                    if sender.get("username", "").lower() == username.lower():
                        return update["message"]["chat"]["id"]
    except: pass
    return None

@app.post("/api/send_code")
def send_code(data: TGReq):
    tg_name = data.tg_username.replace("@", "").strip()
    chat_id = get_chat_id_by_username(tg_name)
    if not chat_id and tg_name.isdigit(): chat_id = tg_name
    if not chat_id: return {"status": "error", "detail": "Нажми /start в боте", "debug_code": "Нет доступа"}
        
    code = str(random.randint(1000, 9999))
    tg_codes[tg_name] = code
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": f"Твой код: {code}"}
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200: return {"status": "ok"}
        return {"status": "error", "debug_code": code}
    except: return {"status": "error", "debug_code": code}

@app.post("/api/verify_code")
def verify_code(data: VerifyReq):
    tg_name = data.tg_username.replace("@", "").strip()
    if tg_codes.get(tg_name) == data.code: return {"status": "ok"}
    raise HTTPException(status_code=400, detail="Неверный код")

@app.post("/api/auth")
def auth(data: AuthData):
    db = SessionLocal()
    try:
        user = db.query(UserDB).filter((UserDB.username == data.username) | (UserDB.tg_username == data.tg_username)).first()
        if user:
            if user.password != data.password: raise HTTPException(status_code=400, detail="Неверный пароль")
            return {"status": "ok"}
        else:
            new_user = UserDB(username=data.username, email=data.email, phone=data.phone, tg_username=data.tg_username, password=data.password)
            db.add(new_user)
            db.commit()
            return {"status": "ok"}
    finally:
        db.close()

@app.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    filename = f"{int(time.time())}_{file.filename}"
    file_location = f"uploads/{filename}"
    
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # ДИНАМИЧЕСКАЯ ССЫЛКА (сама подставит правильный URL)
    base_url = str(request.base_url).rstrip("/")
    return {"url": f"{base_url}/{file_location}"}

@app.get("/api/messages/{chat_id}")
def get_messages(chat_id: str):
    db = SessionLocal()
    try:
        msgs = db.query(MessageDB).filter(MessageDB.chat_id == chat_id).order_by(MessageDB.id).all()
        return [{"id": m.id, "sender": m.sender, "text": m.text, "media_url": m.media_url, "type": m.msg_type, "time": m.time} for m in msgs]
    finally:
        db.close()

@app.post("/api/messages")
def send_message(data: MessageData):
    db = SessionLocal()
    try:
        new_msg = MessageDB(chat_id=data.chat_id, sender=data.sender, text=data.text, media_url=data.media_url, msg_type=data.msg_type, time=time.strftime("%H:%M"))
        db.add(new_msg)
        db.commit()
        return {"status": "ok"}
    finally:
        db.close()


# Общие профили
"""Optional profile API for Material Chat's existing FastAPI backend.

Call install_profile_api(app, SessionLocal, engine, UserDB, tg_codes) after
creating the existing app, database models and tg_codes dictionary.
"""
import base64
import binascii
import hmac
import re
import secrets
import threading
import time

from fastapi import Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Text, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import declarative_base

ProfileBase = declarative_base()


class ChatProfile(ProfileBase):
    __tablename__ = "chat_profiles"
    user_id = Column(Integer, primary_key=True)
    nickname = Column(String(40), nullable=False, default="")
    handle = Column(String(32), unique=True, nullable=True)
    avatar = Column(Text, nullable=False, default="")


class ProfileLogin(BaseModel):
    identifier: str
    password: str


class ProfileRegistration(BaseModel):
    tg_username: str
    password: str
    code: str


class ProfileChanges(BaseModel):
    nickname: str = ""
    handle: str = ""
    avatar: str = ""


def validate_avatar(value):
    if not value:
        return ""
    if len(value) > 280_000:
        raise HTTPException(status_code=413, detail="Avatar is too large")
    match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)", value)
    if not match:
        raise HTTPException(status_code=400, detail="Unsupported avatar format")
    try:
        content = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Invalid avatar")
    kind = match.group(1)
    valid = (kind == "png" and content.startswith(b"\x89PNG\r\n\x1a\n")) or \
        (kind == "jpeg" and content.startswith(b"\xff\xd8\xff")) or \
        (kind == "webp" and content.startswith(b"RIFF") and content[8:12] == b"WEBP")
    if not valid or len(content) > 200_000:
        raise HTTPException(status_code=400, detail="Invalid or oversized avatar")
    return value


def install_profile_api(app, SessionLocal, engine, UserDB, tg_codes):
    ProfileBase.metadata.create_all(bind=engine)
    # Sessions expire on server restart. No password is retained in a session.
    sessions = {}
    session_lock = threading.Lock()
    lifetime = 12 * 60 * 60

    def issue_token(user_id):
        token = secrets.token_urlsafe(32)
        now = time.time()
        with session_lock:
            for old, (_, expires) in list(sessions.items()):
                if expires <= now:
                    sessions.pop(old, None)
            sessions[token] = (user_id, now + lifetime)
        return token

    def user_id_for(authorization):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Sign in again")
        token = authorization[7:]
        with session_lock:
            item = sessions.get(token)
            if item and item[1] <= time.time():
                sessions.pop(token, None)
                item = None
        if not item:
            raise HTTPException(status_code=401, detail="Session expired")
        return item[0]

    def serialize(profile):
        return {"nickname": profile.nickname or "", "handle": profile.handle or "", "avatar": profile.avatar or ""} if profile else {"nickname": "", "handle": "", "avatar": ""}

    @app.post("/api/profile/register")
    def register_with_code(data: ProfileRegistration):
        tg = data.tg_username.strip().lstrip("@")
        if not tg or not data.password or not data.code:
            raise HTTPException(status_code=400, detail="Missing fields")
        code = tg_codes.get(tg)
        if not code or not hmac.compare_digest(str(code).encode("utf-8"), str(data.code).strip().encode("utf-8")):
            raise HTTPException(status_code=400, detail="Invalid code")
        db = SessionLocal()
        try:
            if db.query(UserDB).filter(func.lower(UserDB.tg_username) == tg.lower()).first():
                raise HTTPException(status_code=409, detail="Account already exists")
            # The identifier is internal; a public handle can be chosen later.
            user = UserDB(username="u_" + secrets.token_hex(16), tg_username=tg, password=data.password)
            db.add(user)
            db.commit()
            db.refresh(user)
            tg_codes.pop(tg, None)
            return {"token": issue_token(user.id), "identifier": tg}
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Account already exists")
        finally:
            db.close()

    @app.post("/api/profile/session")
    def profile_session(data: ProfileLogin):
        identifier = data.identifier.strip().lstrip("@")
        db = SessionLocal()
        try:
            users = db.query(UserDB).filter((func.lower(UserDB.tg_username) == identifier.lower()) | (UserDB.username == identifier)).all()
            # Existing server stores plaintext passwords; compare without logging or retaining them.
            matches = [item for item in users if item.password and hmac.compare_digest(item.password.encode('utf-8'), data.password.encode('utf-8'))]
            # The old backend has two identifiers; never guess between accounts.
            if len(matches) != 1:
                raise HTTPException(status_code=401, detail="Incorrect or ambiguous credentials")
            return {"token": issue_token(matches[0].id)}
        finally:
            db.close()

    @app.get("/api/profile/me")
    def get_my_profile(authorization: str = Header(default="")):
        user_id = user_id_for(authorization)
        db = SessionLocal()
        try:
            return serialize(db.query(ChatProfile).filter(ChatProfile.user_id == user_id).first())
        finally:
            db.close()

    @app.put("/api/profile/me")
    def update_my_profile(data: ProfileChanges, authorization: str = Header(default="")):
        user_id = user_id_for(authorization)
        nickname = data.nickname.strip()
        handle = data.handle.strip().lstrip("@").lower()
        if len(nickname) > 40:
            raise HTTPException(status_code=400, detail="Nickname is too long")
        if handle and not re.fullmatch(r"[a-z][a-z0-9_]{2,31}", handle):
            raise HTTPException(status_code=400, detail="Invalid handle")
        avatar = validate_avatar(data.avatar)
        db = SessionLocal()
        try:
            profile = db.query(ChatProfile).filter(ChatProfile.user_id == user_id).first()
            if not profile:
                profile = ChatProfile(user_id=user_id)
                db.add(profile)
            profile.nickname = nickname
            profile.handle = handle or None
            profile.avatar = avatar
            db.commit()
            return serialize(profile)
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Handle already taken")
        finally:
            db.close()

    @app.get("/api/profile/public/{sender}")
    def public_profile(sender: str):
        if len(sender) > 100:
            raise HTTPException(status_code=400, detail="Invalid sender")
        db = SessionLocal()
        try:
            users = db.query(UserDB).filter((UserDB.username == sender) | (func.lower(UserDB.tg_username) == sender.lower())).all()
            # Legacy sender strings can refer to more than one account; do not misattribute them.
            return serialize(db.query(ChatProfile).filter(ChatProfile.user_id == users[0].id).first()) if len(users) == 1 else serialize(None)
        finally:
            db.close()

    # Allows optional extensions to verify the same short-lived sessions.
    return user_id_for


# Общие реакции
"""Optional shared-reaction endpoints for the legacy Material Chat server.

Install the profile API first and pass its returned token verifier here. The
legacy message API still needs its own access-control and privacy fixes.
"""
from collections import defaultdict
import unicodedata

from fastapi import Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, UniqueConstraint
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import declarative_base

ReactionBase = declarative_base()


class ChatReaction(ReactionBase):
    __tablename__ = "chat_reactions"
    id = Column(Integer, primary_key=True)
    chat_id = Column(String(200), nullable=False, index=True)
    message_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False)
    emoji = Column(String(64), nullable=False)
    __table_args__ = (UniqueConstraint("message_id", "user_id", "emoji", name="uq_chat_reaction"),)


class ReactionRequest(BaseModel):
    chat_id: str
    message_id: str
    emoji: str


def install_reaction_api(app, SessionLocal, engine, MessageDB, user_id_for):
    if not callable(user_id_for):
        raise ValueError("A profile session verifier is required")
    ReactionBase.metadata.create_all(bind=engine)

    def grouped(rows, viewer):
        result = defaultdict(lambda: defaultdict(lambda: {"count": 0, "reacted": False}))
        for row in rows:
            item = result[str(row.message_id)][row.emoji]
            item["count"] += 1
            if viewer is not None and row.user_id == viewer:
                item["reacted"] = True
        return {mid: [{"emoji": emoji, **data} for emoji, data in groups.items()] for mid, groups in result.items()}

    @app.get('/api/reactions')
    def get_reactions(chat_id: str, authorization: str = Header(default="")):
        if not chat_id or len(chat_id) > 200:
            raise HTTPException(status_code=400, detail="Invalid chat")
        viewer = None
        if authorization:
            try:
                viewer = user_id_for(authorization)
            except HTTPException as exc:
                if exc.status_code != 401:
                    raise
        db = SessionLocal()
        try:
            rows = db.query(ChatReaction).filter(ChatReaction.chat_id == chat_id).all()
            return {"messages": grouped(rows, viewer)}
        finally:
            db.close()

    @app.post('/api/reactions')
    def toggle_reaction(data: ReactionRequest, authorization: str = Header(default="")):
        viewer = user_id_for(authorization)
        emoji = data.emoji.strip()
        if not data.chat_id or len(data.chat_id) > 200 or not data.message_id.isascii() or not data.message_id.isdigit() or len(data.message_id) > 18:
            raise HTTPException(status_code=400, detail="Invalid message")
        if not emoji or len(emoji) > 32 or any(unicodedata.category(c) == 'Cc' for c in emoji):
            raise HTTPException(status_code=400, detail="Invalid reaction")
        msg_id = int(data.message_id)
        db = SessionLocal()
        try:
            message = db.query(MessageDB).filter(MessageDB.id == msg_id, MessageDB.chat_id == data.chat_id).first()
            if not message:
                raise HTTPException(status_code=404, detail="Message not found")
            existing = db.query(ChatReaction).filter_by(message_id=msg_id, user_id=viewer, emoji=emoji).first()
            if existing:
                db.delete(existing)
            else:
                db.add(ChatReaction(chat_id=data.chat_id, message_id=msg_id, user_id=viewer, emoji=emoji))
            db.commit()
            rows = db.query(ChatReaction).filter_by(chat_id=data.chat_id, message_id=msg_id).all()
            return {"reactions": grouped(rows, viewer).get(str(msg_id), [])}
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Reaction changed; try again")
        finally:
            db.close()


# Подключаем оба дополнения один раз.
verify_profile_session = install_profile_api(app, SessionLocal, engine, UserDB, tg_codes)
install_reaction_api(app, SessionLocal, engine, MessageDB, verify_profile_session)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
