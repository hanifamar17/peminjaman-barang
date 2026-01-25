# mailer.py
from flask_mail import Mail, Message
from flask import current_app
from apscheduler.schedulers.background import BackgroundScheduler
import datetime

mail = Mail()
scheduler = BackgroundScheduler()
_started = False


def init_app(app):
    """Inisialisasi Flask-Mail dan scheduler (opsional)."""
    global _started
    mail.init_app(app)

    if app.config.get("ENABLE_SCHEDULER", False) and not _started:
        scheduler.start()
        _started = True


def send_loan_email(
    to_emails,
    code,
    borrower_name,
    items,
    loan_date,
    return_date,
    receipt_url,
    note=""
):
    """
    Kirim email konfirmasi peminjaman barang (Flask-Mail).
    items: list of dict {'name', 'qty'}
    """

    # Render daftar barang
    items_html = "".join(
        f"<tr><td>{i['name']}</td><td align='center'>{i['qty']}</td></tr>"
        for i in items
    )

    html_content = f"""
    <h2>Konfirmasi Peminjaman Barang</h2>

    <p>Halo <b>{borrower_name}</b>,</p>
    <p>Berikut adalah detail peminjaman Anda:</p>

    <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%; max-width: 400px;">
        <thead style="background:#f3f3f3;">
            <tr>
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

    <p>
        Cek detail peminjaman Anda melalui halaman berikut:<br>
        <a href="{receipt_url}">{receipt_url}</a>
    </p>

    {f"<p><b>Catatan:</b> {note}</p>" if note else ""}

    <hr>
    <p style="font-size:0.9em;color:#666;">
        Ini adalah email otomatis. Mohon <b>tidak membalas</b> email ini.
    </p>
    """

    msg = Message(
        subject=f"Konfirmasi Peminjaman ({code})",
        recipients=to_emails,
        html=html_content,
        sender=current_app.config["MAIL_USERNAME"],
    )

    mail.send(msg)


def schedule_return_reminder(job_id, run_at_dt, func, args=None):
    """Jadwalkan pengingat H-1 (hanya untuk lokal / non-serverless)."""
    if run_at_dt <= datetime.datetime.utcnow():
        return

    scheduler.add_job(
        func,
        "date",
        run_date=run_at_dt,
        args=args or [],
        id=job_id,
        replace_existing=True,
    )


def reminder_send_email(to_emails, code, borrower_name, items=None):
    """Email pengingat H-1."""
    with current_app.app_context():
        send_loan_email(
            to_emails=to_emails,
            code=code,
            borrower_name=borrower_name,
            items=items,
            loan_date="-",
            return_date="-",
            receipt_url="#",
            note="Besok adalah batas pengembalian barang yang Anda pinjam.",
        )
