from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from routes.decorators import login_required


perizinan_bp = Blueprint("perizinan", __name__, url_prefix="/perizinan")