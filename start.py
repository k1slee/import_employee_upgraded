from app import create_app, db
from app.models import User

app = create_app()
with app.app_context():
    db.create_all()
    # Проверим, есть ли уже пользователь admin
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin')
        admin.set_password('admin123')  # пароль, который будете использовать для входа
        db.session.add(admin)
        db.session.commit()
        print("Пользователь admin создан с паролем admin123")
    else:
        print("Пользователь уже существует")