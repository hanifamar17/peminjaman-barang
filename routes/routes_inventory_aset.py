"""
routes_inventaris.py
CRUD inventaris + endpoint search (dipakai autocomplete di form peminjaman) khusus untuk SARPRAS.
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, abort, flash, json, current_app
from sheets.sheets_peminjaman_aset import (
    get_all_inventaris,
    find_inventaris_by_id,
    search_inventaris,
    create_inventaris,
    update_inventaris,
    delete_inventaris,
    get_loan_by_code,
    update_items_return,
    _get_inventaris_raw,
    get_stock_map,
    update_stock_return_batch,
)
from sheets.sheets_peminjaman_aset import append_peminjaman, get_last_sequence_this_month, get_all_peminjaman, find_row_by_id, update_row, get_sheet_headers, deduct_inventaris_stock, search_inventaris
from peminjaman_aset.document_generator import generate_pdf, generate_nomor_surat
from peminjaman_aset.drive_uploader import upload_file
from routes.decorators import login_required
import os, uuid


inventaris_bp = Blueprint("inventaris", __name__, url_prefix="/peminjaman-aset")

KONDISI_OPTIONS = ["Baik", "Rusak Ringan", "Rusak Berat"]
SUMBER_DANA_OPTIONS = ["BOS", "BOSDA", "Hibah", "Lainnya"]
SUB_BIDANG_OPTIONS = ["Perpustakaan", "Lab IPA", "Lab Komputer", "Asrama", "Madrasah"]


# landing page peminjaman aset
@inventaris_bp.route("/")
def peminjaman_aset_landing():
    return render_template("peminjaman_aset/peminjaman_aset.html")

# ---------------------------------------------------------------------------
# LIST + CREATE
# ---------------------------------------------------------------------------
@inventaris_bp.route("/inventaris")
@login_required
def list_inventaris():
    data = get_all_inventaris()
    return render_template(
        "peminjaman_aset/inventory/daftar_inventaris_sarpras.html",
        data=data,
    )


@inventaris_bp.route("/inventaris/tambah", methods=["GET", "POST"])
@login_required
def tambah_inventaris():
    if request.method == "GET":
        return render_template(
            "peminjaman_aset/inventory/inventaris_sarpras_form.html",
            mode="tambah",
            item=None,
            kondisi_options=KONDISI_OPTIONS,
            sumber_dana_options=SUMBER_DANA_OPTIONS,
            sub_bidang_options=SUB_BIDANG_OPTIONS,
        )
 
    form = request.form
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    
    jumlah_total = int(form.get("jumlah_total", 0))
 
    data = {
        "nama_barang": form.get("nama_barang", "").strip(),
        "merk": form.get("merk", "").strip(),
        "kondisi": form.get("kondisi", "Baik"),
        "lokasi": form.get("lokasi", "").strip(),
        "tahun_pengadaan": form.get("tahun_pengadaan", "").strip(),
        "sumber_dana": form.get("sumber_dana", ""),
        "sub_bidang": form.get("sub_bidang", ""),
        "jumlah_total": jumlah_total,
    }
    item_id = create_inventaris(data)
 
    if is_ajax:
        return jsonify({"ok": True, "item_id": item_id})
    flash(f"Barang {item_id} berhasil ditambahkan")
    return render_template("peminjaman_aset/inventory/inventaris_sarpras_form.html")


# ---------------------------------------------------------------------------
# EDIT
# ---------------------------------------------------------------------------
@inventaris_bp.route("/inventaris/<item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_inventaris(item_id):
    row_index, row = find_inventaris_by_id(item_id)
    if row is None:
        abort(404)
 
    if request.method == "GET":
        item = dict(zip(
            ["id", "nama_barang", "merk", "kondisi", "lokasi", "tahun_pengadaan",
             "sumber_dana", "sub_bidang", "jumlah_total", "jumlah_dipinjam",
             "created_at", "last_updated"],
            row,
        ))
        return render_template(
            "peminjaman_aset/inventory/inventaris_sarpras_form.html",
            mode="edit",
            item=item,
            kondisi_options=KONDISI_OPTIONS,
            sumber_dana_options=SUMBER_DANA_OPTIONS,
            sub_bidang_options=SUB_BIDANG_OPTIONS,
        )
 
    form = request.form
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
 
    
    jumlah_total = int(form.get("jumlah_total", 0))
 
    data = {
        "nama_barang": form.get("nama_barang", "").strip(),
        "merk": form.get("merk", "").strip(),
        "kondisi": form.get("kondisi", "Baik"),
        "lokasi": form.get("lokasi", "").strip(),
        "tahun_pengadaan": form.get("tahun_pengadaan", "").strip(),
        "sumber_dana": form.get("sumber_dana", ""),
        "sub_bidang": form.get("sub_bidang", ""),
        "jumlah_total": jumlah_total,
    }
    update_inventaris(item_id, data)
 
    if is_ajax:
        return jsonify({"ok": True, "item_id": item_id})
    flash(f"Barang {item_id} berhasil diperbarui")
    return render_template("peminjaman_aset/inventory/inventaris_sarpras_form.html")


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------
@inventaris_bp.route("/inventaris/<item_id>/hapus", methods=["GET", "POST"])
@login_required
def hapus_inventaris(item_id):
    # Ambil data dan posisi baris (hanya 1x panggil API untuk GET maupun POST)
    row_index, row = find_inventaris_by_id(item_id)
    if row is None:
        abort(404)

    # Memetakan row ke dalam dictionary untuk kebutuhan template HTML
    headers = [
        "id", "nama_barang", "merk", "kondisi", "lokasi", "tahun_pengadaan",
        "sumber_dana", "sub_bidang", "jumlah_total", "jumlah_dipinjam",
        "created_at", "last_updated"
    ]
    item = dict(zip(headers, row))

    if request.method == "GET":
        return render_template("peminjaman_aset/inventory/inventaris_sarpras_hapus.html", item=item)

    # JIKA METHOD POST (Tombol "Ya, Hapus" ditekan)
    # Langsung kirim row_index yang sudah didapatkan di atas
    ok = delete_inventaris(item_id, row_index=row_index)
    
    if ok:
        flash(f"Barang '{item['nama_barang']}' (ID: {item_id}) berhasil dihapus.", "success")
    else:
        flash("Gagal menghapus barang. Terjadi kesalahan pada sistem.", "danger")
        
    return redirect(url_for("inventaris.list_inventaris"))


# ---------------------------------------------------------------------------
# SEARCH (JSON) - dipakai autocomplete form peminjaman
# ---------------------------------------------------------------------------
@inventaris_bp.route("/inventaris/search")
def search_inventaris_api():
    q = request.args.get("q", "")
    results = search_inventaris(q, limit=10)
    return jsonify([
        {
            "id": r["id"],
            "nama_barang": r["nama_barang"],
            "merk": r.get("merk", ""),
            "jumlah_tersedia": r["jumlah_tersedia"],
        }
        for r in results
    ])


# =======================
# PEMINJAMAN ASET SECTION (SARPRAS)
# =======================
# Form peminjaman aset
@inventaris_bp.route("/form")
def peminjaman_aset_form():
    return render_template("peminjaman_aset/peminjaman_aset_form.html")
 
# ==== Endpoint search barang (inventory) ====
@inventaris_bp.route("/search-barang")
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
@inventaris_bp.route("/submit", methods=["POST"])
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
            "dikembalikan": False,
            "tgl_dikembalikan": "",
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
            "inventaris.ringkasan_peminjaman_aset", record_id=record_id, _external=True
        )
        return jsonify({
            "success": True,
            "message": "Peminjaman berhasil diajukan. Silakan buka link ringkasan untuk konfirmasi.",
            "record_id": record_id,
            "ringkasan_url": ringkasan_url,
        })
    except Exception as e:
        current_app.logger.error(f"Gagal proses peminjaman aset: {e}")
        # stok sudah terlanjur dikurangi tapi record gagal disimpan -> perlu rollback manual
        return jsonify({
            "success": False,
            "message": "Terjadi kesalahan saat menyimpan data peminjaman. Stok mungkin sudah dikurangi, hubungi admin untuk pengecekan."
        }), 500
     

# Riwayat peminjaman aset
@inventaris_bp.route("/riwayat")
@login_required
def daftar_peminjaman_aset():
    rows = get_all_peminjaman()
    for r in rows:
        r["sudah_generate"] = bool(r.get("pdf_link"))
        r["ringkasan_url"] = url_for(
            "inventaris.ringkasan_peminjaman_aset", record_id=r["record_id"]
        )
    return render_template("peminjaman_aset/daftar_peminjaman_aset.html", data=rows)

# Ringkasan peminjaman aset
@inventaris_bp.route("/ringkasan/<record_id>")
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
@inventaris_bp.route("/ringkasan/<record_id>/generate", methods=["GET", "POST"])
def generate_pdf_peminjaman_aset(record_id):
    # Validasi persetujuan WAJIB dicek di server, jangan percaya JS saja
    setuju = request.form.get("setuju") == "on" or request.json and request.json.get("setuju")
    if not setuju:
        return jsonify({"success": False, "message": "Anda harus menyetujui ringkasan terlebih dahulu"}), 400
 
    row_index, row = find_row_by_id(record_id)
    if row is None:
        abort(404)
 
    headers = get_sheet_headers()

    current_app.logger.info(f"HEADERS: {headers}")
    current_app.logger.info(f"ROW: {row}")
    data = dict(zip(headers, row))
    current_app.logger.info(f"NOMOR_SURAT RAW: {data.get('nomor_surat')!r}")
    
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
        data["barang"] = json.loads(data.get("barang_json", "[]"))
        data["jaminan_identitas"] = str(data.get("jaminan_identitas")).lower() in ("true", "1", "on")
        data["jaminan_surat"] = str(data.get("jaminan_surat")).lower() in ("true", "1", "on")
 
        pdf_path = generate_pdf(data)
        tgl_surat_clean = str(data.get("tgl_surat", "")).replace("/", "-")
        nomor_surat_clean = str(data.get("nomor_surat", "")).replace("/", "-")
        base_name = f"{nomor_surat_clean}_{data['nama'].replace(' ', '_')}"
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
        current_app.logger.error(f"Gagal generate PDF peminjaman aset ({record_id}): {e}")
        return jsonify({"success": False, "message": "Gagal membuat PDF, coba lagi"}), 500

# Preview PDF peminjaman aset
@inventaris_bp.route("/ringkasan/<record_id>/preview")
def preview_pdf_peminjaman_aset(record_id):
    row_index, row = find_row_by_id(record_id)
    if row is None:
        abort(404)
    headers = get_sheet_headers()
    data = dict(zip(headers, row))
    if not data.get("pdf_link"):
        flash("PDF belum dibuat. Silakan generate terlebih dahulu.")
        return redirect(url_for("inventaris.ringkasan_peminjaman_aset", record_id=record_id))
    return redirect(data["pdf_link"])

@inventaris_bp.route("/api/loan/<path:code>")
def api_loan(code):
    loan = get_loan_by_code(code.strip().upper())
    if not loan:
        return jsonify(ok=False, error="Tidak ditemukan")

    item_ids = [i.get("id") for i in loan["items"]]
    stock_map = get_stock_map(item_ids)

    all_returned = all(i.get("dikembalikan") for i in loan["items"]) if loan["items"] else False

    return jsonify(ok=True, loan={
        "code": loan["nomor_surat"],
        "borrower_name": loan.get("nama", "-"),
        "loan_date": loan.get("tgl_pinjam", "-"),
        "return_date": loan.get("tgl_kembali", "-"),
        "note": loan.get("tujuan", "-"),
        "status": "dikembalikan" if all_returned else "dipinjam",
        "items": [
            {
                "id": i.get("id"),
                "item_name": i.get("nama"),
                "merk": i.get("merk"),
                "qty": i.get("jumlah"),
                "dikembalikan": bool(i.get("dikembalikan")),
            }
            for i in loan["items"]
        ],
    })


@inventaris_bp.route("/return")
@login_required
def return_aset():
    return render_template(
            "peminjaman_aset/peminjaman_aset_return.html")


@inventaris_bp.route("/return/submit", methods=["POST"])
def return_submit():
    code = (request.form.get("code") or "").strip()
    catatan = (request.form.get("catatan") or "").strip()

    loan = get_loan_by_code(code)
    if not loan:
        return jsonify(ok=False, error="Peminjaman tidak ditemukan")

    pending_ids = [i.get("id") for i in loan["items"] if not i.get("dikembalikan")]
    if not pending_ids:
        return jsonify(ok=False, error="Semua barang sudah dikembalikan")

    ok, deltas = update_items_return(loan["nomor_surat"], pending_ids, catatan)
    if not ok:
        return jsonify(ok=False, error="Gagal update")

    update_stock_return_batch(deltas)

    return jsonify(ok=True)

# Daftarkan blueprint di app.py:
#   from routes_inventaris import inventaris_bp
#   app.register_blueprint(inventaris_bp)