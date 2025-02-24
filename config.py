import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'sua-chave-secreta-aqui'
    # Ajuste para usar o arquivo new.db na pasta persistente /app/instance
    SQLALCHEMY_DATABASE_URI = 'sqlite:////app/instance/new.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
