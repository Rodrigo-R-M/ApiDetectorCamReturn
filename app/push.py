# app/push.py - Envío de notificaciones push con Firebase Cloud Messaging (FCM)
#
# Credenciales (en este orden):
#   1. FIREBASE_CREDENTIALS_JSON  -> contenido JSON completo (ideal para Render)
#   2. FIREBASE_CREDENTIALS       -> ruta a un archivo .json
#   3. <Proyecto API>/firebase-service-account.json  (desarrollo local)
import os
import json
import logging

logger = logging.getLogger(__name__)

# Ruta por defecto del archivo de credenciales en desarrollo local
_DEFAULT_CRED_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "firebase-service-account.json",
)

_initialized = False


def _load_credentials():
    """Devuelve un objeto credentials.Certificate o None si no hay credenciales."""
    from firebase_admin import credentials

    inline = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if inline:
        try:
            return credentials.Certificate(json.loads(inline))
        except Exception as e:
            logger.error(f"FIREBASE_CREDENTIALS_JSON inválido: {e}")
            return None

    path = os.getenv("FIREBASE_CREDENTIALS", _DEFAULT_CRED_PATH)
    if os.path.exists(path):
        return credentials.Certificate(path)

    return None


def init_firebase() -> bool:
    """Inicializa el SDK de Firebase Admin una sola vez. Devuelve True si está listo."""
    global _initialized
    if _initialized:
        return True

    try:
        import firebase_admin
    except ImportError:
        logger.warning("firebase-admin no instalado: las notificaciones push están desactivadas")
        return False

    cred = _load_credentials()
    if cred is None:
        logger.warning(
            "Firebase no configurado (sin credenciales): las notificaciones push están desactivadas"
        )
        return False

    try:
        firebase_admin.initialize_app(cred)
        _initialized = True
        logger.info("🔥 Firebase Admin inicializado")
        return True
    except ValueError:
        # Ya estaba inicializado en este proceso
        _initialized = True
        return True
    except Exception as e:
        logger.error(f"Error al inicializar Firebase: {e}")
        return False


def enviar_push(token: str, titulo: str, cuerpo: str, data: dict | None = None) -> bool:
    """Envía una notificación push a un dispositivo. Devuelve True si se envió."""
    if not token:
        return False
    if not init_firebase():
        return False

    from firebase_admin import messaging

    mensaje = messaging.Message(
        notification=messaging.Notification(title=titulo, body=cuerpo),
        token=token,
        data={k: str(v) for k, v in (data or {}).items()},
        android=messaging.AndroidConfig(priority="high"),
    )
    try:
        messaging.send(mensaje)
        logger.info("📲 Push enviado correctamente")
        return True
    except Exception as e:
        logger.error(f"Error al enviar push: {e}")
        return False
