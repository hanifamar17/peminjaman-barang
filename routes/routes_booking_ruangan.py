import os
from flask import Blueprint, render_template, jsonify

from sheets.sheets_jadwal import get_jadwal, get_kalender_akademik


booking_ruangan_bp = Blueprint("booking_ruangan", __name__, url_prefix="/booking-ruangan")

# =======================
# JADWAL PENGGUNAAN LAB (booking ruangan)
# =======================
@booking_ruangan_bp.route("/")
def booking_landing():
    return render_template("booking_ruangan/booking_landing.html")

@booking_ruangan_bp.route("/prosedur")
def booking_prosedur():
    return render_template("booking_ruangan/booking_prosedur.html")

@booking_ruangan_bp.route("/jadwal")
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
@booking_ruangan_bp.route("/api/jadwal")
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

@booking_ruangan_bp.route("/form")
def booking_form_page():
    booking_form_url = "https://docs.google.com/forms/d/e/1FAIpQLSc7oMnechEl_sMkKAtWGsHsES9LKhZYirz9qUXErYi588lfgg/viewform"
    
    booking_form_embed_url = os.getenv("BOOKING_FORM_EMBED_URL", booking_form_url)
    return render_template(
        "booking_ruangan/form_peminjaman.html",
        booking_form_url=booking_form_url,
        booking_form_embed_url=booking_form_embed_url,
    )
