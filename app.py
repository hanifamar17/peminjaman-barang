import os, time
from flask import (
    Flask,
    abort,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    flash,
    send_from_directory,
    request, redirect, url_for, session, flash
)
from mailer import (
    mail,
    init_app,
)
from dotenv import load_dotenv
from werkzeug.security import check_password_hash
from werkzeug.security import check_password_hash
from functools import wraps
from flask_wtf import CSRFProtect
from urllib.parse import urlparse, urljoin

from sheets.sheets import read_sheet
from sheets.sheets_pengumuman import get_all_pengumuman

from routes.routes_jadwal_pelajaran import split_mixed_script

from routes.routes_inventory_aset import inventaris_bp
from routes.routes_booking_ruangan import booking_ruangan_bp
from routes.routes_inventory_komp import inventory_labkomp_bp
from routes.routes_peminjaman import peminjaman_invlabkomp_bp
from routes.routes_pengumuman import pengumuman_bp
from routes.routes_jadwal_pelajaran import jadwal_pelajaran_bp



load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")
app.config["UPLOAD_FOLDER"] = os.getenv("UPLOAD_FOLDER", "static/uploads")
app.register_blueprint(inventaris_bp)
app.register_blueprint(booking_ruangan_bp)
app.register_blueprint(inventory_labkomp_bp)
app.register_blueprint(peminjaman_invlabkomp_bp)
app.register_blueprint(pengumuman_bp)
app.register_blueprint(jadwal_pelajaran_bp)
app.jinja_env.globals['split_mixed_script'] = split_mixed_script

# =========================
# DETEKSI ENVIRONMENT
# =========================
IS_VERCEL = os.getenv("VERCEL") == "1"

ENABLE_SCHEDULER = (
    os.getenv("ENABLE_SCHEDULER", "false").lower() in ["true", "1"]
    and not IS_VERCEL
)

app.config["ENABLE_SCHEDULER"] = ENABLE_SCHEDULER

# =========================
# SESSION CONFIG
# =========================
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=IS_VERCEL,  # True hanya di Vercel (HTTPS)
    SESSION_COOKIE_SAMESITE="Lax",
)

# =========================
# CSRF PROTECTION
# =========================
csrf = CSRFProtect()
csrf.init_app(app)

# =========================
# Konfigurasi Email (Gmail App Password)
# =========================
app.config.update(
    MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.gmail.com"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
    MAIL_USE_TLS=os.getenv("MAIL_USE_TLS", "True") in ["True", "true", "1"],
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
)

mail.init_app(app)

# scheduler hanya di lokal
if app.config["ENABLE_SCHEDULER"]:
    init_app(app)

# Maintenance Mode    
@app.before_request
def maintenance_mode():
    maintenance = os.getenv("MAINTENANCE_MODE", "false").lower() == "true"
    ALLOWED = ("/maintenance", "/static")
    if maintenance and not request.path.startswith(ALLOWED):
        return render_template("maintenance.html"), 503

@app.route("/maintenance")
def maintenance():
    return render_template("maintenance.html"), 503

# LOGIN
def is_safe_url(target):
    """Cegah open redirect: hanya izinkan redirect ke path relatif di domain sendiri."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return (
        test_url.scheme in ("http", "https")
        and ref_url.netloc == test_url.netloc
        )

@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.values.get("next", "") 

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        rows = read_sheet("login")
        if not rows:
            flash("Sistem login belum dikonfigurasi.")
            return redirect(url_for("login"))

        headers = rows[0]
        users = [dict(zip(headers, r)) for r in rows[1:]]
        user = next((u for u in users if u["username"] == username), None)

        time.sleep(0.5)

        if user and check_password_hash(user["password_hash"], password):
            session["user"] = username
            session.regenerate = True

            target = request.form.get("next") or next_url
            if is_safe_url(target):
                return redirect(target)
            return redirect(url_for("repository"))

        flash("Username atau password salah.")
        
        return redirect(url_for("login", next=next_url))

    return render_template("login.html", next=next_url)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("repository"))


# main page
@app.route("/")
def index():
    return redirect(url_for("repository"))

# repository page
@app.route("/repository")
def repository():
    repository_data = [
        {
            "category": "Home",
            "color": "slate",
            "icon": '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"/></svg>',
            "links": []
        },
        {
            "category": "Akademik",
            "color": "blue",
            "icon": '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"></path></svg>',
            "links": [
                {"title": "Kalender akademik", "url": url_for('booking_ruangan.jadwal_penggunaan'), "subtext": "Dokumen kalender akademik"},
                {"title": "Jadwal KBM", "url": url_for('jadwal_pelajaran.jadwal_pelajaran_landing'), "subtext": "Jadwal kegiatan belajar mengajar (KBM)"},
                {"title": "Rapor Digital Madrasah", "url": "#", "subtext": "Coming Soon", "disabled": True}
            ]
        },
        {
            "category": "Sekolah",
            "color": "emerald",
            "icon": '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 14l9-5-9-5-9 5 9 5z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 14l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 14l9-5-9-5-9 5 9 5zm0 0l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14zm-4 6v-7.5l4-2.222"/></svg>',
            "links": [
                {"title": "Presensi Sekolah", "url": "", "subtext": "Coming Soon", "disabled": True},
                {"title": "Presensi Diniyah", "url": "https://script.google.com/macros/s/AKfycbydodNzn3SzN3ekC7jv17PZgoV-7GktfQn3cFyxyEXcFcz1Zv-U5ab3sGBwHxnYojOg/exec", "subtext": "Formulir presensi kegiatan kelas diniyyah", "disabled": False},
                {"title": "Jurnal Mapel", "url": "https://docs.google.com/forms/d/e/1FAIpQLSdGZ7jXITewg7GQM7zoSLmPEUglqbMj3TwGFGWZ46HuGSCotg/viewform", "subtext": "Formulir jurnal kegiatan belajar mengajar mata pelajaran", "disabled": False},
                {"title": "Supervisi", "url": "#", "subtext": "Coming Soon", "disabled": True},
            ]
        },
        {
            "category": "Ekstrakurikuler",
            "color": "amber",
            "icon": '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 22a3.5 3.5 0 01-3.5-3.5c0-2 1.5-3.5 3.5-5.5 2 2 3.5 3.5 3.5 5.5A3.5 3.5 0 0112 22zM12 13V2M12 2c-2.5 2.5-6 3.5-8 3.5M12 2c2.5 2.5 6 3.5 8 3.5M12 6.5c-2 2-4 2.5-6 2.5M12 6.5c2 2 4 2.5 6 2.5"/></svg>',
            "links": [
                {"title": "Presensi Ekstrakurikuler", "url": "https://script.google.com/macros/s/AKfycbxiuxLz2L7ob5jAG9KUKwT2-uXDtzhGG9VCuBfky6-rLp8cHsv9tG3OW3SVck8ny8dh/exec", "subtext": "Formulir presensi kegiatan ekstrakurikuler", "disabled": False},
                {"title": "Jurnal Ekstrakurikuler", "url": "https://docs.google.com/forms/d/e/1FAIpQLSfu0TYIpe67BVyhjXyaSdkPj5ZdvnynCEB2TXrNnMjuSdqxJQ/viewform", "subtext": "Formulir jurnal kegiatan ekstrakurikuler", "disabled": False}
            ]
        },
        {
            "category": "Asrama",
            "color": "violet",
            "icon": '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"></path></svg>',
            "links": [
                {"title": "Presensi kegiatan Asrama", "url": "https://presensimanu.my.id/login", "subtext": "Formulir presensi kegiatan asrama"},
                {"title": "Berita Acara Persidangan Santri", "url": "https://docs.google.com/forms/d/e/1FAIpQLSc5OG8Kf879_mOgmQNxIRuTfH3beYR_DZ54waDaDjWudECLtQ/viewform", "subtext": "Formulir berita acara persidangan santri"},
                {"title": "Buku Catatan Santri", "url": "https://docs.google.com/spreadsheets/d/10smJykmE_TgM4JfR5eigez4bUa5LDEgEtxjnyZJyA1Q/edit?gid=0#gid=0", "subtext": "Under maintenance", "disabled": True},
                {"title": "Formulir Perizinan", "url": "https://tally.so/r/w5Gqz6", "subtext": "Under maintenance", "disabled": True},
                {"title": "Jurnal Perizinan", "url": "https://datastudio.google.com/u/0/reporting/73d02ac9-ca68-479f-9fd3-e1f40834dc6b/page/OTbEE", "subtext": "Under maintenance", "disabled": True},
                {"title": "Tabungan Santri", "url": "#", "subtext": "Under maintenance", "disabled": True}
            ]
        },
        {
            "category": "Sarpras",
            "color": "rose",
            "icon": '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>',
            "links": [
                {"title": "Peminjaman Aset", "url": url_for('inventaris.peminjaman_aset_landing'), "subtext": "Pengelolaan peminjaman aset madrasah", "disabled": False},
                {"title": "Database sarpras", "url": url_for('inventaris.list_inventaris'), "subtext": "Pengelolaan database sarana dan prasarana", "disabled": False}
            ]
        },
        {
            "category": "Lab Komp",
            "color": "indigo",
            "icon": '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>',
            "links": [
                {"title": "Inventaris Lab Komp", "url": url_for('inventory_labkomp.inventory_landing'), "subtext": "Master data inventaris lab komputer"},
                {"title": "Peminjaman Barang", "url": url_for('peminjaman_invlabkomp.peminjaman_landing'), "subtext": "Pengelolaan peminjaman barang lab komputer"},
                {"title": "Peminjaman Ruangan", "url": url_for('booking_ruangan.booking_landing'), "subtext": "Pengelolaan peminjaman ruangan lab komputer"},
            ]
        },
    ]
    pengumuman = get_all_pengumuman()[:10]

    return render_template('repository/landing_repository.html', repository_data=repository_data, pengumuman=pengumuman)


# landing page
@app.route("/e-labkomp")
def labkomp_landing():
    return render_template("landing.html")



# =======================
# STATIC FILE UPLOAD
# =======================
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

#URL
@app.context_processor
def inject_base_url():
    from sheets.sheets import read_sheet

    rows = read_sheet('url')
    if not rows or len(rows) < 2:
        base_url = '/'
    else:
        base_url = rows[1][0] or '/'

    return dict(base_url=base_url)


# ERROR HANDLER
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404


# =======================
# MAIN
# =======================
if __name__ == "__main__":
    app.run(debug=True)
