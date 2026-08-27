import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import Employee
from app.tasks import import_excel_to_db

app = create_app()
with app.app_context():
    excel_path = 'pass.xlsx'
    if not os.path.exists(excel_path):
        print(f"Файл {excel_path} не найден")
        sys.exit(1)
    count = import_excel_to_db(excel_path)
    print(f"Импортировано {count} сотрудников.")