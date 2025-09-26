import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Obtener la URL de la base de datos desde .env, con valor por defecto para desarrollo
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./users.db")

# Configurar connect_args solo si es SQLite
connect_args = {}
if "sqlite" in DATABASE_URL:
    connect_args = {"check_same_thread": False}

# Crear el motor de base de datos
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args
)

# Crear la fábrica de sesiones
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Clase base para los modelos
Base = declarative_base()