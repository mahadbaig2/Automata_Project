from datetime import datetime, timedelta
from models import Task, db

def repeat_scheduler(app):
    with app.app_context():
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        tasks = Task.query.filter_by(status='Completed').all()

        for task in tasks:
            if task.repeat in ['daily', 'weekly']:
                last_time = datetime.strptime(task.remind_time, "%Y-%m-%d %H:%M")
                if task.repeat == 'daily':
                    next_time = last_time + timedelta(days=1)
                else:
                    next_time = last_time + timedelta(weeks=1)

                # Clone task
                new_task = Task(
                    description=task.description,
                    remind_time=next_time.strftime("%Y-%m-%d %H:%M"),
                    status='Pending',
                    repeat=task.repeat,
                    user_id=task.user_id
                )
                db.session.add(new_task)
                task.status = 'Archived'
        db.session.commit()
