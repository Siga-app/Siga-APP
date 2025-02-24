import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'sua-chave-secreta-aqui'
    # O banco será criado no volume persistente montado em /app/instance
    SQLALCHEMY_DATABASE_URI = 'sqlite:////app/instance/new.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
