# database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

# ✅ FORZAR SQLITE (ignorar cualquier DATABASE_URL externa)
DATABASE_URL = "sqlite:///./users.db"

# Configurar connect_args para SQLite
connect_args = {"check_same_thread": False}

# Crear el motor de base de datos
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    poolclass=None  # Evitar problemas de pool en SQLite
)

# Crear la fábrica de sesiones
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Clase base para los modelos
Base = declarative_base()