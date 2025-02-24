import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'sua-chave-secreta-aqui'
    # Use um nome diferente para forçar a criação de um novo DB
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///new.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
