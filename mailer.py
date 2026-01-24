from flask_mail import Mail, Message
from flask import current_app
from apscheduler.schedulers.background import BackgroundScheduler
import datetime

mail = Mail()
scheduler = BackgroundScheduler()
started = False

def init_app(app):
    global started
    mail.init_app(app)
    if app.config.get('ENABLE_SCHEDULER') and not started:
        scheduler.start()
        started = True

def send_loan_email(to_addrs, subject, html_body):
    msg = Message(subject=subject, recipients=to_addrs, html=html_body, sender=current_app.config['MAIL_USERNAME'])
    mail.send(msg)

def schedule_return_reminder(job_id, run_at_dt, func, args=None):
    if run_at_dt <= datetime.datetime.utcnow():
        # if date passed, skip
        return
    scheduler.add_job(func, 'date', run_date=run_at_dt, args=args or [], id=job_id)

# contoh fungsi pengingat
def reminder_send_email(to_addrs, subject, html_body):
    with current_app.app_context():
        send_loan_email(to_addrs, subject, html_body)