import datetime
from flask import Blueprint, abort, abort, render_template, request, jsonify, url_for, current_app
from routes.decorators import login_required
from sheets.sheets_inventory_labkomp import (
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


peminjaman_invlabkomp_bp = Blueprint("peminjaman_invlabkomp", __name__, url_prefix="/peminjaman")


# =======================
# BORROWING PAGE
# =======================
# Landing page peminjaman
@peminjaman_invlabkomp_bp.route("/")
def peminjaman_landing():
    return render_template("peminjaman/landing_peminjaman.html")


@peminjaman_invlabkomp_bp.route("/borrow")
@login_required
def borrow():
    return render_template("peminjaman/borrow.html")


# submit borrow
@peminjaman_invlabkomp_bp.route("/borrow/submit", methods=["POST"])
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
    receipt_url = url_for('peminjaman_invlabkomp.receipt', code=code, _external=True)
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
        current_app.logger.warning(f"Email gagal dikirim: {e}")

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
        current_app.logger.warning(f'Reminder gagal dijadwalkan: {e}')

    return jsonify({"ok": True, "code": code})


# =======================
# HALAMAN PENGEMBALIAN
# =======================
@peminjaman_invlabkomp_bp.route("/return")
@login_required
def return_page():
    return render_template("peminjaman/return.html")


# ambil data peminjaman berdasarkan kode
@peminjaman_invlabkomp_bp.route("/api/loan/<code>")
def api_loan(code):
    loan = get_loan_with_items(code)

    if not loan:
        return jsonify(ok=False, error="Peminjaman tidak ditemukan")

    return jsonify(ok=True, loan=loan)


# submit pengembalian
@peminjaman_invlabkomp_bp.route("/return/submit", methods=["POST"])
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

        # 1️ update status per item
        update_loan_status(code, item_id, "dikembalikan", proof)

        # 2️ kembalikan stok per item
        update_stock(item_id, qty)

    return jsonify(ok=True)


# =======================
# RIWAYAT PEMINJAMAN
# =======================
@peminjaman_invlabkomp_bp.route("/history")
@login_required
def history():
    from sheets.sheets_inventory_labkomp import read_sheet

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


@peminjaman_invlabkomp_bp.route("/loan/<code>")
@login_required
def loan_detail(code):
    from sheets.sheets_inventory_labkomp import read_sheet

    rows = read_sheet("loans")
    headers = rows[0]
    data = [dict(zip(headers, r)) for r in rows[1:] if r[headers.index("code")] == code]
    receipt_url = url_for("peminjaman_invlabkomp.receipt", code=code, _external=True)

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


@peminjaman_invlabkomp_bp.route("/receipt/<code>")
def receipt(code):
    loan = get_loan_with_items(code)

    if not loan:
        abort(404)

    return render_template("peminjaman/receipt.html", loan=loan)