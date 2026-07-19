"""
routes_inventaris.py
CRUD inventaris + endpoint search (dipakai autocomplete di form peminjaman) khusus untuk SARPRAS.
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, abort, flash

from sheets.sheets_peminjaman_aset import (
    get_all_inventaris,
    find_inventaris_by_id,
    search_inventaris,
    create_inventaris,
    update_inventaris,
    delete_inventaris,
)

inventaris_bp = Blueprint("inventaris", __name__, url_prefix="/peminjaman-aset/inventaris")

KONDISI_OPTIONS = ["Baik", "Rusak Ringan", "Rusak Berat"]
SUMBER_DANA_OPTIONS = ["BOS", "BOSDA", "Hibah", "Lainnya"]
SUB_BIDANG_OPTIONS = ["Perpustakaan", "Lab IPA", "Lab Komputer", "Asrama", "Madrasah"]


# ---------------------------------------------------------------------------
# LIST + CREATE
# ---------------------------------------------------------------------------
@inventaris_bp.route("/")
# @login_required
def list_inventaris():
    data = get_all_inventaris()
    return render_template(
        "peminjaman_aset/inventory/daftar_inventaris_sarpras.html",
        data=data,
    )


@inventaris_bp.route("/tambah", methods=["GET", "POST"])
# @login_required
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
@inventaris_bp.route("/<item_id>/edit", methods=["GET", "POST"])
# @login_required
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
@inventaris_bp.route("/<item_id>/hapus", methods=["GET", "POST"])
# @login_required
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
@inventaris_bp.route("/search")
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

# Daftarkan blueprint di app.py:
#   from routes_inventaris import inventaris_bp
#   app.register_blueprint(inventaris_bp)