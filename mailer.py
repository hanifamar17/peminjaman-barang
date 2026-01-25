# mailer.py
from flask_mail import Mail, Message
from flask import current_app
from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import smtplib
from email.mime.text import MIMEText

mail = Mail()
scheduler = BackgroundScheduler()
started = False


def init_app(app):
    """Inisialisasi Flask-Mail dan scheduler."""
    global started
    mail.init_app(app)
    if app.config.get("ENABLE_SCHEDULER", False) and not started:
        scheduler.start()
        started = True


def send_loan_email(
    to_emails, code, borrower_name, items, loan_date, return_date, receipt_url, note=""
):
    """
    Kirim email konfirmasi peminjaman barang.
    - to_emails: list of email penerima
    - code: kode peminjaman
    - borrower_name: nama peminjam
    - items: list of dict {'item_name', 'qty'}
    - loan_date, return_date: string/tanggal
    - note: catatan tambahan
    """

    EMAIL_USER = current_app.config["MAIL_USERNAME"]
    EMAIL_PASS = current_app.config["MAIL_PASSWORD"]
    EMAIL_HOST = current_app.config["MAIL_SERVER"]
    EMAIL_PORT = current_app.config["MAIL_PORT"]

    # Buat daftar barang dalam HTML
    items_html = "".join(
        f"<tr><td>{i['name']}</td><td style='text-align:center'>{i['qty']}</td></tr>"
        for i in items
    )

    html_content = f"""
    <html>
    <body>
        <h2>Konfirmasi Peminjaman Barang</h2>
        <p>Halo <b>{borrower_name}</b>,</p>
        <p>Berikut adalah detail peminjaman Anda:</p>

        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%; max-width: 400px;">
            <thead>
                <tr style="background-color: #f3f3f3;">
                    <th>Barang</th>
                    <th>Jumlah</th>
                </tr>
            </thead>
            <tbody>
                {items_html}
            </tbody>
        </table>

        <p><b>Kode Peminjaman:</b> {code}</p>
        <p><b>Tanggal Pinjam:</b> {loan_date}</p>
        <p><b>Tanggal Kembali:</b> {return_date}</p>
        <p><b>Cek detail peminjaman Anda:</b> <a href="{receipt_url}">{receipt_url}</a></p>
        {'<p><b>Catatan:</b> ' + note + '</p>' if note else ''}

        <hr>
        <p style="font-size: 0.9em; color: #555;">
            Ini adalah email otomatis. Mohon <b>tidak membalas</b> email ini.
        </p>
    </body>
    </html>
    """

    msg = MIMEText(html_content, "html")
    msg["Subject"] = f"Konfirmasi Peminjaman Barang ({code})"
    msg["From"] = EMAIL_USER
    msg["To"] = ", ".join(to_emails)

    try:
        with smtplib.SMTP(current_app.config['MAIL_SERVER'], int(current_app.config['MAIL_PORT'])) as server:
            if current_app.config.get('MAIL_USE_TLS', True):
                server.starttls()
            server.login(current_app.config['MAIL_USERNAME'], current_app.config['MAIL_PASSWORD'])
            server.sendmail(current_app.config['MAIL_USERNAME'], to_emails, msg.as_string())
        current_app.logger.info(f'Email konfirmasi terkirim ke {to_emails}')
    except Exception as e:
        current_app.logger.warning(f'Email gagal dikirim: {e}')


def schedule_return_reminder(job_id, run_at_dt, func, args=None):
    """Jadwalkan pengingat H-1 sebelum tanggal pengembalian."""
    if run_at_dt <= datetime.datetime.utcnow():
        return
    scheduler.add_job(func, "date", run_date=run_at_dt, args=args or [], id=job_id)


def reminder_send_email(to_emails, code, item_name):
    """Fungsi yang dipanggil oleh scheduler untuk pengingat."""
    with current_app.app_context():
        send_loan_email(
            to_emails,
            code=code,
            borrower_name="Peminjam",
            items=[{"item_name": item_name, "qty": 1}],
            loan_date="-",
            return_date="-",
            note=f"Besok adalah batas pengembalian {item_name}.",
        )
