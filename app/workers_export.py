import csv
import json
import os
import logging
from app.config import Config


logger = logging.getLogger(__name__)
def _col(name, default):
    return getattr(Config, name, None) or default

def build_workers_dict(csv_path, encoding='cp1251'):
    card_col  = _col('WORKERS_CARD_COL',  'card_track_two')
    tab_col   = _col('WORKERS_TAB_COL',   'matchcode')
    name_col  = _col('WORKERS_NAME_COL',  'name')
    first_col = _col('WORKERS_FIRST_COL', 'first_name')
    patr_col  = _col('WORKERS_PATR_COL',  'patronym')

    result = {}
    with open(csv_path, 'r', encoding=encoding, newline='') as f:
        reader = csv.DictReader(f, delimiter = ';')
        for row in reader:
            card = (row.get(card_col) or '').strip()
            if not card:
                continue
            fio = ' '.join(p for p in(
                (row.get(name_col) or '').strip(),
                (row.get(first_col) or '').strip(),
                (row.get(patr_col) or '').strip(),
            ) if p)

            result[card] = {
                'name': fio,
                'matchcode':  (row.get(tab_col) or '').strip(),
                'card_number': card,
            }
        return result 

def export_workers_json(csv_path, json_path, encoding='cp1251'):
    """Собирает json """
    data = build_workers_dict(csv_path, encoding=encoding)

    dirname = os.path.dirname(json_path)

    if dirname:
        os.makedirs(dirname, exist_ok=True)

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent= 2)
    logger.info(f"workers_by_card.json: {len(data)} Записей {json_path}")
    return data