import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'sua-chave-secreta-aqui'
    # Usar caminho absoluto para o volume persistente no Render.
    # Certifique-se de que o volume esteja montado em /app/instance e que o arquivo seja new.db.
    SQLALCHEMY_DATABASE_URI = 'sqlite:////app/instance/new.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
