# models.py
from sqlalchemy import Column, Integer, String, Boolean
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)  # bcrypt genera ~60 chars, pero damos margen
    tipo = Column(String(20), nullable=False)              # "cliente", "server"
    sesion_activa = Column(Boolean, default=False)
    servidor_camara = Column(Boolean, default=False)
    camara_ip = Column(String(45), nullable=True)          # IPv6: hasta 45 caracteres
    camara_puerto = Column(String(5), nullable=True)       # puertos: 0-65535 → 5 dígitos máx.