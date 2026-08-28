import re

from flask import Blueprint, session, request, redirect, url_for, abort, jsonify, render_template
from routes.decorators import login_required, role_required
from sheets.sheets_perizinan import (
    ENUM_DURASI, ENUM_STATUS_PETUGAS, MAX_ALASAN, MAX_CATATAN, MAX_NAMA, MAX_PETUGAS,
    rate_limit_check, validate_enum, sanitize_text, validate_nisn_format,
    check_duplikat_aktif, gen_id_perizinan, now_iso, get_riwayat, get_riwayat_detail, get_izin_aktif_hari_ini,
    find_siswa_by_nisn, get_data_siswa, simpan_perizinan_langsung, simpan_pengajuan, get_pengajuan,
    get_pengajuan_detail, proses_acc, get_surat_data, get_wali_kelas_untuk_siswa, validate_rentang_manual,
    get_list_kelas
    )

perizinan_bp = Blueprint("perizinan", __name__, url_prefix="/perizinan")

@perizinan_bp.route("/")
@login_required
def index():
    return render_template("perizinan/perizinan_landing.html")
 
# DASHBOARD
@perizinan_bp.route("/dashboard")
@login_required
def dashboard():
    tanggal, items = get_izin_aktif_hari_ini()
    return render_template("perizinan/perizinan_dashboard.html", tanggal=tanggal, items=items)
 
# RIWAYAT
@perizinan_bp.route("/riwayat", methods=["GET"])
@login_required
def riwayat_list():
    kelas_selected = request.args.get("kelas", "").strip()
    tgl_mulai = request.args.get("tgl_mulai", "").strip()
    tgl_selesai = request.args.get("tgl_selesai", "").strip()
    
    # Auto-extract bulan dari tgl_mulai jika bulan tidak dikirim spesifik
    bulan = request.args.get("bulan", "").strip()
    if not bulan and tgl_mulai and len(tgl_mulai) >= 7:
        bulan = tgl_mulai[:7]  # Format YYYY-MM

    # Panggil fungsi get_riwayat sesuai definisi
    items = get_riwayat(
        kelas=kelas_selected or None, 
        bulan=bulan or None
    ) or []

    # Filter tambahan presisi rentang tanggal (YYYY-MM-DD)
    if tgl_mulai:
        items = [
            r for r in items
            if str(r.get("tanggal", "")) >= tgl_mulai
        ]
    if tgl_selesai:
        items = [
            r for r in items
            if str(r.get("tanggal", "")) <= tgl_selesai
        ]

    list_kelas = get_list_kelas()

    return render_template(
        "perizinan/perizinan_riwayat.html",
        items=items,
        list_kelas=list_kelas,
        kelas_selected=kelas_selected,
        tgl_mulai=tgl_mulai,
        tgl_selesai=tgl_selesai,
        bulan=bulan
    )
 
@perizinan_bp.route("/riwayat/<id_perizinan>")
@login_required
def riwayat_detail(id_perizinan):
    item = get_riwayat_detail(id_perizinan)
    if not item:
        return redirect(url_for("perizinan.riwayat_list"))
    return render_template("perizinan/perizinan_riwayat_detail.html", item=item)
 
# SISWA SEARCH (autocomplete)
@perizinan_bp.route("/siswa/search")
@login_required
def siswa_search():
    q = request.args.get("q", "").strip().lower()
    if len(q) < 2:
        return jsonify([])
    
    hasil = []
    for s in get_data_siswa():
        if q in str(s.get("nama_siswa", "")).lower():
            wali_info = get_wali_kelas_untuk_siswa(s)
            
            if isinstance(wali_info, dict):
                nama_wali = wali_info.get("nama", "")
            else:
                nama_wali = str(wali_info or "")

            hasil.append({
                "nisn": s["nisn"],
                "nama_siswa": s["nama_siswa"],
                "kelas_umum": s["kelas_umum"],
                "wali_kelas": nama_wali, 
            })
            if len(hasil) >= 10:
                break

    return jsonify(hasil)
    
# FORM PERIZINAN
@perizinan_bp.route("/form", methods=["GET", "POST"])
@login_required
def form_perizinan():
    if request.method == "POST":
        try:
            rate_limit_check(session["user"])
 
            data = request.form
            nisn = data.get("nisn", "").strip()
            validate_nisn_format(nisn)
            siswa = find_siswa_by_nisn(nisn)
            if not siswa:
                return jsonify({"success": False, "message": "nisn tidak ditemukan di data_siswa"}), 404

            kelas_umum = siswa.get("kelas_umum", "")
            tanggal_mulai = data.get("tanggal_mulai", "").strip()
            jam_mulai = data.get("jam_mulai", "").strip()
            tanggal_selesai = data.get("tanggal_selesai", "").strip()
            jam_selesai = data.get("jam_selesai", "").strip()
            validate_rentang_manual(tanggal_mulai, jam_mulai, tanggal_selesai, jam_selesai)
 
            durasi = data.get("jumlah_jpl", "").strip()

            DURASI_MAP = {
                "2_jpl": "2 JPL",
                "4_jpl": "4 JPL",
                "6_jpl": "6 JPL",
                "8_jpl": "8 JPL",
                "10_jpl": "10 JPL",
                "1_hari": "1 Hari",
                "lebih_1_hari": "Lebih dari 1 Hari",
            }

            if durasi not in DURASI_MAP:
                return jsonify({
                    "success": False,
                    "message": "Durasi perizinan wajib dipilih."
                }), 400

            jumlah_jpl = DURASI_MAP[durasi]
 
            alasan = sanitize_text(data.get("alasan", ""), MAX_ALASAN)
            if not alasan:
                return jsonify({"success": False, "message": "alasan wajib diisi"}), 400
 
            petugas = sanitize_text(data.get("petugas", ""), MAX_PETUGAS)

            status_petugas = data.get("status_petugas", "")
            validate_enum(status_petugas, ENUM_STATUS_PETUGAS, "status_petugas")
            
            if not petugas:
                return jsonify({"success": False, "message": "petugas wajib diisi"}), 400
 
            need_acc = data.get("need_acc") == "1"
 
            # wali kelas tujuan otomatis dari kelas siswa, bukan input manual
            wali_info = get_wali_kelas_untuk_siswa(siswa)
            wali_kelas_tujuan = wali_info.get("nama", "") if isinstance(wali_info, dict) else str(wali_info)
            no_hp_raw = wali_info.get("no_hp", "")

            # Clean & format HP ke 628xxx
            no_hp_wa = re.sub(r'\D', '', no_hp_raw)
            if no_hp_wa.startswith('0'):
                no_hp_wa = '62' + no_hp_wa[1:]

            if check_duplikat_aktif(nisn, tanggal_mulai, jumlah_jpl):
                return jsonify({"success": False, "message": "Siswa sudah punya izin aktif di tanggal & durasi yang sama"}), 400
 
            id_perizinan = gen_id_perizinan(tanggal_mulai)
            ts = now_iso()
 
            base_row = {
                "id_perizinan": id_perizinan, "nisn": nisn, "nama_siswa": siswa["nama_siswa"], "kelas_umum": kelas_umum,
                "tanggal": tanggal_mulai, "durasi": jumlah_jpl, "alasan": alasan,
                "petugas": petugas, "status_petugas": status_petugas,
                "created_at": ts, "updated_at": ts,
                "jam_mulai": jam_mulai, "tanggal_mulai": tanggal_mulai,
                "jam_selesai": jam_selesai, "tanggal_selesai": tanggal_selesai,
            }
 
            if not need_acc:
                simpan_perizinan_langsung({**base_row, "status_perizinan": "aktif"})
                return jsonify({
                    "success": True,
                    "message": f"Perizinan {id_perizinan} berhasil diterbitkan.",
                    "redirect": url_for("perizinan.riwayat_list"),
                }), 200
            else:
                simpan_pengajuan({
                    **base_row, "status_perizinan": "menunggu_acc",
                    "diajukan_oleh": petugas, "wali_kelas_tujuan": wali_kelas_tujuan,
                    "tanggal_acc": "", "catatan_wali_kelas": "",
                })

                url_acc = url_for("perizinan.acc_detail_pending", id_perizinan=id_perizinan, _external=True)

                pesan_wa = (
                    f"*PENGAJUAN ACC PERIZINAN SISWA*\n\n"
                    f"Yth. Bapak/Ibu Wali Kelas ({wali_kelas_tujuan}),\n"
                    f"Mohon periksa pengajuan izin siswa berikut:\n\n"
                    f"• *Nama:* {siswa['nama_siswa']}\n"
                    f"• *Kelas:* {kelas_umum}\n"
                    f"• *Waktu mulai:* {tanggal_mulai} ({jam_mulai})\n"
                    f"• *Waktu selesai:* {tanggal_selesai} ({jam_selesai})\n"
                    f"• *Alasan:* {alasan}\n"
                    f"• *Petugas Input:* {petugas}\n\n"
                    f"Silakan klik link berikut untuk memproses (setujui/tolak):\n"
                    f"{url_acc}"
                )

                return jsonify({
                    "success": True,
                    "message": f"Pengajuan {id_perizinan} terkirim ke {wali_kelas_tujuan or '(wali kelas belum diset)'}.",
                    "redirect": url_for("perizinan.form_perizinan"),
                    "wa_target": no_hp_wa,
                    "wa_text": pesan_wa
                }), 200
 
        except ValueError as e:
            return jsonify({"success": False, "message": str(e)}), 400
 
    return render_template("perizinan/perizinan_form.html")
 
# ACC PENGAJUAN
# ACC WALI KELAS - LIST
@perizinan_bp.route("/acc", methods=["GET", "POST"])
@login_required
@role_required("admin", "wali kelas")
def acc_list():
    if request.method == "POST":
        try:
            rate_limit_check(session["user"])

            data = request.form
            id_perizinan = data.get("id_perizinan", "").strip()
            aksi = data.get("aksi", "").strip()
            catatan = sanitize_text(data.get("catatan", ""), MAX_CATATAN)

            validate_enum(aksi, {"approve", "reject"}, "aksi")

            hasil = proses_acc(
                id_perizinan=id_perizinan,
                aksi=aksi,
                catatan=catatan,
                target_row=get_pengajuan_detail(id_perizinan)
            )

            return jsonify(hasil)

        except ValueError as e:
            return jsonify({
                "success": False,
                "message": str(e)
            }), 400

    items = get_pengajuan("semua")

    items_pending = [
        r for r in items
        if r.get("status_perizinan") == "menunggu_acc"
    ]

    items_riwayat = [
        r for r in items
        if r.get("status_perizinan") in {"aktif", "ditolak", "disetujui", "selesai"}
    ]

    return render_template(
        "perizinan/perizinan_acc.html",
        items_pending=items_pending,
        items_riwayat=items_riwayat
    )

# ACC WALI KELAS - DETAIL PENDING
@perizinan_bp.route("/acc/pending/<id_perizinan>", methods=["GET"])
@login_required
@role_required("admin", "wali kelas")
def acc_detail_pending(id_perizinan):
    detail = get_pengajuan_detail(id_perizinan)
    if not detail or detail.get("status_perizinan") != "menunggu_acc":
        return redirect(url_for("perizinan.acc_list", err="Data pending tidak ditemukan."))

    return render_template("perizinan/perizinan_pending_detail.html", r=detail)


# ACC WALI KELAS - DETAIL RIWAYAT
@perizinan_bp.route("/acc/riwayat/<id_perizinan>", methods=["GET"])
@login_required
@role_required("admin", "wali kelas")
def acc_detail_riwayat(id_perizinan):
    detail = get_pengajuan_detail(id_perizinan)
    if not detail or detail.get("status_perizinan") == "menunggu_acc":
        return redirect(url_for("perizinan.acc_list", err="Data riwayat tidak ditemukan."))

    return render_template("perizinan/perizinan_acc_detail.html", r=detail)
 
# SURAT DIGITAL
@perizinan_bp.route("/surat/<id_perizinan>")
@login_required
def surat_digital(id_perizinan):
    item = get_surat_data(id_perizinan)
    if not item:
        return redirect(url_for("perizinan.riwayat_list"))
    return render_template("perizinan/perizinan_surat.html", dicetak=now_iso(), **item)