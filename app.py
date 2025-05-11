# backend/app.py

import os
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func # For sum and count aggregates
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta # Added timedelta for active user check
import uuid # For generating referral codes
from functools import wraps # For login_required decorator

app = Flask(__name__, template_folder=
    "../templates", static_folder="../static")

# Configuration
app.config["SECRET_KEY"] = os.environ.get(
    "FLASK_SECRET_KEY", "a_very_secret_key_for_dev_23456789") # IMPORTANT: Change in production!
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///criptomain.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# --- Database Models (based on technical_design_advanced.md) ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    cripto_main_tokens = db.Column(db.Float, default=0.0, nullable=False)
    taps_for_next_token = db.Column(db.Integer, default=0, nullable=False)
    referral_code = db.Column(db.String(36), unique=True, nullable=True)
    referred_by_user_id = db.Column(db.Integer, db.ForeignKey(
        "user.id"), nullable=True)
    personal_rate_bonus = db.Column(db.Float, default=0.0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)
    is_admin = db.Column(db.Boolean, default=False) # Admin flag

    # User settings - expanded for step 006
    display_name = db.Column(db.String(100), nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)
    payment_address = db.Column(db.String(200), nullable=True)
    music_enabled = db.Column(db.Boolean, default=True) # For background music
    selected_music_track = db.Column(db.String(100), default="track1.mp3", nullable=True)
    selected_theme = db.Column(db.String(50), default="default", nullable=True) # e.g., "default", "dark", "light"
    selected_click_animation = db.Column(db.String(50), default="default", nullable=True) # e.g., "default", "ripple", "sparkle"
    sound_effects_enabled = db.Column(db.Boolean, default=True) # For UI sounds

    withdrawal_requests = db.relationship(
        "WithdrawalRequest", backref="user", lazy=True)
    referrals_made = db.relationship(
        "Referral", foreign_keys="Referral.referrer_user_id",
        backref="referrer", lazy="dynamic")
    referral_received = db.relationship(
        "Referral", foreign_keys="Referral.referred_user_id",
        backref="referred_user", uselist=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_referral_code(self):
        if not self.referral_code:
            self.referral_code = str(uuid.uuid4())

class GlobalSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    setting_name = db.Column(db.String(100), unique=True, nullable=False)
    setting_value_float = db.Column(db.Float, nullable=True)
    setting_value_int = db.Column(db.Integer, nullable=True)
    setting_value_str = db.Column(db.String(255), nullable=True)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow,
                             onupdate=datetime.utcnow)

class TokenPriceHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    price_usd = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(255), nullable=True)

class WithdrawalRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    tokens_to_withdraw = db.Column(db.Float, nullable=False)
    global_price_at_withdrawal = db.Column(db.Float, nullable=False)
    personal_bonus_at_withdrawal = db.Column(db.Float, nullable=False)
    total_usd_value_before_commission = db.Column(db.Float, nullable=False)
    commission_percentage = db.Column(db.Float, nullable=False, default=0.40)
    commission_amount_usd = db.Column(db.Float, nullable=False)
    amount_to_user_usd = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(100), nullable=False)
    payment_details = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default="pending",
                       nullable=False)  # pending, processed, rejected
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)
    admin_notes = db.Column(db.Text, nullable=True)

class Referral(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    referrer_user_id = db.Column(db.Integer, db.ForeignKey(
        "user.id"), nullable=False)
    referred_user_id = db.Column(db.Integer, db.ForeignKey(
        "user.id"), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --- Helper Functions for Global Settings ---
def get_global_setting(name, default=None, type_cast=float):
    setting = GlobalSetting.query.filter_by(setting_name=name).first()
    if setting:
        if type_cast == float and setting.setting_value_float is not None:
            return setting.setting_value_float
        if type_cast == int and setting.setting_value_int is not None:
            return setting.setting_value_int
        if type_cast == str and setting.setting_value_str is not None:
            return setting.setting_value_str
    return default

def set_global_setting(name, value):
    setting = GlobalSetting.query.filter_by(setting_name=name).first()
    if not setting:
        setting = GlobalSetting(setting_name=name)
        db.session.add(setting)
    if isinstance(value, float):
        setting.setting_value_float = value
    elif isinstance(value, int):
        setting.setting_value_int = value
    elif isinstance(value, str):
        setting.setting_value_str = value
    else:
        raise ValueError("Unsupported type for global setting")
    db.session.commit()

# --- Initialization Function ---
def initialize_global_settings():
    with app.app_context():
        if GlobalSetting.query.count() == 0:
            print("Initializing global settings...")
            set_global_setting("initial_token_price_usd", 1.6)
            set_global_setting("price_increment_per_user_usd", 0.1)
            set_global_setting("total_users", 0)
            initial_price = get_global_setting("initial_token_price_usd")
            set_global_setting("current_global_token_price_usd", initial_price)
            price_log = TokenPriceHistory(price_usd=initial_price,
                                        reason="Initial system setup")
            db.session.add(price_log)
            admin_username = os.environ.get("ADMIN_USERNAME", "admin")
            admin_password = os.environ.get("ADMIN_PASSWORD", "criptoadminpass1234") 
            admin_email = os.environ.get("ADMIN_EMAIL", "admin@criptomain.com")
            if not User.query.filter_by(username=admin_username).first():
                admin_user = User(username=admin_username, email=admin_email, is_admin=True)
                admin_user.set_password(admin_password)
                admin_user.generate_referral_code()
                db.session.add(admin_user)
                print(f"Admin user {admin_username} created with default password.")
            db.session.commit()
            print("Global settings initialized.")
        else:
            print("Global settings already exist.")

# --- Decorators ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login", next=request.url))
        user = User.query.get(session["user_id"])
        if not user or not user.is_admin:
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated_function

# --- Routes ---
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/game")
@login_required
def game():
    return render_template("game.html")

@app.route("/profile", methods=["GET"])
@login_required
def profile_get(): # Renamed to avoid conflict, GET for profile page
    user = User.query.get(session["user_id"])
    return render_template("profile.html", user=user)

@app.route("/settings", methods=["GET"])
@login_required
def settings_page(): # Route to display the settings page
    user = User.query.get(session["user_id"])
    # Music tracks and themes would ideally come from a config or another DB table
    # For now, let's assume some defaults for the template to render
    available_music_tracks = [{"id": "track1.mp3", "name": "Chill Vibe"}, {"id": "track2.mp3", "name": "Upbeat Energy"}]
    available_themes = [{"id": "default", "name": "Default"}, {"id": "dark", "name": "Dark Mode"}, {"id": "light", "name": "Light Mode"}]
    available_animations = [{"id": "default", "name": "Default"}, {"id": "ripple", "name": "Ripple"}, {"id": "sparkle", "name": "Sparkle"}]
    return render_template("settings.html", user=user, 
                           available_music_tracks=available_music_tracks,
                           available_themes=available_themes,
                           available_animations=available_animations)

@app.route("/api/user_settings", methods=["GET", "POST"])
@login_required
def user_settings_api():
    user = User.query.get(session["user_id"])
    if request.method == "GET":
        return jsonify({
            "success": True,
            "settings": {
                "display_name": user.display_name or user.username,
                "phone_number": user.phone_number,
                "payment_address": user.payment_address,
                "music_enabled": user.music_enabled,
                "selected_music_track": user.selected_music_track,
                "selected_theme": user.selected_theme,
                "selected_click_animation": user.selected_click_animation,
                "sound_effects_enabled": user.sound_effects_enabled
            }
        })
    elif request.method == "POST":
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400

        user.display_name = data.get("display_name", user.display_name)
        user.phone_number = data.get("phone_number", user.phone_number)
        user.payment_address = data.get("payment_address", user.payment_address)
        
        if "music_enabled" in data:
            user.music_enabled = bool(data["music_enabled"])
        user.selected_music_track = data.get("selected_music_track", user.selected_music_track)
        user.selected_theme = data.get("selected_theme", user.selected_theme)
        user.selected_click_animation = data.get("selected_click_animation", user.selected_click_animation)
        if "sound_effects_enabled" in data:
            user.sound_effects_enabled = bool(data["sound_effects_enabled"])
        
        db.session.commit()
        return jsonify({"success": True, "message": "Settings updated successfully."})

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        referral_code_input = request.form.get("referral_code", "").strip()

        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))
        if len(password) < 6: 
             flash("Password must be at least 6 characters long.", "danger")
             return redirect(url_for("register"))

        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "danger")
            return redirect(url_for("register"))
        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "danger")
            return redirect(url_for("register"))

        new_user = User(username=username, email=email, display_name=username) # Set initial display_name
        new_user.set_password(password)
        new_user.generate_referral_code()
        db.session.add(new_user)
        db.session.flush() 

        if referral_code_input:
            referrer = User.query.filter_by(referral_code=referral_code_input).first()
            if referrer and referrer.id != new_user.id:
                new_user.referred_by_user_id = referrer.id
                referrer.personal_rate_bonus += 0.01
                referral_record = Referral(referrer_user_id=referrer.id, referred_user_id=new_user.id)
                db.session.add(referral_record)
                db.session.add(referrer)
                flash(f"Successfully registered! You were referred by {referrer.username}. Their rate bonus increased!", "success")
            else:
                flash("Invalid or self-referral code. Registered without referral bonus.", "warning")
        else:
            flash("Successfully registered!", "success")

        total_users = get_global_setting("total_users", 0, int) + 1
        set_global_setting("total_users", total_users)
        initial_price = get_global_setting("initial_token_price_usd")
        increment = get_global_setting("price_increment_per_user_usd")
        current_total_users_for_price = total_users 
        new_global_price = initial_price + (current_total_users_for_price * increment) 
        set_global_setting("current_global_token_price_usd", new_global_price)
        price_log = TokenPriceHistory(price_usd=new_global_price, reason=f"New user: {username} (ID: {new_user.id})")
        db.session.add(price_log)
        
        db.session.commit()
        session["user_id"] = new_user.id
        session["username"] = new_user.username
        session["is_admin"] = new_user.is_admin
        return redirect(url_for("game"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
            session["username"] = user.username
            session["is_admin"] = user.is_admin
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            flash("Logged in successfully!", "success")
            next_url = request.args.get("next")
            if user.is_admin:
                 return redirect(next_url or url_for("admin_dashboard"))
            return redirect(next_url or url_for("game"))
        else:
            flash("Invalid username or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    session.pop("user_id", None)
    session.pop("username", None)
    session.pop("is_admin", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

# --- API Routes for Game Mechanics ---

@app.route("/api/game_state", methods=["GET"])
@login_required
def get_game_state():
    user = User.query.get(session["user_id"])
    current_global_price = get_global_setting("current_global_token_price_usd")
    effective_rate = current_global_price + user.personal_rate_bonus
    return jsonify({
        "username": user.username,
        "cripto_main_tokens": user.cripto_main_tokens,
        "taps_for_next_token": user.taps_for_next_token,
        "referral_code": user.referral_code,
        "current_global_token_price_usd": current_global_price,
        "personal_rate_bonus": user.personal_rate_bonus,
        "effective_token_value_usd": round(effective_rate, 3),
        # User settings for frontend application
        "settings": {
            "display_name": user.display_name or user.username,
            "phone_number": user.phone_number,
            "payment_address": user.payment_address,
            "music_enabled": user.music_enabled,
            "selected_music_track": user.selected_music_track,
            "selected_theme": user.selected_theme,
            "selected_click_animation": user.selected_click_animation,
            "sound_effects_enabled": user.sound_effects_enabled
        } 
    })

@app.route("/api/record_tap", methods=["POST"])
@login_required
def record_tap_route():
    user = User.query.get(session["user_id"])
    user.taps_for_next_token += 1
    tokens_earned_this_tap = 0
    if user.taps_for_next_token >= 100:
        tokens_earned_this_tap = user.taps_for_next_token // 100
        user.cripto_main_tokens += tokens_earned_this_tap
        user.taps_for_next_token %= 100
    db.session.commit()
    return jsonify({
        "success": True,
        "cripto_main_tokens": user.cripto_main_tokens,
        "taps_for_next_token": user.taps_for_next_token,
        "tokens_earned_this_tap": tokens_earned_this_tap
    })

@app.route("/api/request_withdrawal", methods=["POST"])
@login_required
def request_withdrawal_route():
    data = request.get_json()
    user = User.query.get(session["user_id"])
    tokens_to_withdraw = data.get("tokens_to_withdraw")
    payment_method = data.get("payment_method") 
    payment_details = data.get("payment_details") 

    try:
        tokens_to_withdraw = float(tokens_to_withdraw)
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Invalid token amount."}), 400

    if not all([tokens_to_withdraw, payment_method, payment_details]):
        return jsonify({"success": False, "message": "Missing required fields for withdrawal (tokens, payment method, payment details)."}), 400

    if tokens_to_withdraw <= 0 or tokens_to_withdraw > user.cripto_main_tokens:
        return jsonify({"success": False, "message": "Invalid withdrawal amount or insufficient balance."}), 400

    current_global_price = get_global_setting("current_global_token_price_usd")
    effective_rate = current_global_price + user.personal_rate_bonus
    total_usd_value = tokens_to_withdraw * effective_rate
    commission = total_usd_value * 0.40
    amount_to_user = total_usd_value * 0.60

    user.cripto_main_tokens -= tokens_to_withdraw
    
    withdrawal = WithdrawalRequest(
        user_id=user.id,
        tokens_to_withdraw=tokens_to_withdraw,
        global_price_at_withdrawal=current_global_price,
        personal_bonus_at_withdrawal=user.personal_rate_bonus,
        total_usd_value_before_commission=total_usd_value,
        commission_amount_usd=commission,
        amount_to_user_usd=amount_to_user,
        payment_method=payment_method,
        payment_details=payment_details
    )
    db.session.add(withdrawal)
    db.session.commit()

    return jsonify({
        "success": True, 
        "message": "Withdrawal request submitted successfully.",
        "new_token_balance": user.cripto_main_tokens
    })

@app.route("/api/price_history", methods=["GET"])
@login_required 
def price_history_route():
    days_filter = request.args.get("days", 30, type=int)
    limit_records = request.args.get("limit", 100, type=int)
    start_date = datetime.utcnow() - timedelta(days=days_filter)
    
    history = TokenPriceHistory.query.filter(TokenPriceHistory.timestamp >= start_date)\
                                     .order_by(TokenPriceHistory.timestamp.asc()).limit(limit_records).all()
        
    return jsonify([{"timestamp": h.timestamp.isoformat(), "price_usd": round(h.price_usd, 3), "reason": h.reason} for h in history])

# --- Admin Routes ---
@app.route("/admin")
@admin_required
def admin_dashboard():
    total_users_count = get_global_setting("total_users", 0, int)
    current_price = get_global_setting("current_global_token_price_usd")
    active_users_24h = User.query.filter(User.last_login_at >= datetime.utcnow() - timedelta(hours=24)).count()
    active_users_7d = User.query.filter(User.last_login_at >= datetime.utcnow() - timedelta(days=7)).count()
    total_tokens_in_circulation = db.session.query(func.sum(User.cripto_main_tokens)).scalar() or 0.0
    pending_withdrawals_count = WithdrawalRequest.query.filter_by(status="pending").count()
    total_usd_pending_withdrawal = db.session.query(func.sum(WithdrawalRequest.amount_to_user_usd)).filter_by(status="pending").scalar() or 0.0
    total_usd_paid_out = db.session.query(func.sum(WithdrawalRequest.amount_to_user_usd)).filter_by(status="processed").scalar() or 0.0
    total_admin_commission = db.session.query(func.sum(WithdrawalRequest.commission_amount_usd)).filter_by(status="processed").scalar() or 0.0
    today = datetime.utcnow().date()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)
    new_users_today = User.query.filter(User.created_at >= today).count()
    new_users_this_week = User.query.filter(User.created_at >= start_of_week).count()
    new_users_this_month = User.query.filter(User.created_at >= start_of_month).count()

    return render_template("admin/dashboard.html", 
                           total_users_count=total_users_count, 
                           current_price=round(current_price,3) if current_price else 0,
                           active_users_24h=active_users_24h,
                           active_users_7d=active_users_7d,
                           total_tokens_in_circulation=round(total_tokens_in_circulation, 2),
                           pending_withdrawals_count=pending_withdrawals_count,
                           total_usd_pending_withdrawal=round(total_usd_pending_withdrawal, 2),
                           total_usd_paid_out=round(total_usd_paid_out, 2),
                           total_admin_commission=round(total_admin_commission, 2),
                           new_users_today=new_users_today,
                           new_users_this_week=new_users_this_week,
                           new_users_this_month=new_users_this_month
                           )

@app.route("/admin/users")
@admin_required
def admin_users():
    page = request.args.get("page", 1, type=int)
    search_query = request.args.get("search", "")
    query = User.query.order_by(User.created_at.desc())
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(User.username.ilike(search_term) | User.email.ilike(search_term))
    users_pagination = query.paginate(page=page, per_page=15)
    return render_template("admin/users.html", users_pagination=users_pagination, search_query=search_query)

@app.route("/admin/withdrawals")
@admin_required
def admin_withdrawals():
    page = request.args.get("page", 1, type=int)
    status_filter = request.args.get("status", "pending")
    query = WithdrawalRequest.query.join(User).order_by(WithdrawalRequest.requested_at.desc())
    if status_filter != "all":
        query = query.filter(WithdrawalRequest.status == status_filter)
    
    withdrawals_pagination = query.paginate(page=page, per_page=15)
    return render_template("admin/withdrawals.html", withdrawals_pagination=withdrawals_pagination, current_status=status_filter)

@app.route("/admin/withdrawal/<int:request_id>/process", methods=["POST"])
@admin_required
def admin_process_withdrawal(request_id):
    withdrawal = WithdrawalRequest.query.get_or_404(request_id)
    action = request.form.get("action") 
    admin_notes = request.form.get("admin_notes", "")

    if withdrawal.status != "pending":
        flash("This request has already been actioned.", "warning")
        return redirect(url_for("admin_withdrawals"))

    if action == "processed":
        withdrawal.status = "processed"
        withdrawal.processed_at = datetime.utcnow()
        withdrawal.admin_notes = admin_notes
        flash(f"Withdrawal request #{withdrawal.id} for user {withdrawal.user.username} marked as processed.", "success")
    elif action == "rejected":
        withdrawal.status = "rejected"
        withdrawal.processed_at = datetime.utcnow() 
        withdrawal.admin_notes = admin_notes
        user = User.query.get(withdrawal.user_id)
        if user:
            user.cripto_main_tokens += withdrawal.tokens_to_withdraw
            flash(f"Withdrawal request #{withdrawal.id} for user {withdrawal.user.username} marked as rejected. Tokens returned to user.", "info")
        else:
            flash(f"Withdrawal request #{withdrawal.id} marked as rejected. User not found for token return.", "danger")
    else:
        flash("Invalid action.", "danger")
        return redirect(url_for("admin_withdrawals"))

    db.session.commit()
    return redirect(url_for("admin_withdrawals", status=withdrawal.status))

@app.route("/admin/tokenomics")
@admin_required
def admin_tokenomics():
    settings = GlobalSetting.query.all()
    price_history = TokenPriceHistory.query.order_by(TokenPriceHistory.timestamp.desc()).limit(20).all()
    return render_template("admin/tokenomics.html", settings=settings, price_history=price_history)

@app.route("/admin/referrals")
@admin_required
def admin_referrals():
    page = request.args.get("page", 1, type=int)
    
    total_referrals_made = Referral.query.count()
    number_of_referrers = db.session.query(func.count(func.distinct(Referral.referrer_user_id))).scalar() or 0
    average_referrals_per_referrer = (total_referrals_made / number_of_referrers) if number_of_referrers > 0 else 0

    top_referrers_query = db.session.query(
        User.username,
        User.email,
        User.personal_rate_bonus,
        func.count(Referral.id).label("referral_count")
    ).join(Referral, User.id == Referral.referrer_user_id)\
     .group_by(User.id)\
     .order_by(func.count(Referral.id).desc())
    
    top_referrers_pagination = top_referrers_query.paginate(page=page, per_page=15)
    return render_template("admin/referrals.html", 
                           top_referrers_pagination=top_referrers_pagination,
                           total_referrals_made=total_referrals_made,
                           number_of_referrers=number_of_referrers,
                           average_referrals_per_referrer=round(average_referrals_per_referrer, 2)
                           )

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        initialize_global_settings()
    app.run(host="0.0.0.0", port=5000, debug=True)

