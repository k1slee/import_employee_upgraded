from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory
from flask_login import login_user, logout_user, login_required, current_user
from app import db, login_manager
from app.models import User, Employee
from app.tasks import start_processing_async, is_running, import_excel_to_db, excel_date_to_datetime, is_worker_active
from app.config import Config
from datetime import datetime
import os
import logging
from app.tasks import get_status

bp = Blueprint('routes', __name__)
logger = logging.getLogger(__name__)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@bp.route('/status')
@login_required
def get_job_status():
    """Возвращает текущий статус выполнения (JSON)."""
    from flask import jsonify
    return jsonify(get_status())

@bp.route('/')
@login_required
def dashboard():
    """Главная страница с дашбордом."""
    active_count = Employee.query.filter_by(is_active=True).count()
    total_count = Employee.query.count()
    return render_template('dashboard.html',
                           active_count=active_count,
                           total_count=total_count,
                           is_running=is_running,
                           output_json=Config.OUTPUT_JSON,
                           output_csv=Config.OUTPUT_CSV)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('routes.dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Вход выполнен успешно.', 'success')
            return redirect(url_for('routes.dashboard'))
        flash('Неверное имя пользователя или пароль.', 'danger')
    return render_template('login.html')

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('routes.login'))

@bp.route('/run', methods=['POST'])
@login_required
def run_processing():
    """Запуск обработки."""
    if is_running:
        flash('Обработка уже выполняется.', 'warning')
    else:
        start_processing_async()
        flash('Обработка запущена в фоновом режиме.', 'success')
    return redirect(url_for('routes.dashboard'))

@bp.route('/download/<filename>')
@login_required
def download_file(filename):
    safe_files = ['workers.json', 'workers.csv', 'accepted.csv', 'duplicates.txt']
    if filename not in safe_files:
        flash('Файл не разрешён для скачивания.', 'danger')
        return redirect(url_for('routes.dashboard'))
    
    # Абсолютный путь к папке data
    data_dir = os.path.abspath('data')
    
    # Проверяем существование файла
    file_path = os.path.join(data_dir, filename)
    if not os.path.exists(file_path):
        flash(f'Файл {filename} не найден в {data_dir}', 'warning')
        return redirect(url_for('routes.dashboard'))
    
    return send_from_directory(data_dir, filename, as_attachment=True)

@bp.route('/upload_excel', methods=['GET', 'POST'])
@login_required
def upload_excel():
    """Загрузка Excel-файла для обновления БД."""
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename.endswith('.xlsx'):
            flash('Пожалуйста, загрузите файл .xlsx', 'danger')
            return redirect(url_for('routes.upload_excel'))
        # Сохраняем временный файл
        temp_path = os.path.join('data', 'temp_upload.xlsx')
        file.save(temp_path)
        # Запускаем импорт (может быть долгим, делаем в фоне или синхронно)
        from app.tasks import import_excel_to_db
        try:
            import_excel_to_db(temp_path)
            flash('Данные успешно обновлены.', 'success')
        except Exception as e:
            flash(f'Ошибка импорта: {e}', 'danger')
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        return redirect(url_for('routes.dashboard'))
    return render_template('upload.html')

# ---------- Управление сотрудниками ----------
@bp.route('/employees')
@login_required
def employees():
    """Список всех сотрудников."""
    # Получаем параметры фильтрации из query string
    show = request.args.get('show', 'all')  # 'active', 'inactive', 'all'
    search = request.args.get('search', '').strip()
    
    query = Employee.query
    if show == 'active':
        query = query.filter_by(is_active=True)
    elif show == 'inactive':
        query = query.filter_by(is_active=False)
    
    if search:
        query = query.filter(Employee.full_name.contains(search))
    
    employees_list = query.order_by(Employee.full_name).all()
    return render_template('employees.html', employees=employees_list, show=show, search=search)

@bp.route('/run_all', methods=['POST'])
@login_required
def run_all():
    """Запуск всех шагов последовательно."""
    from app.tasks import is_running, start_full_process_async
    if is_running:
        flash('Обработка уже выполняется.', 'warning')
    else:
        start_full_process_async()
        flash('Запущен полный цикл обработки.', 'success')
    return redirect(url_for('routes.dashboard'))

@bp.route('/employees/add', methods=['GET', 'POST'])
@login_required
def add_employee():
    """Добавление нового сотрудника."""
    if request.method == 'POST':
        personal_number = request.form.get('personal_number', '').strip() or None
        full_name = request.form.get('full_name', '').strip()
        hire_date_str = request.form.get('hire_date', '').strip()
        fire_date_str = request.form.get('fire_date', '').strip()
        
        if not full_name:
            flash('ФИО обязательно для заполнения.', 'danger')
            return render_template('add_employee.html')
        
        # Преобразование дат
        hire_date = None
        if hire_date_str:
            try:
                hire_date = datetime.strptime(hire_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Неверный формат даты приёма (ГГГГ-ММ-ДД).', 'danger')
                return render_template('add_employee.html')
        
        fire_date = None
        if fire_date_str:
            try:
                fire_date = datetime.strptime(fire_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Неверный формат даты увольнения (ГГГГ-ММ-ДД).', 'danger')
                return render_template('add_employee.html')
        
        # Вычисляем активность (аналогично is_worker_active)
        today = datetime.now().date()
        is_active = True
        if not hire_date:
            is_active = False
        elif hire_date > today:
            is_active = False
        elif fire_date and fire_date < today:
            is_active = False
        
        employee = Employee(
            personal_number=personal_number,
            full_name=full_name,
            hire_date=hire_date,
            fire_date=fire_date,
            is_active=is_active
        )
        db.session.add(employee)
        db.session.commit()
        flash(f'Сотрудник "{full_name}" успешно добавлен.', 'success')
        return redirect(url_for('routes.employees'))
    
    return render_template('add_employee.html')

@bp.route('/employees/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_employee(id):
    """Редактирование сотрудника."""
    employee = Employee.query.get_or_404(id)
    if request.method == 'POST':
        personal_number = request.form.get('personal_number', '').strip() or None
        full_name = request.form.get('full_name', '').strip()
        hire_date_str = request.form.get('hire_date', '').strip()
        fire_date_str = request.form.get('fire_date', '').strip()
        
        if not full_name:
            flash('ФИО обязательно для заполнения.', 'danger')
            return render_template('edit_employee.html', employee=employee)
        
        # Преобразование дат
        hire_date = None
        if hire_date_str:
            try:
                hire_date = datetime.strptime(hire_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Неверный формат даты приёма (ГГГГ-ММ-ДД).', 'danger')
                return render_template('edit_employee.html', employee=employee)
        
        fire_date = None
        if fire_date_str:
            try:
                fire_date = datetime.strptime(fire_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Неверный формат даты увольнения (ГГГГ-ММ-ДД).', 'danger')
                return render_template('edit_employee.html', employee=employee)
        
        # Пересчёт активности
        today = datetime.now().date()
        is_active = True
        if not hire_date:
            is_active = False
        elif hire_date > today:
            is_active = False
        elif fire_date and fire_date < today:
            is_active = False
        employee.personal_number = personal_number
        employee.full_name = full_name
        employee.hire_date = hire_date
        employee.fire_date = fire_date
        employee.is_active = is_active
        
        db.session.commit()
        flash(f'Данные сотрудника обновлены.', 'success')
        return redirect(url_for('routes.employees'))
    
    return render_template('edit_employee.html', employee=employee)

@bp.route('/employees/<int:id>/delete', methods=['POST'])
@login_required
def delete_employee(id):
    """Удаление сотрудника."""
    employee = Employee.query.get_or_404(id)
    full_name = employee.full_name
    db.session.delete(employee)
    db.session.commit()
    flash(f'Сотрудник "{full_name}" удалён.', 'success')
    return redirect(url_for('routes.employees'))


#Тест маршруты
@bp.route('/step1', methods=['POST'])
@login_required
def step1():
    """Запуск шага 1 (скачивание)."""
    if is_running:
        flash('Другой процесс уже выполняется.', 'warning')
    else:
        from app.tasks import start_step1_async
        start_step1_async()
        flash('Шаг 1 (скачивание) запущен.', 'success')
    return redirect(url_for('routes.dashboard'))

@bp.route('/step2', methods=['POST'])
@login_required
def step2():
    """Запуск шага 2 (обработка)."""
    if is_running:
        flash('Другой процесс уже выполняется.', 'warning')
    else:
        from app.tasks import start_step2_async
        start_step2_async()
        flash('Шаг 2 (обработка) запущен.', 'success')
    return redirect(url_for('routes.dashboard'))

@bp.route('/step3', methods=['POST'])
@login_required
def step3():
    """Запуск шага 3 (финализация)."""
    if is_running:
        flash('Другой процесс уже выполняется.', 'warning')
    else:
        from app.tasks import start_step3_async
        start_step3_async()
        flash('Шаг 3 (финализация) запущен.', 'success')
    return redirect(url_for('routes.dashboard'))

# Старый маршрут /run оставляем для полного цикла