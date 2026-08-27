"""
Модуль для загрузки данных с API.
"""
import requests
import logging
import os
from app.config import Config

logger = logging.getLogger(__name__)

def download_workers_data():
    """
    Загружает CSV файл с данными сотрудников с API.
    """
    try:
        session = requests.Session()
        
        # Берём настройки из Config
        base_url = Config.API_BASE_URL
        login_url = f"{base_url}{Config.API_LOGIN_ENDPOINT}"
        csv_url = f"{base_url}{Config.API_EXPORT_ENDPOINT}"
        
        login_credentials = {
            'login': Config.API_LOGIN,
            'password': Config.API_PASSWORD
        }
        
        logger.info(f"Подключение к API: {base_url}")
        logger.info(f"Логин: {login_credentials['login']}")
        logger.info(f"URL логина: {login_url}")
        logger.info(f"URL выгрузки: {csv_url}")
        
        # Логин
        login_resp = session.post(login_url, data=login_credentials, timeout=60)
        login_resp.raise_for_status()
        
        if 'connect.sid' not in session.cookies:
            raise Exception('Не удалось получить сессию. Проверьте логин/пароль!')
        
        logger.info("Успешная авторизация")
        
        # Загрузка CSV
        csv_resp = session.get(csv_url, timeout=60)
        csv_resp.raise_for_status()
        
        # Убедимся, что папка data существует
        data_dir = os.path.dirname(Config.INPUT_CSV)
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir)
            logger.info(f"Папка {data_dir} создана")
        
        # Сохранение файла
        with open(Config.INPUT_CSV, 'wb') as f:
            f.write(csv_resp.content)
        
        file_size = os.path.getsize(Config.INPUT_CSV)
        logger.info(f"Файл успешно скачан и сохранен как {Config.INPUT_CSV} ({file_size} байт)")
        return True
        
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Ошибка подключения к серверу: {e}")
        raise
    except requests.exceptions.Timeout as e:
        logger.error(f"Таймаут при подключении к серверу: {e}")
        raise
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        raise