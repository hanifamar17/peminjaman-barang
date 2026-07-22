import os, uuid, time
from flask import (
    Flask,
    abort,
    json,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    flash,
    send_from_directory,
)
from dotenv import load_dotenv
from sheets.sheets import read_sheet
from mailer import (
    mail,
    init_app,
)
from peminjaman_aset.document_generator import generate_pdf, generate_nomor_surat
from peminjaman_aset.drive_uploader import upload_file
from sheets.sheets_peminjaman_aset import append_peminjaman, get_last_sequence_this_month, get_all_peminjaman, find_row_by_id, update_row, get_sheet_headers, deduct_inventaris_stock, search_inventaris
from werkzeug.security import check_password_hash
from flask import request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from functools import wraps
from flask_wtf import CSRFProtect
from routes.routes_inventory_aset import inventaris_bp
from routes.routes_booking_ruangan import booking_ruangan_bp
from routes.routes_inventory_komp import inventory_labkomp_bp
from routes.routes_peminjaman import peminjaman_invlabkomp_bp



load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")
app.config["UPLOAD_FOLDER"] = os.getenv("UPLOAD_FOLDER", "static/uploads")
app.register_blueprint(inventaris_bp)
app.register_blueprint(booking_ruangan_bp)
app.register_blueprint(inventory_labkomp_bp)
app.register_blueprint(peminjaman_invlabkomp_bp)

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



# LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():
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

        # Proteksi timing attack (delay kecil)
        time.sleep(0.5)

        if user and check_password_hash(user["password_hash"], password):
            session["user"] = username
            return redirect(url_for("repository"))

        flash("Username atau password salah.")
        return redirect(url_for("login"))

    return render_template("login.html")

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
            "category": "Akademik",
            "color": "blue",
            "icon": '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"></path></svg>',
            "links": [
                {"title": "Kalender akademik", "url": url_for('booking_ruangan.jadwal_penggunaan'), "subtext": "Dokumen kalender akademik"},
                {"title": "Jadwal KBM", "url": "https://drive.google.com/file/d/1x56KSv5q4ihgWq5YGKeRqJauzJGoqL39/view?usp=sharing", "subtext": "Jadwal kegiatan belajar mengajar (KBM)"},
                {"title": "Rapor Digital Madrasah", "url": "#", "subtext": "Coming Soon", "disabled": True}
            ]
        },
        {
            "category": "Sekolah",
            "color": "emerald",
            "icon": '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 14l9-5-9-5-9 5 9 5z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 14l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 14l9-5-9-5-9 5 9 5zm0 0l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14zm-4 6v-7.5l4-2.222"/></svg>',
            "links": [
                {"title": "Presensi Sekolah", "url": "", "subtext": "Coming Soon", "disabled": True},
                {"title": "Presensi Diniyah", "url": "https://script.google.com/macros/s/AKfycbwv4zVl85NIghhD9qwkSkDuwpwQz4i8py2Erm-RSTWr0l-cm3BQOVs1k0i2ClEVze4W/exec", "subtext": "Formulir presensi kegiatan kelas diniyyah", "disabled": False},
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
                {"title": "Manajemen sarpras", "url": url_for('peminjaman_aset_landing'), "subtext": "Coming Soon", "disabled": True}
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
    return render_template('repository/landing_repository.html', repository_data=repository_data)



# landing page
@app.route("/e-labkomp")
def labkomp_landing():
    return render_template("landing.html")

# =======================
# PEMINJAMAN ASET SECTION (SARPRAS)
# =======================

# landing page peminjaman aset
@app.route("/peminjaman-aset")
def peminjaman_aset_landing():
    return render_template("peminjaman_aset/peminjaman_aset.html")

# Form peminjaman aset
@app.route("/peminjaman-aset/form")
def peminjaman_aset_form():
    return render_template("peminjaman_aset/peminjaman_aset_form.html")
 
# ==== Endpoint search barang (inventory) ====
@app.route("/peminjaman-aset/search-barang")
def search_barang_inventaris():
    q = request.args.get("q", "")
    if len(q.strip()) < 2:
        return jsonify({"items": []})

    rows = search_inventaris(q, limit=20)
    items = [{
        "id": r.get("id"),
        "nama_barang": r.get("nama_barang", ""),
        "merk": r.get("merk", ""),
        "kondisi": r.get("kondisi", ""),
        "lokasi": r.get("lokasi", ""),
        "sub_bidang": r.get("sub_bidang", ""),
        "jumlah_tersedia": r.get("jumlah_tersedia", 0)
    } for r in rows]

    items.sort(key=lambda x: x["jumlah_tersedia"] <= 0)
    return jsonify({"items": items})


# ==== Submit peminjaman aset (revisi) ====
@app.route("/peminjaman-aset/submit", methods=["POST"])
def submit_peminjaman_aset():
    form = request.form

    id_list = form.getlist("barang_id[]")
    nama_list = form.getlist("barang_nama[]")
    merk_list = form.getlist("barang_merk[]")
    jumlah_list = form.getlist("barang_jumlah[]")
    kondisi_list = form.getlist("barang_kondisi[]")

    barang = []
    for i in range(len(nama_list)):
        if not nama_list[i].strip():
            continue
        item_id = id_list[i].strip() if i < len(id_list) else ""
        if not item_id:
            return jsonify({
                "success": False,
                "message": f"Barang '{nama_list[i]}' belum dipilih dari daftar pencarian"
            }), 400
        try:
            jumlah = int(jumlah_list[i])
        except (ValueError, IndexError):
            return jsonify({"success": False, "message": f"Jumlah barang '{nama_list[i]}' tidak valid"}), 400
        if jumlah < 1:
            return jsonify({"success": False, "message": f"Jumlah barang '{nama_list[i]}' harus minimal 1"}), 400

        barang.append({
            "no": len(barang) + 1,
            "id": item_id,
            "nama": nama_list[i],
            "merk": merk_list[i] if i < len(merk_list) else "",
            "jumlah": jumlah,
            "kondisi": kondisi_list[i] if i < len(kondisi_list) else "",
        })

    nomor_surat = generate_nomor_surat(get_last_sequence_this_month)

    data = {
        "nomor_surat": nomor_surat,
        "nama": form.get("nama", "").strip(),
        "jenis_kelamin": form.get("jenis_kelamin", ""),
        "pekerjaan": form.get("pekerjaan", "").strip(),
        "alamat": form.get("alamat", "").strip(),
        "telepon": form.get("telepon", "").strip(),
        "no_identitas": form.get("no_identitas", "").strip(),
        "tujuan": form.get("tujuan", "").strip(),
        "lokasi_penggunaan": form.get("lokasi_penggunaan", "").strip(),
        "tgl_pinjam": form.get("tgl_pinjam", ""),
        "tgl_kembali": form.get("tgl_kembali", ""),
        "kota": form.get("kota", "Yogyakarta"),
        "tgl_surat": form.get("tgl_surat", ""),
        "nama_petugas": form.get("nama_petugas", "").strip(),
        "jaminan_identitas": form.get("jaminan_identitas") == "on",
        "jenis_identitas_jaminan": form.get("jenis_identitas_jaminan", "KTP/SIM/Paspor"),
        "jaminan_surat": form.get("jaminan_surat") == "on",
        "barang": barang,
    }

    required = ["nama", "pekerjaan", "alamat", "telepon", "no_identitas",
                "tujuan", "lokasi_penggunaan", "tgl_pinjam", "tgl_kembali", "nama_petugas"]
    missing = [f for f in required if not data[f]]
    if missing:
        return jsonify({"success": False, "message": f"Field belum lengkap: {', '.join(missing)}"}), 400
    if not barang:
        return jsonify({"success": False, "message": "Minimal isi 1 barang yang dipinjam"}), 400

    # ==== Validasi + kurangi stok SEBELUM simpan record peminjaman ====
    deductions = [{"id": b["id"], "jumlah": b["jumlah"]} for b in barang]
    ok, err_msg = deduct_inventaris_stock(deductions)
    if not ok:
        return jsonify({"success": False, "message": err_msg}), 400

    try:
        record_id = uuid.uuid4().hex
        pdf_placeholder = {"id": "", "webViewLink": ""}
        append_peminjaman(record_id, data, pdf_placeholder)

        ringkasan_url = url_for(
            "ringkasan_peminjaman_aset", record_id=record_id, _external=True
        )
        return jsonify({
            "success": True,
            "message": "Peminjaman berhasil diajukan. Silakan buka link ringkasan untuk konfirmasi.",
            "record_id": record_id,
            "ringkasan_url": ringkasan_url,
        })
    except Exception as e:
        app.logger.error(f"Gagal proses peminjaman aset: {e}")
        # stok sudah terlanjur dikurangi tapi record gagal disimpan -> perlu rollback manual
        return jsonify({
            "success": False,
            "message": "Terjadi kesalahan saat menyimpan data peminjaman. Stok mungkin sudah dikurangi, hubungi admin untuk pengecekan."
        }), 500
     

# Riwayat peminjaman aset
@app.route("/peminjaman-aset/riwayat")
# @login_required   # aktifkan sesuai setup auth yang sudah ada
def daftar_peminjaman_aset():
    rows = get_all_peminjaman()
    for r in rows:
        r["sudah_generate"] = bool(r.get("pdf_link"))
        r["ringkasan_url"] = url_for(
            "ringkasan_peminjaman_aset", record_id=r["record_id"]
        )
    return render_template("peminjaman_aset/daftar_peminjaman_aset.html", data=rows)

# Ringkasan peminjaman aset
@app.route("/peminjaman-aset/ringkasan/<record_id>")
def ringkasan_peminjaman_aset(record_id):
    row_index, row = find_row_by_id(record_id)
    if row is None:
        abort(404)

    headers = get_sheet_headers()
    data = dict(zip(headers, row))
    data["sudah_generate"] = bool(data.get("pdf_link"))

    try:
        data["barang"] = json.loads(data.get("barang_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        data["barang"] = []

    return render_template(
        "peminjaman_aset/ringkasan_peminjaman_aset.html",
        record_id=record_id,
        data=data,
    )

# generate PDF peminjaman aset
@app.route("/peminjaman-aset/ringkasan/<record_id>/generate", methods=["GET", "POST"])
def generate_pdf_peminjaman_aset(record_id):
    # Validasi persetujuan WAJIB dicek di server, jangan percaya JS saja
    setuju = request.form.get("setuju") == "on" or request.json and request.json.get("setuju")
    if not setuju:
        return jsonify({"success": False, "message": "Anda harus menyetujui ringkasan terlebih dahulu"}), 400
 
    row_index, row = find_row_by_id(record_id)
    if row is None:
        abort(404)
 
    headers = get_sheet_headers()
    data = dict(zip(headers, row))
 
    if data.get("pdf_link"):
        # sudah pernah digenerate sebelumnya, jangan generate ulang / dobel nomor surat
        return jsonify({
            "success": True,
            "message": "PDF sudah pernah dibuat sebelumnya",
            "pdf_link": data["pdf_link"],
        })
 
    try:
        # rekonstruksi struktur data yang dibutuhkan generate_pdf()
        # (barang disimpan sebagai JSON string di kolom sheet, lihat catatan penyimpanan)
        import json
        data["barang"] = json.loads(data.get("barang_json", "[]"))
        data["jaminan_identitas"] = str(data.get("jaminan_identitas")).lower() in ("true", "1", "on")
        data["jaminan_surat"] = str(data.get("jaminan_surat")).lower() in ("true", "1", "on")
 
        pdf_path = generate_pdf(data)
        base_name = f"Peminjaman_Aset_{data['nama'].replace(' ', '_')}"
        pdf_file = upload_file(pdf_path, "application/pdf", f"{base_name}.pdf")
        os.remove(pdf_path)
 
        # update kolom pdf_id & pdf_link di baris yang sama (index kolom sesuaikan urutan header)
        updated_row = list(row)
        idx_pdf_id = headers.index("pdf_id")
        idx_pdf_link = headers.index("pdf_link")
        # pastikan panjang row cukup
        while len(updated_row) <= max(idx_pdf_id, idx_pdf_link):
            updated_row.append("")
        updated_row[idx_pdf_id] = pdf_file["id"]
        updated_row[idx_pdf_link] = pdf_file["webViewLink"]
        update_row(row_index, updated_row)
 
        return jsonify({
            "success": True,
            "message": "PDF berhasil dibuat",
            "pdf_link": pdf_file["webViewLink"],
        })
    except Exception as e:
        app.logger.error(f"Gagal generate PDF peminjaman aset ({record_id}): {e}")
        return jsonify({"success": False, "message": "Gagal membuat PDF, coba lagi"}), 500

# Preview PDF peminjaman aset
@app.route("/peminjaman-aset/ringkasan/<record_id>/preview")
def preview_pdf_peminjaman_aset(record_id):
    row_index, row = find_row_by_id(record_id)
    if row is None:
        abort(404)
    headers = get_sheet_headers()
    data = dict(zip(headers, row))
    if not data.get("pdf_link"):
        flash("PDF belum dibuat. Silakan generate terlebih dahulu.")
        return redirect(url_for("ringkasan_peminjaman_aset", record_id=record_id))
    return redirect(data["pdf_link"])




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
