from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware  # <-- ¡IMPORTANTE!
from sqlalchemy.orm import Session
from passlib.hash import bcrypt
from sqlalchemy import text
from app.database import SessionLocal, engine
from app.models.user import User
from app.push import init_firebase, enviar_push
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
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
# max_age: la sesión expira a los 14 días en vez de ser eterna.
# https_only: la cookie solo viaja por HTTPS (Render sirve HTTPS).
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=14 * 24 * 60 * 60,  # 14 días
    https_only=True,
    same_site="lax",
)

# Luego el CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Crear tablas (solo desarrollo):]
try:
    User.metadata.create_all(bind=engine)
    logger.info("✅ Tablas creadas correctamente")
except Exception as e:
    logger.error(f"❌ Error al crear tablas: {e}")
    raise


def _asegurar_columnas():
    """Migración ligera: añade columnas nuevas si la tabla ya existía.

    create_all() no altera tablas existentes, así que añadimos a mano las
    columnas de notificaciones. Si ya existen, el ALTER falla y se ignora.
    Funciona tanto en SQLite (local) como en PostgreSQL (Render).
    """
    columnas = {
        "fcm_token": "VARCHAR(255)",
        "ultima_alerta": "VARCHAR(64)",
    }
    for nombre, tipo in columnas.items():
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {nombre} {tipo}"))
            logger.info(f"🔧 Columna '{nombre}' añadida")
        except Exception:
            pass  # la columna ya existe


_asegurar_columnas()

# Inicializar Firebase (si hay credenciales). Si no, los push quedan desactivados
# pero la API sigue funcionando con normalidad.
init_firebase()

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
    # Optional[...] para que un null explícito (que envían algunos clientes)
    # no provoque un error 422 en Pydantic v2.
    ip: Optional[str] = None
    puerto: Optional[str] = None
    url_publica: Optional[str] = None

class TokenRequest(BaseModel):
    token: str

class AlertaRequest(BaseModel):
    camara: int = 0

TIPOS_VALIDOS = {"cliente", "server"}


@app.post("/register")
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    # NO registrar el cuerpo completo: contiene la contraseña en texto plano.
    logger.info(f"📌 /register usuario={request.username} tipo={request.tipo}")

    if request.tipo not in TIPOS_VALIDOS:
        raise HTTPException(status_code=400, detail="Tipo de usuario no válido")

    try:
        if db.query(User).filter(User.username == request.username).first():
            logger.warning("⚠️ Usuario ya registrado")
            raise HTTPException(status_code=400, detail="Usuario ya registrado")

        if db.query(User).filter(User.email == request.email).first():
            logger.warning("⚠️ Correo ya registrado")
            raise HTTPException(status_code=400, detail="Correo ya registrado")

        new_user = User(
            username=request.username,
            email=request.email,
            hashed_password=bcrypt.hash(request.password),
            tipo=request.tipo
        )
        db.add(new_user)
        db.commit()

        logger.info("🎉 Registro exitoso")
        return {"message": "Registro exitoso"}

    except HTTPException:
        # Errores esperados (usuario/correo duplicado, tipo inválido): re-lanzar tal cual.
        raise
    except Exception as e:
        # Error real de BD u otro: deshacer la transacción y devolver 500 limpio.
        db.rollback()
        logger.error(f"💥 ERROR en /register: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno al registrar")

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

@app.post("/registrar-token")
def registrar_token(data: TokenRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """La app móvil registra aquí su token de Firebase (FCM) tras iniciar sesión."""
    current_user.fcm_token = data.token
    db.commit()
    logger.info(f"📲 Token FCM registrado para {current_user.username}")
    return {"ok": True}


@app.post("/alerta")
def alerta(data: AlertaRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """El servidor de cámara avisa de que ha detectado una persona.

    Se notifica por push al cliente emparejado (mismo nombre base sin '_server').
    """
    if current_user.tipo != "server":
        raise HTTPException(status_code=403, detail="Solo un servidor puede enviar alertas")

    # Cliente emparejado: 'rodri_server' -> 'rodri'
    nombre_base = current_user.username
    if nombre_base.endswith("_server"):
        nombre_base = nombre_base[: -len("_server")]

    cliente = db.query(User).filter(
        User.username == nombre_base,
        User.tipo == "cliente"
    ).first()

    # Guardar marca de tiempo de la última alerta en el servidor
    current_user.ultima_alerta = datetime.utcnow().isoformat()
    db.commit()

    push_enviado = False
    if cliente and cliente.fcm_token:
        push_enviado = enviar_push(
            cliente.fcm_token,
            "DetectorCam",
            "🚨 Se ha detectado una persona en tu cámara",
            {"tipo": "persona_detectada", "camara": data.camara},
        )
    else:
        logger.warning(f"Sin token FCM para el cliente '{nombre_base}'; no se envía push")

    return {"ok": True, "push_enviado": push_enviado}


@app.get("/ping")
def ping():
    return {"status": "OK"}