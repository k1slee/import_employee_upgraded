"""
Модуль для обработки CSV файлов и преобразования данных.
"""
import csv
import json
from typing import Dict, List, Set, Tuple
import logging
from app.config import Config

# Настройки из конфига
INPUT_COLUMNS_MAPPING = {
    'Personal number': 'personal_number',
    'Last name': 'last_name',
    'First name': 'first_name',
    'Middle name': 'middle_name',
    'Department': 'department',
    'Card': 'card',
}
OUTPUT_COLUMNS = [
    'personal_number', 'last_name', 'first_name', 'middle_name',
    'department', 'card_track_two', 'country', 'nick_name'
]
EXCLUDED_DEPARTMENTS = ['Уволенные', 'Заблокированные']
SPECIAL_DEPARTMENT = 'Принятые'
INVALID_PERSONAL_NUMBERS = ['0000', '00000']

logger = logging.getLogger(__name__)

def normalize_name(name: str) -> str:
    """Нормализует имя для сравнения."""
    if not name:
        return ''
    return ' '.join(str(name).split()).lower()

def process_card_number(card_raw: str) -> Tuple[str, str]:
    """
    Обрабатывает номер карты, преобразуя формат 'XXX,YYYYY'.
    Возвращает (card_track_one, card_track_two).
    """
    card_clean = card_raw.replace('[', '').replace(']', '').replace('(', '').replace(')', '')
    
    # Проверяем формат 'XXX,YYYYY'
    if (isinstance(card_clean, str) and 
        len(card_clean.split(",")) == 2 and
        card_clean.split(",")[0].isdigit() and
        card_clean.split(",")[1].isdigit()):
        
        part1, part2 = card_clean.split(",")
        card_track_two = part1 + part2
        
        try:
            p1, p2 = int(part1), int(part2)
            card_track_one = str(p1 * 65536 + p2).zfill(10)
        except Exception:
            card_track_one = card_clean
            logger.warning(f"Ошибка при обработке карты: {card_raw}")
    else:
        card_track_two = card_clean
        card_track_one = card_clean
    
    return card_track_one, card_track_two

def should_skip_row(row: Dict, active_names: Set[str]) -> bool:
    """
    Определяет, нужно ли пропустить строку.
    """
    personal_number = row.get('Personal number', '').strip()
    department = row.get('Department', '').strip()
    card_clean = row.get('Card', '').replace('[', '').replace(']', '').replace('(', '').replace(')', '')
    
    # Формируем ФИО для проверки
    fio = (
        row.get('Last name', '').strip(),
        row.get('First name', '').strip(),
        row.get('Middle name', '').strip(),
    )
    fio_str = ' '.join(fio).strip()
    fio_norm = normalize_name(fio_str)
    
    # Специальная обработка для департамента "Принятые"
    if department == SPECIAL_DEPARTMENT:
        return False  # Не пропускаем, обрабатывается отдельно
    
    # Проверка на активность
    if fio_norm not in active_names:
        logger.info(f"Пропущен (неактивен): {fio_str} / Личный № {personal_number}")
        return True
    
    # Общие условия пропуска
    conditions = [
        not card_clean.strip(),
        department in EXCLUDED_DEPARTMENTS,
        (card_clean.strip() and not personal_number),
        personal_number in INVALID_PERSONAL_NUMBERS
    ]
    
    return any(conditions)

def process_workers_data(
    input_file: str,
    output_file: str,
    json_file: str,
    accepted_file: str,
    duplicates_file: str,
    active_employees: List[Dict]
) -> Dict:
    """
    Основная функция обработки CSV данных.
    """
    # Подготавливаем множество активных имен
    active_names = {normalize_name(emp.get('full_name', '')) for emp in active_employees}
    
    duplicates: Set[Tuple] = set()
    seen_fio: Set[Tuple] = set()
    json_dict = {}
    
    with open(input_file, 'r', encoding='utf-8', newline='') as infile, \
         open(output_file, 'w', encoding='windows-1251', newline='') as outfile, \
         open(accepted_file, 'w', encoding='windows-1251', newline='') as acceptedfile:
        
        reader = csv.DictReader(infile, delimiter=',')
        writer = csv.DictWriter(outfile, fieldnames=OUTPUT_COLUMNS, delimiter=';')
        accepted_writer = csv.DictWriter(acceptedfile, fieldnames=OUTPUT_COLUMNS, delimiter=';')
        
        writer.writeheader()
        accepted_writer.writeheader()
        
        for row in reader:
            department = row.get('Department', '').strip()
            personal_number = row.get('Personal number', '').strip()
            
            # Отдельная обработка для "Принятые"
            if department == SPECIAL_DEPARTMENT:
                process_accepted_row(row, accepted_writer)
                continue
            
            # Проверка на пропуск
            if should_skip_row(row, active_names):
                continue
            
            # Обработка карты
            card_raw = row.get('Card', '')
            card_track_one, card_track_two = process_card_number(card_raw)
            
            # Проверка дубликатов по ФИО
            fio = (
                row.get('Last name', '').strip(),
                row.get('First name', '').strip(),
                row.get('Middle name', '').strip(),
            )
            
            if fio in seen_fio:
                duplicates.add(fio)
            else:
                seen_fio.add(fio)
            
            # Формируем выходную строку
            out_row = create_output_row(row, card_track_two, personal_number)
            writer.writerow(out_row)
            
            # Добавляем в JSON словарь
            json_dict[card_track_one] = {
                "name": f"{row.get('Last name', '').strip()} "
                       f"{row.get('First name', '').strip()} "
                       f"{row.get('Middle name', '').strip()}",
                "matchcode": personal_number
            }
    
    # Сохраняем дубликаты
    if duplicates:
        save_duplicates(duplicates, duplicates_file)
    
    # Сохраняем JSON
    save_json(json_dict, json_file)
    
    logger.info(f"CSV файл записан: {output_file}")
    logger.info(f"JSON файл создан: {json_file}")
    logger.info(f"Принятые сотрудники сохранены в: {accepted_file}")
    
    return json_dict

def process_accepted_row(row: Dict, writer):
    """Обрабатывает строку с департаментом 'Принятые'."""
    card_raw = row.get('Card', '')
    card_clean = card_raw.replace('[', '').replace(']', '').replace('(', '').replace(')', '')
    
    out_row = {}
    for in_col, out_col in INPUT_COLUMNS_MAPPING.items():
        out_row[out_col] = row.get(in_col, '')
    
    out_row['card_track_two'] = card_clean
    out_row['country'] = 'Беларусь (BY)'
    out_row['nick_name'] = (
        f"{row.get('Personal number', '')} "
        f"{row.get('Last name', '')} "
        f"{row.get('First name', '')} "
        f"{row.get('Middle name', '')}"
    )
    
    # Удаляем поле 'card', если оно есть
    out_row.pop('card', None)
    
    writer.writerow(out_row)

def create_output_row(row: Dict, card_track_two: str, personal_number: str) -> Dict:
    """Создает выходную строку для CSV."""
    out_row = {}
    for in_col, out_col in INPUT_COLUMNS_MAPPING.items():
        out_row[out_col] = row.get(in_col, '')
    
    out_row['card_track_two'] = card_track_two
    out_row['country'] = 'Беларусь (BY)'
    out_row['nick_name'] = (
        f"{personal_number} "
        f"{row.get('Last name', '')} "
        f"{row.get('First name', '')} "
        f"{row.get('Middle name', '')}"
    )
    
    # Удаляем поле 'card', если оно есть (оно не входит в OUTPUT_COLUMNS)
    out_row.pop('card', None)
    
    return out_row

def save_duplicates(duplicates: Set[Tuple], filename: str):
    """Сохраняет дубликаты в текстовый файл."""
    with open(filename, 'w', encoding='utf-8') as dfile:
        for fio in duplicates:
            dfile.write(' '.join(fio) + '\n')
    logger.info(f"Дубликаты сохранены в {filename}")

def save_json(data: Dict, filename: str):
    """Сохраняет данные в JSON файл."""
    with open(filename, 'w', encoding='utf-8') as jf:
        json.dump(data, jf, ensure_ascii=False, indent=2)
    logger.info(f"JSON файл сохранен: {filename}")