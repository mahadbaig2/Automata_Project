from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import Task

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    stats = {
        "total": len(tasks),
        "pending": sum(1 for t in tasks if t.status == 'Pending'),
        "completed": sum(1 for t in tasks if t.status == 'Completed'),
        "repeating": sum(1 for t in tasks if t.repeat in ['daily', 'weekly']),
    }
    return render_template("dashboard.html", stats=stats)
