from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from routes.decorators import login_required
from sheets.sheets_jadwal import get_all_pengumuman, get_pengumuman_by_id, add_pengumuman, update_pengumuman, delete_pengumuman
from datetime import datetime
from zoneinfo import ZoneInfo


pengumuman_bp = Blueprint("pengumuman", __name__, url_prefix="/pengumuman")


# PENGUMUMAN
@pengumuman_bp.route("/")
@login_required
def pengumuman_list():
    items = get_all_pengumuman()
    return render_template("pengumuman/daftar_pengumuman.html", items=items)

@pengumuman_bp.route("/tambah", methods=["GET", "POST"])
@login_required
def pengumuman_tambah():
    if request.method == "POST":
        title = request.form.get("title")
        desc = request.form.get("desc")

        if not title or not desc:
            return jsonify({
                "success": False,
                "message": "Title, deskripsi wajib diisi."
            }), 400

        add_pengumuman(title, desc)
        return jsonify({
            "success": True,
            "message": "Pengumuman berhasil ditambahkan.",
            "redirect": url_for("pengumuman.pengumuman_list")
        }), 200

    return render_template("pengumuman/pengumuman_form.html", item=None)

@pengumuman_bp.route("/<pengumuman_id>/edit", methods=["GET", "POST"])
@login_required
def pengumuman_edit(pengumuman_id):
    item = get_pengumuman_by_id(pengumuman_id)
    if not item:
        if request.method == "POST":
            return jsonify({
                "success": False,
                "message": "Pengumuman tidak ditemukan."
            }), 404
        return redirect(url_for("pengumuman.pengumuman_list"))

    if request.method == "POST":
        title = request.form.get("title")
        desc = request.form.get("desc")

        if not title or not desc:
            return jsonify({
                "success": False,
                "message": "Title, deskripsi wajib diisi."
            }), 400

        update_pengumuman(pengumuman_id, title, desc)
        return jsonify({
            "success": True,
            "message": "Pengumuman berhasil diperbarui.",
            "redirect": url_for("pengumuman.pengumuman_list")
        }), 200

    return render_template("pengumuman/pengumuman_form.html", item=item)

@pengumuman_bp.route("/<pengumuman_id>/hapus", methods=["GET", "POST"])
@login_required
def pengumuman_hapus(pengumuman_id):

    item = get_pengumuman_by_id(pengumuman_id)

    if not item:
        if request.method == "POST":
            return jsonify({
                "success": False,
                "message": "Pengumuman tidak ditemukan."
            }), 404

        return redirect(url_for("pengumuman.pengumuman_list"))


    if request.method == "POST":

        delete_pengumuman(pengumuman_id)

        return jsonify({
            "success": True,
            "message": "Pengumuman berhasil dihapus.",
            "redirect": url_for("pengumuman.pengumuman_list")
        }), 200


    return render_template(
        "pengumuman/pengumuman_hapus.html",
        item=item
    )


@pengumuman_bp.route("/<pengumuman_id>/detail")
def pengumuman_detail(pengumuman_id):
    item = get_pengumuman_by_id(pengumuman_id)

    if not item:
        return redirect(url_for("repository"))

    return render_template(
        "pengumuman/pengumuman_detail.html",
        item=item
    )