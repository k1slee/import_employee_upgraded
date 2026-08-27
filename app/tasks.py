import logging
import threading
import os
import shutil
import json
import openpyxl
from datetime import datetime, timedelta
from app.config import Config
from app.models import Employee, JobStatus
from app import db
from downloader import download_workers_data
from csv_processor import process_workers_data
from validator import archive_files
from app.utils import copy_to_network

logger = logging.getLogger(__name__)

# Глобальный флаг для отслеживания выполнения
is_running = False

def get_active_employees_from_db():
    """Возвращает список активных сотрудников из БД."""
    from app import create_app
    app = create_app()
    with app.app_context():
        employees = Employee.query.filter_by(is_active=True).all()
        return [{'full_name': emp.full_name} for emp in employees]

def run_processing():
    """Основная функция обработки, запускаемая в фоне."""
    global is_running
    if is_running:
        logger.warning("Обработка уже запущена")
        return
    is_running = True
    try:
        logger.info("=== НАЧАЛО ОБРАБОТКИ ===")
        # 1. Скачивание с API
        download_workers_data()
        # 2. Активные сотрудники из БД
        active_employees = get_active_employees_from_db()
        # 3. Обработка CSV
        json_data = process_workers_data(
            input_file=Config.INPUT_CSV,
            output_file=Config.OUTPUT_CSV,
            json_file=Config.OUTPUT_JSON,
            accepted_file=Config.ACCEPTED_CSV,
            duplicates_file=Config.DUPLICATES_FILE,
            active_employees=active_employees
        )
        # 4. Архивирование
        archive_files()
        # 5. Проверка с БД
        check_with_db(Config.OUTPUT_JSON)
        # 6. Копирование на сеть (заглушка)
        copy_to_network_stub()
        logger.info("=== ОБРАБОТКА УСПЕШНО ЗАВЕРШЕНА ===")
    except Exception as e:
        logger.error(f"Ошибка в фоновой задаче: {e}", exc_info=True)
    finally:
        is_running = False

def start_processing_async():
    """Запускает обработку в отдельном потоке."""
    thread = threading.Thread(target=run_processing)
    thread.daemon = True
    thread.start()

# ---------- Функции для импорта Excel ----------
def excel_date_to_datetime(excel_date):
    if isinstance(excel_date, datetime):
        return excel_date
    elif isinstance(excel_date, (int, float)):
        return datetime(1899, 12, 30) + timedelta(days=excel_date)
    elif isinstance(excel_date, str):
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(excel_date.strip(), fmt)
            except ValueError:
                continue
    return None

def is_worker_active(hire_raw, fire_raw):
    today = datetime.now().date()
    hire_date = excel_date_to_datetime(hire_raw)
    fire_date = excel_date_to_datetime(fire_raw)
    if not hire_date:
        return False
    if hire_date.date() > today:
        return False
    if fire_date and fire_date.date() < today:
        return False
    return True

def import_excel_to_db(excel_path):
    """Импортирует данные из Excel в БД (полная замена данных)."""
    from app import create_app
    app = create_app()
    with app.app_context():
        wb = openpyxl.load_workbook(excel_path, data_only=True)
        ws = wb.active

        # Полностью очищаем таблицу
        try:
            deleted = Employee.query.delete()
            db.session.commit()
            logger.info(f"Удалено {deleted} старых записей.")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Ошибка при очистке таблицы: {e}")
            raise

        count = 0
        for row in range(2, ws.max_row + 1):
            personal_number = ws.cell(row=row, column=2).value
            full_name = ws.cell(row=row, column=3).value
            if not full_name:
                break
            hire_raw = ws.cell(row=row, column=4).value
            fire_raw = ws.cell(row=row, column=5).value

            employee = Employee(
                personal_number=str(personal_number).strip() if personal_number else None,
                full_name=str(full_name).strip(),
                hire_date=excel_date_to_datetime(hire_raw),
                fire_date=excel_date_to_datetime(fire_raw),
                is_active=is_worker_active(hire_raw, fire_raw)
            )
            db.session.add(employee)
            count += 1

        db.session.commit()
        logger.info(f"Импортировано {count} сотрудников в БД.")
        return count

# ---------- Проверка с БД ----------
def check_with_db(json_path: str):
    """
    Проверяет данные workers.json по активным сотрудникам из БД.
    Сохраняет отчёт о расхождениях (по matchcode и по имени).
    """
    from app import create_app
    app = create_app()
    with app.app_context():
        # Загружаем JSON
        with open(json_path, 'r', encoding='utf-8') as f:
            workers_data = json.load(f)

        # Получаем активных сотрудников из БД
        active_employees = Employee.query.filter_by(is_active=True).all()
        db_names = {emp.full_name.strip().lower() for emp in active_employees}
        db_codes = {emp.personal_number for emp in active_employees if emp.personal_number}

        missing_by_name = {}
        missing_by_code = {}

        for card, data in workers_data.items():
            name = data.get('name', '').strip().lower()
            code = data.get('matchcode', '').strip()
            if name and name not in db_names:
                missing_by_name[card] = data
            if code and code not in db_codes:
                missing_by_code[card] = data

        # Сохраняем отчёты
        if missing_by_name:
            with open('data/missing_from_db_by_name.json', 'w', encoding='utf-8') as f:
                json.dump(missing_by_name, f, ensure_ascii=False, indent=2)
            logger.info(f"Найдено {len(missing_by_name)} сотрудников, отсутствующих в БД по имени")
        else:
            logger.info("Все сотрудники присутствуют в БД по имени")

        if missing_by_code:
            with open('data/missing_from_db_by_code.json', 'w', encoding='utf-8') as f:
                json.dump(missing_by_code, f, ensure_ascii=False, indent=2)
            logger.info(f"Найдено {len(missing_by_code)} сотрудников, отсутствующих в БД по табельному номеру")
        else:
            logger.info("Все сотрудники присутствуют в БД по табельному номеру")

def update_status(current_step: str, step_name: str, progress: int, message: str):
    """Обновляет статус выполнения в БД."""
    from app import create_app
    app = create_app()
    with app.app_context():
        status = JobStatus.query.first()
        if not status:
            status = JobStatus()
            db.session.add(status)
        status.current_step = current_step
        status.step_name = step_name
        status.progress = progress
        status.message = message
        status.last_updated = datetime.utcnow()
        db.session.commit()

def get_status():
    """Возвращает текущий статус."""
    from app import create_app
    app = create_app()
    with app.app_context():
        status = JobStatus.query.first()
        if not status:
            return {'current_step': 'idle', 'step_name': 'Ожидание', 'progress': 0, 'message': 'Готов к работе'}
        return {
            'current_step': status.current_step,
            'step_name': status.step_name,
            'progress': status.progress,
            'message': status.message
        }
def start_full_process_async():
    """Запускает полный процесс в отдельном потоке."""
    thread = threading.Thread(target=run_processing_all)
    thread.daemon = True
    thread.start()
# ---------- Заглушка для копирования на сеть ----------
def copy_to_network_stub():
    """Заглушка вместо копирования на сеть (сохраняет в local_stub)."""
    logger.info("Копирование на сеть: временно отключено (заглушка).")
    stub_dir = 'network_stub'
    os.makedirs(stub_dir, exist_ok=True)
    shutil.copy2(Config.OUTPUT_JSON, os.path.join(stub_dir, 'workers.json'))
    logger.info(f"Файл скопирован в {stub_dir}/workers.json (заглушка)")

# ---------- Пошаговые функции для тестирования ----------
def step1_download():
    update_status('downloading', 'Скачивание данных с Guard Plus', 10, 'Подключение к серверу...')
    logger.info("Шаг 1: Загрузка данных...")
    download_workers_data()
    update_status('downloading', 'Скачивание данных с Guard Plus', 100, 'Файл скачан успешно')
    logger.info("Шаг 1: Загрузка завершена.")
    return True

def step2_process():
    from app import create_app
    app = create_app()
    update_status('processing', 'Обработка данных', 20, 'Получение активных сотрудников из БД...')
    with app.app_context():
        logger.info("Шаг 2: Обработка данных...")
        active_employees = get_active_employees_from_db()
        if not active_employees:
            logger.warning("Нет активных сотрудников в БД.")
        if not os.path.exists(Config.INPUT_CSV):
            raise FileNotFoundError(f"Исходный CSV не найден: {Config.INPUT_CSV}.")
        update_status('processing', 'Обработка данных', 40, 'Фильтрация и преобразование данных...')
        json_data = process_workers_data(
            input_file=Config.INPUT_CSV,
            output_file=Config.OUTPUT_CSV,
            json_file=Config.OUTPUT_JSON,
            accepted_file=Config.ACCEPTED_CSV,
            duplicates_file=Config.DUPLICATES_FILE,
            active_employees=active_employees
        )
        update_status('processing', 'Обработка данных', 100, 'Файлы созданы: workers.csv, workers.json')
        logger.info("Шаг 2: Обработка завершена.")
        return json_data

def step3_finalize():
    update_status('finalizing', 'Финализация', 20, 'Архивирование файлов...')
    logger.info("Шаг 3: Финализация...")
    archive_files()
    update_status('finalizing', 'Финализация', 50, 'Проверка данных с БД...')
    check_with_db(Config.OUTPUT_JSON)
    update_status('finalizing', 'Финализация', 80, 'Копирование на сеть (заглушка)...')
    copy_to_network_stub()
    update_status('finalizing', 'Финализация', 100, 'Финализация завершена')
    logger.info("Шаг 3: Финализация завершена.")
    return True

def run_processing_all():
    """Запуск всех шагов последовательно с обновлением статуса."""
    global is_running
    if is_running:
        logger.warning("Обработка уже запущена")
        return
    is_running = True
    try:
        # Шаг 1
        update_status('downloading', 'Шаг 1/3: Скачивание данных с Guard Plus', 10, 'Подключение к серверу...')
        logger.info("Шаг 1: Загрузка данных...")
        download_workers_data()
        update_status('downloading', 'Шаг 1/3: Скачивание данных с Guard Plus', 100, 'Файл скачан успешно')
        
        # Шаг 2
        from app import create_app
        app = create_app()
        update_status('processing', 'Шаг 2/3: Обработка данных', 20, 'Получение активных сотрудников из БД...')
        with app.app_context():
            logger.info("Шаг 2: Обработка данных...")
            active_employees = get_active_employees_from_db()
            if not active_employees:
                logger.warning("Нет активных сотрудников в БД.")
            if not os.path.exists(Config.INPUT_CSV):
                raise FileNotFoundError(f"Исходный CSV не найден: {Config.INPUT_CSV}.")
            update_status('processing', 'Шаг 2/3: Обработка данных', 40, 'Фильтрация и преобразование данных...')
            json_data = process_workers_data(
                input_file=Config.INPUT_CSV,
                output_file=Config.OUTPUT_CSV,
                json_file=Config.OUTPUT_JSON,
                accepted_file=Config.ACCEPTED_CSV,
                duplicates_file=Config.DUPLICATES_FILE,
                active_employees=active_employees
            )
            update_status('processing', 'Шаг 2/3: Обработка данных', 100, 'Файлы созданы: workers.csv, workers.json')
            logger.info("Шаг 2: Обработка завершена.")
        
        # Шаг 3
        update_status('finalizing', 'Шаг 3/3: Финализация', 20, 'Архивирование файлов...')
        logger.info("Шаг 3: Финализация...")
        archive_files()
        update_status('finalizing', 'Шаг 3/3: Финализация', 50, 'Проверка данных с БД...')
        check_with_db(Config.OUTPUT_JSON)
        update_status('finalizing', 'Шаг 3/3: Финализация', 80, 'Копирование на сеть (заглушка)...')
        copy_to_network_stub()
        update_status('finalizing', 'Шаг 3/3: Финализация', 100, 'Финализация завершена')
        logger.info("Шаг 3: Финализация завершена.")
        
        # Все шаги выполнены
        update_status('done', 'Все шаги выполнены', 100, 'Обработка успешно завершена!')
        logger.info("=== ОБРАБОТКА УСПЕШНО ЗАВЕРШЕНА ===")
        
    except Exception as e:
        error_msg = str(e)
        update_status('error', 'Ошибка выполнения', 0, f'Ошибка: {error_msg[:100]}')
        logger.error(f"Ошибка в полном процессе: {e}", exc_info=True)
    finally:
        is_running = False

# Обёртки для асинхронного запуска каждого шага
def start_step1_async():
    thread = threading.Thread(target=step1_download)
    thread.daemon = True
    thread.start()

def start_step2_async():
    thread = threading.Thread(target=step2_process)
    thread.daemon = True
    thread.start()

def start_step3_async():
    thread = threading.Thread(target=step3_finalize)
    thread.daemon = True
    thread.start()