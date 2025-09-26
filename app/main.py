from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware  # <-- ¡IMPORTANTE!
from sqlalchemy.orm import Session
from passlib.hash import bcrypt
from app.database import SessionLocal, engine
from app.models.user import User
from pydantic import BaseModel
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Iniciando aplicación...")
app = FastAPI()

SECRET_KEY = os.getenv("SECRET_KEY", "fallback_inseguro_solo_dev")

# ✅ Agregar SessionMiddleware ANTES de otros middlewares (recomendado)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# Luego el CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Crear tablas (solo desarrollo)
try:
    User.metadata.create_all(bind=engine)
    logger.info("✅ Tablas creadas correctamente")
except Exception as e:
    logger.error(f"❌ Error al crear tablas: {e}")
    raise

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    tipo: str

class LoginRequest(BaseModel):
    username: str
    password: str

class CamaraEstadoRequest(BaseModel):
    estado: bool
    ip: str = None
    puerto: str = None
    url_publica: str = None

@app.post("/register")
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    logger.info("📌 Entrando a /register")
    logger.info(f"📌 Datos recibidos: {request.dict()}")

    try:
        logger.info("🔍 Verificando si el usuario ya existe...")
        if db.query(User).filter(User.username == request.username).first():
            logger.warning("⚠️ Usuario ya registrado")
            raise HTTPException(status_code=400, detail="Usuario ya registrado")

        logger.info("🔍 Verificando si el correo ya existe...")
        if db.query(User).filter(User.email == request.email).first():
            logger.warning("⚠️ Correo ya registrado")
            raise HTTPException(status_code=400, detail="Correo ya registrado")

        logger.info("🆕 Creando nuevo usuario...")
        new_user = User(
            username=request.username,
            email=request.email,
            hashed_password=bcrypt.hash(request.password),
            tipo=request.tipo
        )

        logger.info("💾 Añadiendo usuario a la sesión...")
        db.add(new_user)

        logger.info("✅ Haciendo commit...")
        db.commit()

        logger.info("🎉 Registro exitoso")
        return {"message": "Registro exitoso"}

    except Exception as e:
        logger.error(f"💥 ERROR en /register: {e}")
        logger.error("Traceback:", exc_info=True)
        raise

@app.post("/login")
def login(request_data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == request_data.username).first()
    if not db_user or not bcrypt.verify(request_data.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    request.session["user_id"] = db_user.id
    db_user.sesion_activa = True
    db.commit()
    return {"message": "Inicio de sesión exitoso", "tipo": db_user.tipo}

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return db_user

@app.get("/check-auth")
def check_auth(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    response = {
        "status": "ok",
        "user": current_user.username,
        "tipo": current_user.tipo,
        "camara_activa": current_user.servidor_camara,
        "camara_ip": current_user.camara_ip,
        "camara_puerto": current_user.camara_puerto,
        "url_publica": current_user.url_publica  # ← Añade esta línea
    }

    # Si el usuario es CLIENTE, buscar un servidor conectado
    if current_user.tipo == "cliente":
        servidor_activo = db.query(User).filter(
            User.tipo == "server",
            User.sesion_activa == True,
            User.servidor_camara == True,
            User.camara_ip.isnot(None),
            User.camara_puerto.isnot(None)
        ).first()
        if servidor_activo:
            response["ip_servidor"] = servidor_activo.camara_ip
            response["puerto_servidor"] = servidor_activo.camara_puerto
            response["url_publica_servidor"] = servidor_activo.url_publica
            response["servidor_usuario"] = servidor_activo.username
        else:
            response["ip_servidor"] = None
            response["puerto_servidor"] = None
            response["url_publica_servidor"] = None
            response["servidor_usuario"] = None

    return response

@app.post("/estado-camara")
def actualizar_estado_camara(data: CamaraEstadoRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if data.estado and (not data.ip or not data.puerto):
        raise HTTPException(status_code=400, detail="IP y puerto son obligatorios cuando la cámara está activa")

    current_user.servidor_camara = data.estado
    current_user.camara_ip = data.ip if data.estado else None
    current_user.camara_puerto = data.puerto if data.estado else None
    current_user.url_publica = data.url_publica if data.estado else None
    db.commit()
    return {"estado": current_user.servidor_camara}

@app.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if user_id:
        db_user = db.query(User).filter(User.id == user_id).first()
        if db_user:
            db_user.sesion_activa = False
            db.commit()
    request.session.clear()
    return {"message": "Sesión cerrada"}

@app.get("/ping")
def ping():
    return {"status": "OK"}