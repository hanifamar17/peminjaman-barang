import os, uuid, datetime
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
)
from dotenv import load_dotenv
from sheets import (
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
from mailer import (
    mail,
    init_app,
    send_loan_email,
    schedule_return_reminder,
    reminder_send_email,
)
from werkzeug.security import generate_password_hash, check_password_hash
from flask import request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from functools import wraps
import time
from flask_wtf import CSRFProtect

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")
app.config["UPLOAD_FOLDER"] = os.getenv("UPLOAD_FOLDER", "static/uploads")

IS_VERCEL = os.getenv("VERCEL") == "1"

ENABLE_SCHEDULER = (
    os.getenv("ENABLE_SCHEDULER", "false").lower() in ["true", "1"]
    and not IS_VERCEL
)

app.config["ENABLE_SCHEDULER"] = ENABLE_SCHEDULER

# =========================
# DETEKSI ENVIRONMENT
# =========================
IS_VERCEL = os.getenv("VERCEL") == "1"

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
            return redirect(url_for("landing"))

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
    return redirect(url_for("landing"))

# route: landing
@app.route("/")
def landing():
    return render_template("landing.html")


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
    return render_template("borrow.html")


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
    return render_template("return.html")


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
    from sheets import read_sheet

    rows = read_sheet("loans")
    if not rows:
        return render_template("history.html", loans=[])

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

    return render_template("history.html", loans=loans)


@app.route("/loan/<code>")
@login_required
def loan_detail(code):
    from sheets import read_sheet

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

    return render_template("loan_detail.html", loan=loan, receipt_url=receipt_url)


@app.route("/receipt/<code>")
def receipt(code):
    loan = get_loan_with_items(code)

    if not loan:
        abort(404)

    return render_template("receipt.html", loan=loan)


# =======================
# INVENTORY SECTION
# =======================
# Read inventory list
@app.route("/inventory")
@login_required
def inventory():
    items = get_inventory()
    return render_template("inventory/inventory.html", items=items)

# Add inventory item
@app.route("/inventory/add", methods=["GET", "POST"])
@login_required
def inventory_add():
    if request.method == "POST":
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
        return redirect(url_for("inventory"))

    return render_template("inventory/inventory_form.html")

# Edit inventory item
@app.route("/inventory/edit/<item_id>", methods=["GET", "POST"])
@login_required
def inventory_edit(item_id):
    items = get_inventory()
    item = next((x for x in items if x["item_id"] == item_id), None)

    if request.method == "POST":
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
        return redirect(url_for("inventory"))

    return render_template("inventory/inventory_form.html", item=item)

# Delete inventory item
@app.route("/inventory/delete/<item_id>", methods=["GET", "POST"])
@login_required
def inventory_delete(item_id):
    items = get_inventory()
    item = next((x for x in items if x["item_id"] == item_id), None)

    if request.method == "POST":
        delete_inventory(item_id)
        return redirect(url_for("inventory"))

    return render_template("inventory/inventory_delete.html", item=item)




# =======================
# STATIC FILE UPLOAD
# =======================
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

#URL
@app.context_processor
def inject_base_url():
    from sheets import read_sheet

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
