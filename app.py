from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import smtplib
from email.mime.text import MIMEText
import os
from dotenv import load_dotenv
import csv
import re

from fsm import TaskReminderFSM

load_dotenv()

app = Flask(__name__)
app.secret_key = 'secret123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')
EMAIL_TO = os.getenv('EMAIL_TO')


# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    tasks = db.relationship('Task', backref='owner', lazy=True, cascade='all, delete-orphan')

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return True

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    remind_time = db.Column(db.String(20), nullable=False)
    reminder_offset = db.Column(db.Integer, default=5)
    status = db.Column(db.String(20), default='Pending')
    priority = db.Column(db.String(20), default='Medium')  # High, Medium, Low
    repeat = db.Column(db.String(20), default='once')  # once, daily, weekly, monthly
    alert_type = db.Column(db.String(20), default='both')  # email, browser, both
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    fsm_state = db.Column(db.String(50), default='Idle')
    created_at = db.Column(db.String(20), default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# Initialize FSM
fsm = TaskReminderFSM()


# Smart Task Prioritization
def calculate_priority(description, remind_time):
    """
    Automatically assigns priority based on:
    1. Time until deadline (urgency)
    2. Keywords in description (importance)
    """
    try:
        task_time = datetime.strptime(remind_time, "%Y-%m-%d %H:%M")
        time_diff = task_time - datetime.now()
        hours_until = time_diff.total_seconds() / 3600

        # Keyword analysis for importance
        high_keywords = ['urgent', 'critical', 'important', 'asap', 'emergency', 'deadline', 'exam', 'interview',
                         'meeting']
        medium_keywords = ['task', 'assignment', 'project', 'work', 'study', 'call', 'email']

        description_lower = description.lower()
        has_high_keyword = any(keyword in description_lower for keyword in high_keywords)
        has_medium_keyword = any(keyword in description_lower for keyword in medium_keywords)

        # Priority logic
        if hours_until < 24:  # Less than 24 hours
            if has_high_keyword:
                return 'High'
            return 'High'  # Anything due within 24 hours is high priority
        elif hours_until < 72:  # 1-3 days
            if has_high_keyword:
                return 'High'
            elif has_medium_keyword:
                return 'Medium'
            return 'Medium'
        else:  # More than 3 days
            if has_high_keyword:
                return 'Medium'
            return 'Low'

    except Exception as e:
        print(f"Priority calculation error: {e}")
        return 'Medium'


# Email notification
def send_email_reminder(task_desc, user_email):
    msg = MIMEText(f"Reminder: {task_desc}")
    msg['Subject'] = "Task Reminder"
    msg['From'] = EMAIL_USER
    msg['To'] = user_email
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, [user_email], msg.as_string())
        print(f"✅ Email sent for: {task_desc}")
    except Exception as e:
        print(f"❌ Email failed for {task_desc}: {e}")


# Check reminders scheduler
def check_reminders():
    with app.app_context():
        now = datetime.now()
        tasks = Task.query.filter(Task.status == 'Pending').all()

        for task in tasks:
            task_time = datetime.strptime(task.remind_time, "%Y-%m-%d %H:%M")

            # Calculate reminder time (task_time - offset)
            reminder_time = task_time - timedelta(minutes=task.reminder_offset)

            # Check if it's time to send reminder (within the current minute)
            if now.strftime("%Y-%m-%d %H:%M") == reminder_time.strftime("%Y-%m-%d %H:%M"):
                print(f"📧 Reminder triggered for task: {task.description} ({task.reminder_offset} min before deadline)")

                # Send notification based on alert_type
                if task.alert_type in ['email', 'both']:
                    send_email_reminder(task.description, task.owner.email)

                # Update FSM state
                task.fsm_state = 'Reminder Sent'
                db.session.commit()

            # Check if task is overdue (past deadline and still pending)
            elif now > task_time and task.status == 'Pending':
                print(f"⏰ Task overdue: {task.description}")
                task.status = 'Overdue'
                task.fsm_state = 'Task Overdue'

                # Handle recurring tasks - create next instance even if overdue
                if task.repeat != 'once':
                    handle_recurring_task(task)

                db.session.commit()


# Recurring task handler
def handle_recurring_task(task):
    """Creates next occurrence of recurring task"""
    try:
        last_time = datetime.strptime(task.remind_time, "%Y-%m-%d %H:%M")

        if task.repeat == 'daily':
            next_time = last_time + timedelta(days=1)
        elif task.repeat == 'weekly':
            next_time = last_time + timedelta(weeks=1)
        elif task.repeat == 'monthly':
            next_time = last_time + timedelta(days=30)
        else:
            return

        # Create new task for next occurrence
        new_task = Task(
            description=task.description,
            remind_time=next_time.strftime("%Y-%m-%d %H:%M"),
            reminder_offset=task.reminder_offset,
            status='Pending',
            priority=calculate_priority(task.description, next_time.strftime("%Y-%m-%d %H:%M")),
            repeat=task.repeat,
            alert_type=task.alert_type,
            user_id=task.user_id,
            fsm_state='Task Added'
        )
        db.session.add(new_task)

        # Archive current task (not mark as completed)
        task.status = 'Archived'
        task.fsm_state = 'Task Repeated'

        print(f"🔄 Recurring task created: {task.description} for {next_time}")
    except Exception as e:
        print(f"❌ Recurring task error: {e}")


# Scheduler setup
scheduler = BackgroundScheduler()
scheduler.add_job(check_reminders, 'interval', minutes=1)
scheduler.start()

local_notified_tasks = set()


# Routes - Authentication
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        if User.query.filter_by(email=email).first():
            flash("Email already exists!", "danger")
            return redirect(url_for('signup'))

        if User.query.filter_by(username=username).first():
            flash("Username already taken!", "danger")
            return redirect(url_for('signup'))

        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        user = User(username=username, email=email, password=hashed_pw)
        db.session.add(user)
        db.session.commit()
        flash("Account created successfully! Please log in.", "success")
        return redirect(url_for('login'))

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            flash(f"Welcome back, {user.username}!", "success")
            return redirect(url_for('index'))
        flash("Invalid credentials!", "danger")

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for('login'))


# Routes - Task Management
@app.route('/')
@login_required
def index():
    return render_template('index.html')


@app.route('/add', methods=['POST'])
@login_required
def add_task():
    desc = request.form['description']
    date = request.form['date']
    time = request.form['time']
    offset = int(request.form['reminder_offset'])
    repeat = request.form.get('repeat', 'once')
    alert_type = request.form.get('alert_type', 'both')
    remind_time = f"{date} {time}"

    try:
        datetime.strptime(remind_time, "%Y-%m-%d %H:%M")

        # Calculate priority automatically
        priority = calculate_priority(desc, remind_time)

        new_task = Task(
            description=desc,
            remind_time=remind_time,
            reminder_offset=offset,
            priority=priority,
            repeat=repeat,
            alert_type=alert_type,
            user_id=current_user.id,
            fsm_state='Task Added'
        )
        db.session.add(new_task)
        db.session.commit()
        flash(f"Task added with {priority} priority!", "success")
    except ValueError:
        flash("Invalid date/time format!", "danger")

    return redirect(url_for('view_tasks'))


@app.route('/tasks')
@login_required
def view_tasks():
    q = request.args.get('q', '')
    start = request.args.get('start')
    end = request.args.get('end')
    priority_filter = request.args.get('priority')
    status_filter = request.args.get('status')

    query = Task.query.filter_by(user_id=current_user.id)

    if q:
        query = query.filter(Task.description.ilike(f"%{q}%"))
    if start and end:
        query = query.filter(Task.remind_time.between(start + " 00:00", end + " 23:59"))
    if priority_filter:
        query = query.filter_by(priority=priority_filter)
    if status_filter:
        query = query.filter_by(status=status_filter)

    tasks = query.order_by(Task.remind_time).all()
    return render_template('tasks.html', tasks=tasks)


@app.route('/delete/<int:id>')
@login_required
def delete_task(id):
    task = Task.query.get_or_404(id)
    if task.user_id != current_user.id:
        flash("Unauthorized action!", "danger")
        return redirect(url_for('view_tasks'))

    task.fsm_state = 'Task Deleted'
    db.session.delete(task)
    db.session.commit()
    flash("Task deleted.", "info")
    return redirect(url_for('view_tasks'))


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_task(id):
    task = Task.query.get_or_404(id)
    if task.user_id != current_user.id:
        flash("Unauthorized action!", "danger")
        return redirect(url_for('view_tasks'))

    if request.method == 'POST':
        task.description = request.form['description']
        remind_time = f"{request.form['date']} {request.form['time']}"
        task.remind_time = remind_time
        task.reminder_offset = int(request.form['reminder_offset'])
        task.repeat = request.form.get('repeat', 'once')
        task.alert_type = request.form.get('alert_type', 'both')

        # Recalculate priority
        task.priority = calculate_priority(task.description, remind_time)

        db.session.commit()
        flash("Task updated successfully!", "success")
        return redirect(url_for('view_tasks'))

    return render_template("edit.html", task=task)


@app.route('/complete/<int:id>')
@login_required
def complete_task(id):
    task = Task.query.get_or_404(id)
    if task.user_id != current_user.id:
        flash("Unauthorized action!", "danger")
        return redirect(url_for('view_tasks'))

    task.status = "Completed"
    task.fsm_state = "Task Completed"
    db.session.commit()
    flash("Task marked as completed!", "success")
    return redirect(url_for('view_tasks'))


@app.route('/export')
@login_required
def export_csv():
    from flask import make_response
    from io import StringIO

    tasks = Task.query.filter_by(user_id=current_user.id).all()

    # Create CSV in memory
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["ID", "Description", "Remind Time", "Priority", "Status", "Repeat", "Alert Type", "FSM State", "Created At"])

    for task in tasks:
        writer.writerow([
            task.id,
            task.description,
            task.remind_time,
            task.priority,
            task.status,
            task.repeat,
            task.alert_type,
            task.fsm_state,
            task.created_at or 'N/A'
        ])

    # Create response with CSV data
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers[
        "Content-Disposition"] = f"attachment; filename=task_export_{current_user.username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response.headers["Content-Type"] = "text/csv"

    flash(f"CSV exported successfully!", "success")
    return response


@app.route('/check-local-notifications')
@login_required
def check_local_notifications():
    now = datetime.now()
    results = []
    tasks = Task.query.filter_by(user_id=current_user.id, status='Pending').all()

    for task in tasks:
        if task.alert_type not in ['browser', 'both']:
            continue

        task_time = datetime.strptime(task.remind_time, "%Y-%m-%d %H:%M")
        reminder_time = task_time - timedelta(minutes=task.reminder_offset)

        # Check if it's time for browser notification (reminder time, not deadline)
        if reminder_time.strftime("%Y-%m-%d %H:%M") == now.strftime("%Y-%m-%d %H:%M"):
            if task.id not in local_notified_tasks:
                results.append({
                    "id": task.id,
                    "description": task.description,
                    "priority": task.priority,
                    "minutes_before": task.reminder_offset
                })
                local_notified_tasks.add(task.id)

    return jsonify(notifications=results)


@app.route('/calendar')
@login_required
def calendar():
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    events = []
    for task in tasks:
        # Color coding based on status and priority
        if task.status == "Completed":
            color = "#6c757d"  # Gray
        elif task.status == "Overdue":
            color = "#8b0000"  # Dark red
        elif task.priority == "High":
            color = "#dc3545"  # Red
        elif task.priority == "Medium":
            color = "#ffc107"  # Yellow
        else:
            color = "#28a745"  # Green

        events.append({
            "title": f"[{task.priority}] {task.description}",
            "start": task.remind_time.replace(" ", "T"),
            "color": color,
            "extendedProps": {
                "status": task.status,
                "priority": task.priority
            }
        })
    return render_template("calendar.html", events=events)


@app.route('/dashboard')
@login_required
def dashboard():
    from collections import defaultdict

    tasks = Task.query.filter_by(user_id=current_user.id).all()
    total_tasks = len(tasks)
    pending_tasks = len([t for t in tasks if t.status == 'Pending'])
    completed_tasks = len([t for t in tasks if t.status == 'Completed'])
    overdue_tasks = len([t for t in tasks if t.status == 'Overdue'])
    high_priority = len([t for t in tasks if t.priority == 'High' and t.status == 'Pending'])
    recurring_tasks = len([t for t in tasks if t.repeat != 'once'])

    upcoming = Task.query.filter_by(user_id=current_user.id, status='Pending').order_by(Task.remind_time).limit(5).all()

    # Tasks per day (last 7 days)
    task_dates = defaultdict(int)
    today = datetime.now().date()
    for i in range(7):
        day = today - timedelta(days=i)
        count = Task.query.filter(
            Task.user_id == current_user.id,
            Task.remind_time.like(f"{day}%")
        ).count()
        task_dates[day.strftime("%Y-%m-%d")] = count

    chart_labels = list(task_dates.keys())[::-1]
    chart_data = list(task_dates.values())[::-1]

    # Priority distribution
    priority_data = {
        'High': len([t for t in tasks if t.priority == 'High']),
        'Medium': len([t for t in tasks if t.priority == 'Medium']),
        'Low': len([t for t in tasks if t.priority == 'Low'])
    }

    # Status distribution (including overdue)
    status_data = {
        'Pending': pending_tasks,
        'Completed': completed_tasks,
        'Overdue': overdue_tasks
    }

    # Calculate completion rate (only from completed and overdue, not archived)
    actionable_tasks = completed_tasks + overdue_tasks
    completion_rate = round((completed_tasks / actionable_tasks * 100) if actionable_tasks > 0 else 0, 1)

    return render_template("dashboard.html",
                           total=total_tasks,
                           pending=pending_tasks,
                           completed=completed_tasks,
                           overdue=overdue_tasks,
                           high_priority=high_priority,
                           recurring=recurring_tasks,
                           upcoming=upcoming,
                           labels=chart_labels,
                           chart_data=chart_data,
                           priority_data=priority_data,
                           status_data=status_data,
                           completion_rate=completion_rate)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)