# app.py
import os, csv, io, random
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image

from config import Config
from models import db, User, Notification, Contact, Admin, AdminDirector, Nouveaute, NouveauteLue, Transaction

app = Flask(__name__)
app.config.from_object(Config)
app.config['UPLOAD_FOLDER'] = os.path.join("static", "uploads")
app.config['ALLOWED_IMAGE_EXT'] = {"png", "jpg", "jpeg", "gif", "webp"}
db.init_app(app)

# --- Timezone helpers ---
# Kinshasa is UTC+1
KINSHASA_TZ = timezone(timedelta(hours=1))

def now_utc():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

def make_aware(dt):
    """
    Ensure a datetime is timezone-aware.
    If dt is naive, assume it is stored in UTC and attach timezone.utc.
    If dt is already aware, return as-is.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        # assume stored as UTC if naive in DB
        return dt.replace(tzinfo=timezone.utc)
    return dt

def to_kinshasa(dt):
    """Convert a datetime (naive or aware) to Kinshasa timezone and return an aware datetime."""
    a = make_aware(dt)
    if a is None:
        return None
    return a.astimezone(KINSHASA_TZ)

# --- Utils ---
def generate_account_number():
    digits = ''.join([str(random.randint(0,9)) for _ in range(9)])
    return f"STL-{digits[:3]}-{digits[3:6]}-{digits[6:9]}"

def allowed_image(filename):
    return '.' in filename and filename.rsplit('.',1)[1].lower() in app.config["ALLOWED_IMAGE_EXT"]

def ensure_monthly_fee(user: User):
    """
    Charge a monthly fee if none charged in the last 30 days.
    Uses timezone-aware datetimes (assumes DB stored times in UTC if naive).
    """
    last_fee = Transaction.query.filter_by(user_id=user.id, type="frais de compte").order_by(Transaction.created_at.desc()).first()
    # Determine whether we should charge
    if not last_fee:
        should_charge = True
    else:
        last_fee_time = make_aware(last_fee.created_at)
        should_charge = (now_utc() - last_fee_time) >= timedelta(days=30)

    if should_charge:
        if Decimal(user.solde) > 0:
            fee = (Decimal(user.solde) * Decimal("0.05")).quantize(Decimal("0.01"))
            user.solde = (Decimal(user.solde) - fee).quantize(Decimal("0.01"))
            t = Transaction(user_id=user.id, type="frais de compte", montant=-fee, created_at=now_utc())
            db.session.add(t)
            db.session.add(Notification(username=user.username, statut=f"Frais de compte : -{fee} {app.config.get('DEFAULT_CURRENCY','CDF')}", created_at=now_utc()))
            db.session.commit()

def log_status(username, statut):
    db.session.add(Notification(username=username, statut=statut, created_at=now_utc()))
    db.session.commit()

def require_user():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return None

def require_admin():
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))
    return None

def require_admin_director():
    if "admin_director_id" not in session:
        return redirect(url_for("admin_director_login"))
    return None

# --- CLI init (optionnel en dev) ---
@app.cli.command("init-db")
def init_db():
    with app.app_context():
        db.create_all()
        print("DB created")

# --- Routes publiques ---
@app.route("/")
def index():
    return render_template("index.html", page="accueil")

@app.route("/services")
def services():
    return render_template("services.html", page="services")

@app.route("/politique")
def politique():
    return render_template("politique.html", page="politique")

@app.route("/nouveautes")
def nouveautes():
    user_id = session.get("user_id")
    items = Nouveaute.query.order_by(Nouveaute.date_publication.desc()).all()
    if user_id:
        existing_ids = {nl.nouveaute_id for nl in NouveauteLue.query.filter_by(user_id=user_id).all()}
        for n in items:
            if n.id not in existing_ids:
                db.session.add(NouveauteLue(user_id=user_id, nouveaute_id=n.id))
        db.session.commit()
    return render_template("nouveautes.html", page="nouveautes", items=items)

@app.route("/a-propos")
def a_propos():
    return render_template("a_propos.html", page="a_propos")

@app.route("/contact", methods=["GET","POST"])
def contact():
    if request.method == "POST":
        data = {k: request.form.get(k, "").strip() for k in ["nom","post_nom","prenom","email","telephone","message"]}
        if not all(data.values()):
            flash("Veuillez remplir tous les champs.", "danger")
            return redirect(url_for("contact"))
        c = Contact(**data)
        db.session.add(c)
        db.session.commit()
        flash("Message envoyé. Merci !", "success")
        return redirect(url_for("contact"))
    return render_template("contact.html", page="contact")

# --- Auth utilisateur ---
@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        form = request.form
        required = ["nom","post_nom","prenom","sexe","adresse_residence","telephone","email","password","confirm"]
        if not all(form.get(k,"").strip() for k in required):
            flash("Tous les champs sont obligatoires.", "danger")
            return redirect(url_for("signup"))

        if form["password"] != form["confirm"]:
            flash("Les mots de passe ne correspondent pas.", "danger")
            return redirect(url_for("signup"))

        email = form["email"].strip().lower()
        if User.query.filter_by(email=email).first():
            flash("Cet email est déjà utilisé !", "danger")
            return redirect(url_for("signup"))

        username = (form["nom"] + form["prenom"]).upper().replace(" ", "")
        if User.query.filter_by(username=username).first():
            username = username + str(random.randint(100,999))

        numero_compte = generate_account_number()
        while User.query.filter_by(numero_compte=numero_compte).first():
            numero_compte = generate_account_number()

        # 📸 Gestion de la photo
        photo = request.files.get("photo_profil")
        photo_path = None

        if photo and photo.filename != "":
            if allowed_image(photo.filename):
                photo_filename = secure_filename(photo.filename)
                photo_filename = f"{username}_{photo_filename}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], photo_filename)
                # create upload folder if not exists
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                photo.save(save_path)
                photo_path = f"uploads/{photo_filename}"
            else:
                flash("Format de photo non autorisé.", "danger")
                return redirect(url_for("signup"))

        # 👤 Création utilisateur
        u = User(
            nom=form["nom"].strip(),
            post_nom=form["post_nom"].strip(),
            prenom=form["prenom"].strip(),
            username=username,
            sexe=form["sexe"],
            adresse_residence=form["adresse_residence"].strip(),
            telephone=form["telephone"].strip(),
            email=email,
            photo_profil=photo_path,
            numero_compte=numero_compte,
            solde=Decimal("0.00"),
            password_hash=generate_password_hash(form["password"])
        )
        statut = f"{u.nom}_{u.post_nom}_{u.prenom}"
        # Notify admin / log
        db.session.add(Notification(username=u.email, statut=f"Nouveau client (e): {statut}", created_at=now_utc()))
        db.session.add(u)
        db.session.commit()
        flash("Compte créé, vous pouvez vous connecter.", "success")
        return redirect(url_for("login"))

    # ✅ Si GET, on renvoie toujours une page
    return render_template("signup.html", page="services")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        identifier = request.form.get("identifier","").strip()
        password = request.form.get("password","").strip()
        if not identifier or not password:
            flash("Veuillez renseigner email/username et mot de passe.", "danger")
            return redirect(url_for("login"))
        user = User.query.filter((User.email==identifier.lower()) | (User.username==identifier.upper())).first()
        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session["user_id"] = user.id
            ensure_monthly_fee(user)
            flash("Connexion réussie.", "success")
            return redirect(url_for("dashboard"))
        flash("Identifiants invalides.", "danger")
    return render_template("login.html", page="services")

@app.route("/forgot", methods=["POST"])
def forgot():
    identifier = request.form.get("identifier","").strip()
    if not identifier:
        flash("Veuillez saisir d’abord votre email ou username.", "danger")
        return redirect(url_for("login"))
    flash("Votre demande de récupération est envoyée, nous vous contacterons incessamment !", "success")
    db.session.add(Notification(username=identifier.upper(), statut="Demande récupération (email/username + mot de passe oublié)", created_at=now_utc()))
    db.session.commit()
    return redirect(url_for("login"))

@app.route("/logout")
def logout():
    uid = session.get("user_id")
    if uid:
        user = User.query.get(uid)
        if user:
            log_status(user.username, "s’est déconnecté")
    session.clear()
    return redirect(url_for("index"))

# --- Dashboard utilisateur ---
@app.route("/dashboard")
def dashboard():
    guard = require_user()
    if guard: return guard
    user = User.query.get(session["user_id"])
    ensure_monthly_fee(user)  # sécurité
    notifs = Notification.query.filter_by(username=user.username).order_by(Notification.created_at.desc()).limit(100).all()

    # Convert created_at to Kinshasa timezone for display
    for n in notifs:
        n.created_at = to_kinshasa(n.created_at)

    all_news_ids = [n.id for n in Nouveaute.query.all()]
    read_ids = {nl.nouveaute_id for nl in NouveauteLue.query.filter_by(user_id=user.id).all()}
    unread_count = len(set(all_news_ids) - read_ids)
    return render_template("dashboard.html", user=user, notifs=notifs, unread_count=unread_count)

@app.route("/dashboard/releve.pdf", endpoint="download_releve")
def download_releve_pdf():
    guard = require_user()
    if guard: return guard
    user = User.query.get(session["user_id"])
    txs = Transaction.query.filter_by(user_id=user.id).order_by(Transaction.created_at.asc()).all()

    # buffer mémoire pour stocker le PDF
    buffer = io.BytesIO()

    # Création du document
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30,leftMargin=30, topMargin=30,bottomMargin=18)
    elements = []

    # --- Logo + titre ---
    logo_path = os.path.join("static", "LOGO OFFICIEL STIMLINK.png")
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=80, height=80)
        elements.append(logo)

    styles = getSampleStyleSheet()
    title_style = styles["Heading1"]
    title_style.textColor = colors.HexColor("#004080")  # Bleu foncé
    elements.append(Paragraph("Relevé des opérations - StimLink Épargne", title_style))
    elements.append(Spacer(1, 12))

    # --- Infos client ---
    info_style = styles["Normal"]
    info_text = f"""
    <b>Noms :</b> {user.nom} {user.post_nom} {user.prenom}<br/>
    <b>Numéro de compte :</b> {user.numero_compte}<br/>
    <b>Solde actuel :</b> {user.solde:,.2f} CDF
    """
    elements.append(Paragraph(info_text, info_style))
    elements.append(Spacer(1, 12))

    # --- Tableau transactions ---
    data = [["Date", "Type", "Montant (CDF)", "Solde cumulatif (CDF)"]]
    running = Decimal("0.00")

    for t in txs:
        running += Decimal(t.montant)
        date_str = to_kinshasa(t.created_at).strftime("%d-%m-%Y %H:%M")
        data.append([
            date_str,
            t.type.capitalize(),
            f"{Decimal(t.montant):,.2f}",
            f"{running:,.2f}"
        ])

    table = Table(data, colWidths=[110, 140, 120, 120])

    # Styles tableau
    style = TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#004080")),  # ligne header
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("BOTTOMPADDING", (0,0), (-1,0), 10),
        ("BACKGROUND", (0,1), (-1,-1), colors.whitesmoke),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey)
    ])
    table.setStyle(style)

    elements.append(table)

    # --- Générer le PDF ---
    doc.build(elements)
    buffer.seek(0)

    return send_file(buffer, mimetype="application/pdf",
                     as_attachment=True,
                     download_name=f"releve_{user.numero_compte}.pdf")

# --- Admin Auth ---
@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password_hash, password):
            session.clear()
            session["admin_id"] = admin.id
            flash("Admin connecté.", "success")
            return redirect(url_for("admin_panel"))
        flash("Identifiants invalides.", "danger")
    return render_template("admin.html", login_only=True)

@app.route("/admin_director/login", methods=["GET","POST"])
def admin_director_login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        adm = AdminDirector.query.filter_by(username=username).first()
        if adm and check_password_hash(adm.password_hash, password):
            session["admin_director_id"] = adm.id
            flash("Admin Director connecté.", "success")
            return redirect(url_for("admin_director_panel"))
        flash("Identifiants invalides.", "danger")
    return render_template("admin_director.html", login_only=True)


# --- Admin Panel ---
@app.route("/admin", methods=["GET","POST"])
def admin_panel():
    guard = require_admin()
    if guard: return guard

    stats = {
        "nb_users": User.query.count(),
        "nb_messages": Contact.query.count(),
        "total_solde": db.session.query(db.func.coalesce(db.func.sum(User.solde), 0)).scalar()
    }

    last_notifs = Notification.query.order_by(Notification.created_at.desc()).limit(200).all()
    contacts = Contact.query.order_by(Contact.created_at.desc()).limit(200).all()

    # Convert timestamps to Kinshasa for display
    for n in last_notifs:
        n.created_at = to_kinshasa(n.created_at)
    for c in contacts:
        if hasattr(c, "created_at"):
            c.created_at = to_kinshasa(c.created_at)

    if request.method == "POST":
        action = request.form.get("action")
        numero_compte = request.form.get("numero_compte", "").strip()
        user = User.query.filter_by(numero_compte=numero_compte).first()
        if not user:
            flash("Compte introuvable !", "danger")
            return redirect(url_for("admin_panel"))

        if action == "credit_debit":
            type_tx = request.form.get("type_tx")
            try:
                montant = Decimal(request.form.get("montant", "0").replace(",", "."))
            except:
                flash("Montant invalide !", "danger"); return redirect(url_for("admin_panel"))
            confirm = request.form.get("confirm") == "on"
            if not confirm:
                flash("Veuillez confirmer l’opération !", "warning"); return redirect(url_for("admin_panel"))
            if montant <= 0:
                flash("Le montant doit être positif !", "danger"); return redirect(url_for("admin_panel"))

            if type_tx == "debit":
                user.solde = (Decimal(user.solde) + montant).quantize(Decimal("0.01"))
                db.session.add(Transaction(user_id=user.id, type="debit", montant=montant, created_at=now_utc()))
                db.session.add(Notification(username=user.username, statut=f"Débit : +{montant} {app.config.get('DEFAULT_CURRENCY','CDF')}", created_at=now_utc()))
                db.session.commit()
                flash("Débit enregistré avec succès...", "success")
            elif type_tx == "credit":
                total_to_debit = montant.quantize(Decimal("0.01"))
                fee = (montant * Decimal("0.04")).quantize(Decimal("0.01"))
                total_needed = (total_to_debit + fee)
                if Decimal(user.solde) < total_needed:
                    flash("Solde insuffisant pour effectuer cette opération !", "danger"); return redirect(url_for("admin_panel"))
                user.solde = (Decimal(user.solde) - total_to_debit - fee).quantize(Decimal("0.01"))
                db.session.add(Transaction(user_id=user.id, type="credit", montant=-total_to_debit, created_at=now_utc()))
                db.session.add(Transaction(user_id=user.id, type="frais de retrait", montant=-fee, created_at=now_utc()))
                db.session.add(Notification(username=user.username, statut=f"Crédit : -{total_to_debit} {app.config.get('DEFAULT_CURRENCY','CDF')}", created_at=now_utc()))
                db.session.add(Notification(username=user.username, statut=f"Frais de retrait : -{fee} {app.config.get('DEFAULT_CURRENCY','CDF')}", created_at=now_utc()))
                db.session.commit()
                flash("Crédit enregistré avec succès.", "success")
            else:
                flash("Type d’opération inconnu !", "danger")

        elif action == "message":
            msg = request.form.get("message", "").strip()
            if msg:
                db.session.add(Notification(username=user.username, statut=f"Service client : {msg}", created_at=now_utc()))
                db.session.commit()
                flash("Message envoyé avec succès", "success")
            else:
                flash("Message vide !", "warning")

        return redirect(url_for("admin_panel"))

    return render_template("admin.html",
                           login_only=False,
                           stats=stats,
                           notifs=last_notifs,
                           contacts=contacts)


# --- Admin Director Panel ---
@app.route("/admin-director", methods=["GET","POST"])
def admin_director_panel():
    guard = require_admin_director()
    if guard: return guard

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add_news":
            titre = request.form.get("titre", "").strip()
            contenu = request.form.get("contenu","").strip()
            if not titre or not contenu:
                flash("Titre et contenu requis !", "danger")
            else:
                db.session.add(Nouveaute(titre=titre, contenu=contenu, date_publication=now_utc()))
                db.session.commit()
                flash("Nouvelle ajoutée !", "success")
        elif action == "delete_news":
            nid = request.form.get("nid")
            n = Nouveaute.query.get(nid)
            if n:
                db.session.delete(n)
                db.session.commit()
                flash("Nouvelle supprimée !", "success")
        elif action == "reset_password":
            identifier = request.form.get("identifier", "").strip()
            user = User.query.filter((User.email==identifier.lower()) | (User.username==identifier.upper())).first()
            if user:
                temp = f"TMP{random.randint(1000000, 9999999)}"
                user.password_hash = generate_password_hash(temp)
                db.session.add(Notification(username=user.username, statut=f"Mot de passe réinitialisé. Nouveau mot de passe: {temp}", created_at=now_utc()))
                db.session.commit()
                flash("Mot de passe réinitialisé avec succès (le nouveau mot de passe est communiqué via notification).", "success")
            else:
                flash("Utilisateur introuvable !", "danger")
        return redirect(url_for("admin_director_panel"))

    news = Nouveaute.query.order_by(Nouveaute.date_publication.desc()).all()
    for n in news:
        if hasattr(n, "date_publication"):
            n.date_publication = to_kinshasa(n.date_publication)
    return render_template("admin_director.html", news=news)


@app.route("/micro-credit")
def micro_credit():
    flash("Ce service n’est pas encore disponible, merci pour votre fidélité.", "info")
    return redirect(url_for("services"))


# --- Helpers contextuels pour Jinja ---
@app.context_processor
def inject_ui():
    unread = 0
    uid = session.get("user_id")
    if uid:
        all_ids = [n.id for n in Nouveaute.query.all()]
        read_ids = {nl.nouveaute_id for nl in NouveauteLue.query.filter_by(user_id=uid).all()}
        unread = len(set(all_ids) - read_ids)
    return dict(unread_news=unread)


if __name__ == "__main__":
    # Créer la DB / tables en affichant un message utile si la connexion fail
    with app.app_context():
        try:
            db.create_all()
            print("✅ Base de données initialisée (tables créées).")
        except Exception as e:
            # Erreur de connexion (ex: psycopg2.OperationalError si Postgres indisponible)
            print("‼️ Impossible de créer les tables :")
            print(str(e))
            print("\nAstuce: si vous utilisez PostgreSQL, vérifiez que le service tourne et que la variable d'environnement DATABASE_URL est bien définie.")
            print("Exemple (Linux/macOS): export DATABASE_URL='postgresql+psycopg2://user:pass@localhost:5432/dbname'")
            print("Exemple (Windows PowerShell): $env:DATABASE_URL = 'postgresql+psycopg2://user:pass@localhost:5432/dbname'")
            raise

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=app.config.get("DEBUG", True))
