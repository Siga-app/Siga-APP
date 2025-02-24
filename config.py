import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'sua-chave-secreta-aqui'
    # Usar caminho absoluto do volume persistente no Render
    SQLALCHEMY_DATABASE_URI = 'sqlite:////app/instance/new.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
