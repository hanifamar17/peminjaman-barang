import os, uuid, datetime, time
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
from sheets.sheets import (
    generate_item_id,
    add_inventory,
    delete_inventory,
    get_inventory,
    append_loan,
    get_loan_with_items,
    update_inventory,
    update_stock,
    find_loan_by_code,
    update_loan_status,
    read_sheet,
)
from sheets.sheets_jadwal import get_jadwal, get_kalender_akademik
from mailer import (
    mail,
    init_app,
    send_loan_email,
    schedule_return_reminder,
    reminder_send_email,
)
from peminjaman_aset.document_generator import generate_pdf, generate_nomor_surat
from peminjaman_aset.drive_uploader import upload_file, delete_drive_file
from sheets.sheets_peminjaman_aset import append_peminjaman, get_last_sequence_this_month, get_all_peminjaman, find_row_by_id, update_row, get_sheet_headers, deduct_inventaris_stock, get_all_inventaris, search_inventaris
from werkzeug.security import generate_password_hash, check_password_hash
from flask import request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from functools import wraps
from flask_wtf import CSRFProtect
from routes_inventaris import inventaris_bp


load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")
app.config["UPLOAD_FOLDER"] = os.getenv("UPLOAD_FOLDER", "static/uploads")
app.register_blueprint(inventaris_bp)

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
                {"title": "Kalender akademik", "url": url_for('jadwal_penggunaan'), "subtext": "Dokumen kalender akademik"},
                {"title": "Jadwal KBM", "url": "https://drive.google.com/file/d/1x56KSv5q4ihgWq5YGKeRqJauzJGoqL39/view?usp=sharing", "subtext": "Jadwal kegiatan belajar mengajar (KBM)"},
            ]
        },
        {
            "category": "Pengajaran",
            "color": "emerald",
            "icon": '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>',
            "links": [
                {"title": "Jurnal Mengajar Harian Guru", "url": "https://docs.google.com/forms/d/e/1FAIpQLSdGZ7jXITewg7GQM7zoSLmPEUglqbMj3TwGFGWZ46HuGSCotg/viewform", "subtext": "Formulir jurnal mengajar harian guru"},
                {"title": "Presensi Diniyah", "url": "https://script.google.com/macros/s/AKfycbwv4zVl85NIghhD9qwkSkDuwpwQz4i8py2Erm-RSTWr0l-cm3BQOVs1k0i2ClEVze4W/exec", "subtext": "Formulir presensi kegiatan diniyah"},
                {"title": "Jurnal Ekstrakurikuler", "url": "https://docs.google.com/forms/d/e/1FAIpQLSfu0TYIpe67BVyhjXyaSdkPj5ZdvnynCEB2TXrNnMjuSdqxJQ/viewform", "subtext": "Formulir jurnal kegiatan ekstrakurikuler"},
                {"title": "Presensi Ekstrakurikuler", "url": "https://script.google.com/macros/s/AKfycbxiuxLz2L7ob5jAG9KUKwT2-uXDtzhGG9VCuBfky6-rLp8cHsv9tG3OW3SVck8ny8dh/exec", "subtext": "Formulir presensi kegiatan ekstrakurikuler"},
                {"title": "Rapor Digital Madrasah", "url": "#", "subtext": "Coming Soon", "disabled": True}
            ]
        },
        {
            "category": "Lab Komp",
            "color": "indigo",
            "icon": '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>',
            "links": [
                {"title": "Inventaris Lab Komp", "url": url_for('inventory_landing'), "subtext": "Master data inventaris lab komputer"},
                {"title": "Peminjaman Barang", "url": url_for('peminjaman_landing'), "subtext": "Pengelolaan peminjaman barang lab komputer"},
                {"title": "Peminjaman Ruangan", "url": url_for('booking_landing'), "subtext": "Pengelolaan peminjaman ruangan lab komputer"},
            ]
        },
        {
            "category": "Asrama",
            "color": "violet",
            "icon": '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"></path></svg>',
            "links": [
                {"title": "Presensi kegiatan Asrama", "url": "https://presensimanu.my.id/login", "subtext": "Formulir presensi kegiatan asrama"},
                {"title": "Berita Acara Persidangan Santri", "url": "https://docs.google.com/forms/d/e/1FAIpQLSc5OG8Kf879_mOgmQNxIRuTfH3beYR_DZ54waDaDjWudECLtQ/viewform", "subtext": "Formulir berita acara persidangan santri"},
                {"title": "Buku Catatan Santri", "url": "https://docs.google.com/spreadsheets/d/10smJykmE_TgM4JfR5eigez4bUa5LDEgEtxjnyZJyA1Q/edit?gid=0#gid=0", "subtext": "Formulir buku catatan santri"},
                {"title": "Formulir Perizinan", "url": "https://tally.so/r/w5Gqz6", "subtext": "Formulir perizinan kegiatan"},
                {"title": "Jurnal Perizinan", "url": "https://datastudio.google.com/u/0/reporting/73d02ac9-ca68-479f-9fd3-e1f40834dc6b/page/OTbEE", "subtext": "Formulir jurnal perizinan"}
            ]
        },
        {
            "category": "Sarpras",
            "color": "rose",
            "icon": '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>',
            "links": [
                {"title": "Manajemen sarpras", "url": url_for('peminjaman_aset_landing'), "subtext": "Coming Soon", "disabled": True}
            ]
        }
    ]
    return render_template('repository/landing_repository.html', repository_data=repository_data)

# landing page
@app.route("/e-labkomp")
def labkomp_landing():
    return render_template("landing.html")

# Landing page peminjaman
@app.route("/peminjaman")
def peminjaman_landing():
    return render_template("peminjaman/landing_peminjaman.html")

# Landing page inventory
@app.route("/inventory")
def inventory_landing():
    return render_template("inventory/landing_inventory.html")


# API: search inventory by q
@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip().lower()
    items = get_inventory()
    if not q:
        return jsonify(items[:20])
    results = [
        i
        for i in items
        if q in i.get("name", "").lower() or q in i.get("description", "").lower()
    ]
    return jsonify(results[:50])


# =======================
# BORROWING PAGE
# =======================
@app.route("/borrow")
@login_required
def borrow():
    return render_template("peminjaman/borrow.html")


# submit borrow
@app.route("/borrow/submit", methods=["POST"])
def borrow_submit():
    data = request.get_json()
    note = data.get("note", "")

    if not data:
        return jsonify({"ok": False, "error": "Data tidak valid"}), 400

    items = data.get("items", [])
    if not items:
        return jsonify({"ok": False, "error": "Minimal pilih 1 barang"}), 400

    required = ["borrower_name", "borrower_email", "loan_date", "return_date"]
    for r in required:
        if not data.get(r):
            return jsonify({"ok": False, "error": f"{r} wajib diisi"}), 400

    now = datetime.datetime.now()
    code = now.strftime("LAB-%d%m%y-%H%M")
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # =====================
    # SIMPAN SETIAP BARANG
    # =====================
    for item in items:
        qty = int(item.get("qty", 1))

        loan_row = [
            code,
            item["item_id"],
            item["name"],
            data["borrower_name"],
            data["borrower_email"],
            "",
            str(qty),
            data["loan_date"],
            data["return_date"],
            "dipinjam",
            note,
            created_at,
            "",
        ]

        append_loan(loan_row)

        # update stok per item
        update_stock(item["item_id"], -qty)

    # kirim email konfirmasi peminjaman
    receipt_url = url_for('receipt', code=code, _external=True)
    try:
        send_loan_email(
            [data["borrower_email"]],
            code=code,
            borrower_name=data["borrower_name"],
            items=items,
            loan_date=data["loan_date"],
            return_date=data["return_date"],
            receipt_url=receipt_url,
            note=note,
        )
    except Exception as e:
        app.logger.warning(f"Email gagal dikirim: {e}")

    # jadwalkan reminder H-1
    try:
        return_dt = datetime.datetime.fromisoformat(data['return_date'])
        remind_at = return_dt - datetime.timedelta(days=1)
        if remind_at > datetime.datetime.utcnow():
            schedule_return_reminder(
                job_id=f'reminder-{code}',
                run_at_dt=remind_at,
                func=reminder_send_email,
                args=(
                    [data['borrower_email']],
                    f'Pengingat Pengembalian ({code})',
                    f'Besok adalah batas pengembalian barang Anda ({receipt_url})'
                )
            )
    except Exception as e:
        app.logger.warning(f'Reminder gagal dijadwalkan: {e}')

    return jsonify({"ok": True, "code": code})


# =======================
# HALAMAN PENGEMBALIAN
# =======================
@app.route("/return")
@login_required
def return_page():
    return render_template("peminjaman/return.html")


# ambil data peminjaman berdasarkan kode
@app.route("/api/loan/<code>")
def api_loan(code):
    loan = get_loan_with_items(code)

    if not loan:
        return jsonify(ok=False, error="Peminjaman tidak ditemukan")

    return jsonify(ok=True, loan=loan)


# submit pengembalian
@app.route("/return/submit", methods=["POST"])
def return_submit():
    code = request.form.get("code")
    proof = request.form.get("proof", "")

    loan = get_loan_with_items(code)
    if not loan:
        return jsonify(ok=False, error="Peminjaman tidak ditemukan")

    # loop SEMUA barang dalam 1 kode peminjaman
    for item in loan["items"]:
        item_id = item["item_id"]
        qty = int(item["qty"])

        # 1️⃣ update status per item
        update_loan_status(code, item_id, "dikembalikan", proof)

        # 2️⃣ kembalikan stok per item
        update_stock(item_id, qty)

    return jsonify(ok=True)


# =======================
# RIWAYAT PEMINJAMAN
# =======================
@app.route("/history")
@login_required
def history():
    from sheets.sheets import read_sheet

    rows = read_sheet("loans")
    if not rows:
        return render_template("peminjaman/history.html", loans=[])

    headers = rows[0]
    data = [dict(zip(headers, r)) for r in rows[1:]]

    grouped = {}
    for d in data:
        code = d["code"]
        if code not in grouped:
            grouped[code] = {
                "code": code,
                "borrower_name": d["borrower_name"],
                "status": d["status"],
                "loan_date": d["loan_date"],
                "created_at": d.get("created_at"),  # ⬅penting
                "items": [],
            }
        grouped[code]["items"].append(d["item_name"])

    loans = []
    for g in grouped.values():
        loans.append({
            "code": g["code"],
            "borrower_name": g["borrower_name"],
            "status": g["status"],
            "loan_date": g["loan_date"],
            "created_at": g["created_at"],
            "item_name": ", ".join(g["items"]),
        })

    # SORT TERKINI DI ATAS
    loans.sort(key=lambda x: x["created_at"] or "", reverse=True)

    return render_template("peminjaman/history.html", loans=loans)


@app.route("/loan/<code>")
@login_required
def loan_detail(code):
    from sheets.sheets import read_sheet

    rows = read_sheet("loans")
    headers = rows[0]
    data = [dict(zip(headers, r)) for r in rows[1:] if r[headers.index("code")] == code]
    receipt_url = url_for("receipt", code=code, _external=True)

    if not data:
        abort(404)

    loan = {
        "code": code,
        "borrower_name": data[0]["borrower_name"],
        "loan_date": data[0]["loan_date"],
        "return_date": data[0]["return_date"],
        "status": data[0]["status"],
        "note": data[0]["note"],
        "borrower_email": data[0]["borrower_email"],
        "data": data,
    }

    return render_template("peminjaman/loan_detail.html", loan=loan, receipt_url=receipt_url)


@app.route("/receipt/<code>")
def receipt(code):
    loan = get_loan_with_items(code)

    if not loan:
        abort(404)

    return render_template("peminjaman/receipt.html", loan=loan)


# =======================
# INVENTORY SECTION
# =======================
# Read inventory list
@app.route("/inventory/list")
@login_required
def inventory_list():
    items = get_inventory()
    return render_template("inventory/inventory.html", items=items)

# Add inventory item
@app.route("/inventory/add", methods=["GET", "POST"])
@login_required
def inventory_add():
    if request.method == "POST":
        try:
            data = {
                "item_id": generate_item_id(),
                "name": request.form["name"],
                "stock": int(request.form["stock"]),
                "uom": request.form["uom"],
                "condition": request.form["condition"],
                "location": request.form["location"],
                "note": request.form["note"]
            }
            add_inventory(data)
            
            # Cek jika request datang dari AJAX (JavaScript Fetch)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"ok": True, "message": "Barang berhasil ditambahkan"})
            
            return redirect(url_for("inventory_list"))
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"ok": False, "error": str(e)}), 400
            return str(e), 400

    return render_template("inventory/inventory_form.html", item=None)

@app.route("/inventory/edit/<item_id>", methods=["GET", "POST"])
@login_required
def inventory_edit(item_id):
    items = get_inventory()
    item = next((x for x in items if x["item_id"] == item_id), None)

    if request.method == "POST":
        try:
            updated_data = {
                "item_id": item_id,
                "name": request.form["name"],
                "stock": int(request.form["stock"]),
                "uom": request.form["uom"],
                "condition": request.form["condition"],
                "location": request.form["location"],
                "note": request.form["note"]
            }
            update_inventory(item_id, updated_data)

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"ok": True, "message": "Barang diperbarui"})
            
            return redirect(url_for("inventory_list"))
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"ok": False, "error": str(e)}), 400
            return str(e), 400

    return render_template("inventory/inventory_form.html", item=item)

# Delete inventory item
@app.route("/inventory/delete/<item_id>", methods=["GET", "POST"])
@login_required
def inventory_delete(item_id):
    items = get_inventory()
    item = next((x for x in items if x["item_id"] == item_id), None)

    if request.method == "POST":
        try:
            delete_inventory(item_id)
        
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"ok": True, "message": "Barang berhasil dihapus"})
            
            return redirect(url_for("inventory_list"))
        except Exception as e:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"ok": False, "error": str(e)}), 400
            return str(e), 400

    return render_template("inventory/inventory_delete.html", item=item)





# =======================
# JADWAL PENGGUNAAN LAB (booking ruangan)
# =======================
@app.route("/booking-ruangan")
def booking_landing():
    return render_template("booking_ruangan/booking_landing.html")

@app.route("/booking-ruangan/prosedur")
def booking_prosedur():
    return render_template("booking_ruangan/booking_prosedur.html")

@app.route("/booking-ruangan/jadwal")
def jadwal_penggunaan():
    jadwal = get_jadwal()
    booking_form_url = "https://s.id/booking-lab-komp"

    jadwal_json = [
        {
            "nama_pemesan": j["nama_pemesan"],
            "nama_kegiatan": j["nama_kegiatan"],
            "tanggal": j["tanggal"],
            "tanggal_iso": j.get("tanggal_iso"),
            "waktu_mulai_raw": j["waktu_mulai_raw"],
            "waktu_selesai_raw": j["waktu_selesai_raw"],
            "catatan_tambahan": j.get("catatan_tambahan", ""),
        }
        for j in jadwal
    ]

    return render_template(
        "booking_ruangan/jadwal_penggunaan.html",
        jadwal=jadwal,
        jadwal_json=jadwal_json,
        booking_form_url=booking_form_url,
        kalender_json=get_kalender_akademik()
    )


# API: jadwal dalam format JSON (opsional, untuk fetch dari JS/kalender)
@app.route("/api/jadwal")
def api_jadwal():
    jadwal = get_jadwal()
    data = [
        {
            "nama_pemesan": j["nama_pemesan"],
            "nama_kegiatan": j["nama_kegiatan"],
            "tanggal": j["tanggal"],
            "waktu_mulai": j["waktu_mulai_raw"],
            "waktu_selesai": j["waktu_selesai_raw"],
            "conflict": j["conflict"],
        }
        for j in jadwal
    ]
    return jsonify(data)

@app.route("/booking-ruangan/form")
def booking_form_page():
    booking_form_url = "https://docs.google.com/forms/d/e/1FAIpQLSc7oMnechEl_sMkKAtWGsHsES9LKhZYirz9qUXErYi588lfgg/viewform"
    # Ganti dengan URL embed asli dari Google Form kamu
    # (Format: https://docs.google.com/forms/d/e/FORM_ID/viewform?embedded=true)
    booking_form_embed_url = os.getenv("BOOKING_FORM_EMBED_URL", booking_form_url)
    return render_template(
        "booking_ruangan/form_peminjaman.html",
        booking_form_url=booking_form_url,
        booking_form_embed_url=booking_form_embed_url,
    )



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
