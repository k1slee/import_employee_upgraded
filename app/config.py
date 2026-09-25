import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '..', '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY не задан в переменных окружения!")
    
    # База данных
    SQLALCHEMY_DATABASE_URI = 'sqlite:////app/instance/app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # API Guard Plus
    API_BASE_URL = os.environ.get('API_BASE_URL')
    if not API_BASE_URL:
        raise ValueError("API_BASE_URL не задан в переменных окружения!")
    
    API_LOGIN_ENDPOINT = os.environ.get('API_LOGIN_ENDPOINT', '/login')
    API_EXPORT_ENDPOINT = os.environ.get('API_EXPORT_ENDPOINT', '/export/workers/csv')
    
    API_LOGIN = os.environ.get('API_LOGIN')
    if not API_LOGIN:
        raise ValueError("API_LOGIN не задан в переменных окружения!")
    
    API_PASSWORD = os.environ.get('API_PASSWORD')
    if not API_PASSWORD:
        raise ValueError("API_PASSWORD не задан в переменных окружения!")
    
    # Пути к файлам
    INPUT_CSV = os.environ.get('INPUT_CSV', 'data/workers-guard-plus.csv')
    OUTPUT_CSV = os.environ.get('OUTPUT_CSV', 'data/workers.csv')
    OUTPUT_JSON = os.environ.get('OUTPUT_JSON', 'data/workers.json')
    ACCEPTED_CSV = os.environ.get('ACCEPTED_CSV', 'data/accepted.csv')
    DUPLICATES_FILE = os.environ.get('DUPLICATES_FILE', 'data/duplicates.txt')
    EXCEL_FILE = os.environ.get('EXCEL_FILE', 'pass.xlsx')
    
    # Сеть
    NETWORK_PATH = os.environ.get('NETWORK_PATH', r'\\kiosk\Терминал 2022\card_reader\workers.json')
    ARCHIVE_DIR = os.environ.get('ARCHIVE_DIR', 'archive/')