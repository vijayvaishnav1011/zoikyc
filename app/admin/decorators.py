from functools import wraps
from flask import redirect, url_for, flash, abort
from flask_login import current_user

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please sign in with administrator credentials.", "warning")
            return redirect(url_for('auth.login'))
        if current_user.role != 'super_admin':
            flash("Access denied: Administrator privileges required.", "danger")
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function
