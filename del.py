from app import create_app, db
from app.models import Employee
app = create_app()
with app.app_context():
    Employee.query.delete()
    db.session.commit()