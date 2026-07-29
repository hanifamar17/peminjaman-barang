import os, re
from flask import Blueprint, render_template, jsonify, request
from itertools import groupby as it_groupby
from sheets.sheets_jadwal_pelajaran import get_jadwal_pelajaran_data, get_jadwal_by_hari, get_jadwal_by_kelas, _get_jadwal_pelajaran_service


jadwal_pelajaran_bp = Blueprint("jadwal_pelajaran", __name__, url_prefix="/jadwal-pelajaran")

# =======================
# JADWAL KBM
# =======================
_ARABIC_CHAR_RE = re.compile(r'[\u0600-\u06FF\u0750-\u077F]')

def split_mixed_script(text):
    """
    Pecah teks jadi list of (segment, is_arabic).
    'Qiroah Kitab: أدب العالم' -> [('Qiroah Kitab: ', False), ('أدب العالم', True)]
    """
    if not text:
        return [('', False)]
    parts = []
    buf = ''
    buf_is_arabic = None
    for ch in text:
        is_arabic = bool(_ARABIC_CHAR_RE.match(ch))
        if buf_is_arabic is None:
            buf_is_arabic = is_arabic
        if is_arabic == buf_is_arabic or ch.isspace():
            buf += ch
        else:
            parts.append((buf, buf_is_arabic))
            buf = ch
            buf_is_arabic = is_arabic
    if buf:
        parts.append((buf, buf_is_arabic))
    return parts

def _waktu_to_minutes(waktu):
    m = re.match(r"(\d{1,2})[.:](\d{2})", (waktu or "").strip())
    if not m:
        return 9999
    return int(m.group(1)) * 60 + int(m.group(2))


@jadwal_pelajaran_bp.route("/")
def jadwal_pelajaran_landing():
    data = get_jadwal_pelajaran_data()

    # 1. sort by hari + id (urutan sesi asli sheet)
    jadwal_sorted = sorted(
        data["jadwal"],
        key=lambda r: (r.get("hari") or "", int(r.get("id") or 0)),
    )

    # 2. group per hari -> per kelas, urutan kelas = first-appearance
    jadwal_per_hari = {}
    for hari, rows_hari_iter in it_groupby(jadwal_sorted, key=lambda r: r.get("hari") or ""):
        rows_hari = list(rows_hari_iter)
        kelas_order = []
        per_kelas = {}
        for r in rows_hari:
            k = r.get("nama_kelas") or "Lainnya"
            if k not in per_kelas:
                per_kelas[k] = []
                kelas_order.append(k)
            per_kelas[k].append(r)
        # sort tiap kelas by jam, jaga2 kalau ada anomali id
        for k in per_kelas:
            per_kelas[k].sort(key=lambda r: _waktu_to_minutes(r.get("waktu")))
        jadwal_per_hari[hari] = [(k, per_kelas[k]) for k in kelas_order]

    return render_template(
        "jadwal_pelajaran/jadwal_pelajaran_landing.html",
        kelas_list=data["kelas"],
        jadwal_per_hari=jadwal_per_hari,
    )

@jadwal_pelajaran_bp.route("/api/data")
def jadwal_pelajaran_api():
    force = request.args.get("refresh") == "1"
    return jsonify(get_jadwal_pelajaran_data(force_refresh=force))

@jadwal_pelajaran_bp.route("/kelas/<nama_kelas>")
def jadwal_by_kelas(nama_kelas):
    rows = get_jadwal_by_kelas(nama_kelas)
    return render_template(
        "jadwal_pelajaran/jadwal_kelas.html",
        nama_kelas=nama_kelas,
        rows=rows,
    )

@jadwal_pelajaran_bp.route("/hari/<hari>")
def jadwal_by_hari(hari):
    rows = get_jadwal_by_hari(hari)
    return render_template(
        "jadwal_pelajaran/jadwal_hari.html",
        hari=hari,
        rows=rows,
    )

