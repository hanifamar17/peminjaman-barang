from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from routes.decorators import login_required
from sheets.sheets_inventory_labkomp import (
    generate_item_id,
    add_inventory,
    delete_inventory,
    get_inventory,
    update_inventory,
)


inventory_labkomp_bp = Blueprint("inventory_labkomp", __name__, url_prefix="/inventory")

# Landing page inventory
@inventory_labkomp_bp.route("/")
def inventory_landing():
    return render_template("inventory/landing_inventory.html")


# API: search inventory by q
@inventory_labkomp_bp.route("/api/search")
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
# INVENTORY SECTION
# =======================
# Read inventory list
@inventory_labkomp_bp.route("/list")
@login_required
def inventory_list():
    items = get_inventory()
    return render_template("inventory/inventory.html", items=items)

# Add inventory item
@inventory_labkomp_bp.route("/add", methods=["GET", "POST"])
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

@inventory_labkomp_bp.route("/edit/<item_id>", methods=["GET", "POST"])
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
@inventory_labkomp_bp.route("/delete/<item_id>", methods=["GET", "POST"])
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