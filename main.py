from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import declarative_base, sessionmaker
import time, random, requests

# --- ТОКЕН БОТА ---
BOT_TOKEN = "9229804048:AAECzn-YF2dcTb4tUyP5pbl8rk8sP8n7PFY"

# --- БАЗА ДАННЫХ ---
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

tg_codes = {}

# --- МОДЕЛИ ДАННЫХ ---
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

class ResetReq(BaseModel):
    tg_username: str
    code: str
    new_password: str

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

@app.post("/api/reset_password")
def reset_password(data: ResetReq):
    db = SessionLocal()
    try:
        tg_name = data.tg_username.replace("@", "").strip()
        if tg_codes.get(tg_name) != data.code: raise HTTPException(status_code=400, detail="Неверный код")
        user = db.query(UserDB).filter(UserDB.tg_username == tg_name).first()
        if not user: raise HTTPException(status_code=404, detail="Пользователь не найден")
        user.password = data.new_password
        db.commit()
        return {"status": "ok"}
    finally:
        db.close()

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
