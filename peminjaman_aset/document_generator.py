import os
import uuid
import datetime
import tempfile

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
)

BULAN_ROMAWI = {
    1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI",
    7: "VII", 8: "VIII", 9: "IX", 10: "X", 11: "XI", 12: "XII",
}


def generate_nomor_surat(get_last_sequence_this_month) -> str:
    """
    Generate nomor surat otomatis, format: 001/PA/MANU/VII/2026

    get_last_sequence_this_month: callable yang mengembalikan jumlah surat
    peminjaman aset yang sudah terbit di bulan & tahun berjalan (int).
    """
    now = datetime.datetime.now()
    seq = get_last_sequence_this_month() + 1
    return f"{seq:03d}/PA/MANU/{BULAN_ROMAWI[now.month]}/{now.year}"


# ---------- Styles ----------

_styles = getSampleStyleSheet()

STYLE_TITLE = ParagraphStyle(
    "SuratTitle", parent=_styles["Normal"],
    fontName="Times-Bold", fontSize=13, alignment=TA_CENTER,
    spaceAfter=2, leading=16,
)
STYLE_NOMOR = ParagraphStyle(
    "SuratNomor", parent=_styles["Normal"],
    fontName="Times-Roman", fontSize=11, alignment=TA_CENTER,
    spaceAfter=14,
)
STYLE_BODY = ParagraphStyle(
    "SuratBody", parent=_styles["Normal"],
    fontName="Times-Roman", fontSize=12, alignment=TA_JUSTIFY,
    spaceAfter=8, leading=16,
)
STYLE_SECTION = ParagraphStyle(
    "SuratSection", parent=_styles["Normal"],
    fontName="Times-Bold", fontSize=12, alignment=TA_JUSTIFY,
    spaceBefore=10, spaceAfter=6, leading=16,
)
STYLE_JAMINAN = ParagraphStyle(
    "SuratJaminan", parent=_styles["Normal"],
    fontName="Times-Roman", fontSize=12, leftIndent=20,
    spaceAfter=3, leading=16,
)
STYLE_TTD_LABEL = ParagraphStyle(
    "TtdLabel", parent=_styles["Normal"],
    fontName="Times-Roman", fontSize=12, alignment=TA_CENTER, leading=16,
)
STYLE_METERAI = ParagraphStyle(
    "Meterai", parent=_styles["Normal"],
    fontName="Times-Italic", fontSize=10, alignment=TA_CENTER, leading=13,
)
STYLE_TTD_NAME = ParagraphStyle(
    "TtdName", parent=_styles["Normal"],
    fontName="Times-Bold", fontSize=12, alignment=TA_CENTER, leading=16,
)


def _identitas_table(rows):
    """rows: list of (label, value) tuples -> rapi seperti 'Label : Value'"""
    data = [[Paragraph(label, STYLE_BODY), ":", Paragraph(str(value), STYLE_BODY)] for label, value in rows]
    t = Table(data, colWidths=[4.3 * cm, 0.4 * cm, 10.3 * cm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return t


def _barang_table(barang):
    header = ["No", "Nama Barang", "Merek/Spesifikasi", "Jumlah", "Kondisi Saat Dipinjam"]
    cell_style = ParagraphStyle("cell", parent=_styles["Normal"], fontName="Times-Roman", fontSize=10.5, leading=13)
    header_style = ParagraphStyle("cellH", parent=cell_style, fontName="Times-Bold", alignment=TA_CENTER)

    data = [[Paragraph(h, header_style) for h in header]]
    for b in barang:
        data.append([
            Paragraph(str(b["no"]), ParagraphStyle("c", parent=cell_style, alignment=TA_CENTER)),
            Paragraph(str(b["nama"]), cell_style),
            Paragraph(str(b["spek"]), cell_style),
            Paragraph(str(b["jumlah"]), ParagraphStyle("c", parent=cell_style, alignment=TA_CENTER)),
            Paragraph(str(b["kondisi"]), ParagraphStyle("c", parent=cell_style, alignment=TA_CENTER)),
        ])

    col_widths = [1.2 * cm, 4.8 * cm, 4.3 * cm, 2 * cm, 2.9 * cm]
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.75, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.94, 0.94, 0.94)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def generate_pdf(data: dict) -> str:
    """
    Generate PDF surat peminjaman aset langsung dari data, pakai ReportLab
    (pure Python, tanpa dependency sistem -> aman untuk Vercel serverless).
    Mengembalikan path file PDF sementara di /tmp (harus dihapus setelah diupload).
    """
    tmp_filename = f"peminjaman_aset_{uuid.uuid4().hex}.pdf"
    tmp_path = os.path.join(tempfile.gettempdir(), tmp_filename)

    doc = SimpleDocTemplate(
        tmp_path,
        pagesize=A4,
        topMargin=2.5 * cm, bottomMargin=2 * cm,
        leftMargin=2 * cm, rightMargin=2 * cm,
    )

    story = []

    story.append(Paragraph("SURAT PEMINJAMAN ASET MA NURUL UMMAH", STYLE_TITLE))
    story.append(Paragraph(f"Nomor: {data['nomor_surat']}", STYLE_NOMOR))

    story.append(Paragraph("Saya yang bertanda tangan di bawah ini:", STYLE_BODY))
    story.append(_identitas_table([
        ("Nama", data["nama"]),
        ("Jenis Kelamin", data["jenis_kelamin"]),
        ("Pekerjaan/Instansi", data["pekerjaan"]),
        ("Alamat", data["alamat"]),
        ("No. Telepon/WA", data["telepon"]),
        ("No. Identitas", data["no_identitas"]),
    ]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Dengan ini mengajukan permohonan untuk meminjam aset milik:", STYLE_BODY))
    story.append(_identitas_table([
        ("Nama Lembaga", "MA Nurul Ummah Yogyakarta"),
        ("Alamat Lembaga", "Jalan Raden Ronggo KG/II 982, Prenggan, Kotagede, D.I. Yogyakarta"),
    ]))

    story.append(Paragraph("RINCIAN BARANG YANG DIPINJAM", STYLE_SECTION))
    story.append(_barang_table(data["barang"]))
    story.append(Spacer(1, 8))

    story.append(_identitas_table([
        ("Tujuan Peminjaman", data["tujuan"]),
        ("Lokasi Penggunaan", data["lokasi_penggunaan"]),
        ("Tanggal Peminjaman", data["tgl_pinjam"]),
        ("Tanggal Pengembalian", data["tgl_kembali"]),
    ]))

    story.append(Paragraph("JAMINAN PEMINJAMAN", STYLE_SECTION))
    story.append(Paragraph("Sebagai bentuk pertanggungjawaban, peminjam menyerahkan jaminan berupa:", STYLE_BODY))
    check_identitas = "[X]" if data.get("jaminan_identitas") else "[  ]"
    check_surat = "[X]" if data.get("jaminan_surat") else "[  ]"
    story.append(Paragraph(
        f"{check_identitas} Identitas Asli berupa {data.get('jenis_identitas_jaminan', 'KTP/SIM/Paspor')}",
        STYLE_JAMINAN,
    ))
    story.append(Paragraph(f"{check_surat} Surat Jaminan dari Instansi/Organisasi", STYLE_JAMINAN))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Jaminan akan dikembalikan apabila seluruh barang dikembalikan dalam kondisi baik, "
        "lengkap, dan tepat waktu.",
        STYLE_BODY,
    ))

    story.append(Paragraph("PERNYATAAN TANGGUNG JAWAB", STYLE_SECTION))
    story.append(Paragraph(
        "Saya bertanggung jawab penuh atas penggunaan, perawatan, dan pengembalian "
        "barang-barang yang saya pinjam. Jika terjadi kerusakan atau kehilangan, saya "
        "bersedia memperbaiki atau mengganti sesuai ketentuan yang berlaku.",
        STYLE_BODY,
    ))
    story.append(Paragraph(
        "Demikian surat ini saya buat dengan sebenar-benarnya untuk digunakan sebagaimana mestinya.",
        STYLE_BODY,
    ))

    story.append(Spacer(1, 30))

    ttd_data = [
        [Paragraph("Petugas Lembaga,", STYLE_TTD_LABEL),
         Paragraph(f"{data['kota']}, {data['tgl_surat']}", STYLE_TTD_LABEL)],
        ["", Paragraph("Yang Meminjam,", STYLE_TTD_LABEL)],
        [Spacer(1, 30), Paragraph("(Meterai Rp10.000)", STYLE_METERAI)],
        [Spacer(1, 25), Spacer(1, 25)],
        [Paragraph(data["nama_petugas"], STYLE_TTD_NAME),
         Paragraph(data["nama"], STYLE_TTD_NAME)],
    ]
    ttd_table = Table(ttd_data, colWidths=[8 * cm, 8 * cm])
    ttd_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(KeepTogether(ttd_table))

    doc.build(story)
    return tmp_path