from functools import wraps
from flask import session, redirect, url_for, request

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            # sertakan URL tujuan sebagai next
            return redirect(url_for("login", next=request.full_path))
        return f(*args, **kwargs)
    return decorated