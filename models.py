# models.py
from datetime import datetime, timezone
from decimal import Decimal
from flask_sqlalchemy import SQLAlchemy
from datetime import timezone, timedelta

db = SQLAlchemy()

KINSHASA_TZ = timezone(timedelta(hours=1))  # UTC+1


def now_utc():
    # renvoie naive UTC pour SQLAlchemy; on peut adapter pour timezone-aware si voulu
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(120), nullable=False)
    post_nom = db.Column(db.String(120), nullable=False)
    prenom = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    sexe = db.Column(db.String(10))
    adresse_residence = db.Column(db.String(250))
    telephone = db.Column(db.String(50))
    email = db.Column(db.String(150), unique=True, nullable=False)
    photo_profil = db.Column(db.String(300))
    numero_compte = db.Column(db.String(50), unique=True, nullable=False)
    solde = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc)

    # Repr utile pour debug
    def __repr__(self):
        return f"<User {self.username} ({self.numero_compte})>"


class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)  # destinataire (username ou identifiant générique)
    statut = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc)

    @property
    def to_kinshasa(self):
        if self.created_at.tzinfo is None:
            return self.created_at.replace(tzinfo=timezone.utc).astimezone(KINSHASA_TZ)
        return self.created_at.astimezone(KINSHASA_TZ)


class Contact(db.Model):
    __tablename__ = "contacts"
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(120), nullable=False)
    post_nom = db.Column(db.String(120), nullable=False)
    prenom = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), nullable=False)
    telephone = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc)


class Admin(db.Model):
    __tablename__ = "admins"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc)


class AdminDirector(db.Model):
    __tablename__ = "admin_directors"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc)


class Nouveaute(db.Model):
    __tablename__ = "nouveautes"
    id = db.Column(db.Integer, primary_key=True)
    titre = db.Column(db.String(250), nullable=False)
    contenu = db.Column(db.Text, nullable=False)
    date_publication = db.Column(db.DateTime(timezone=True), default=now_utc)


class NouveauteLue(db.Model):
    __tablename__ = "nouveautes_lues"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    nouveaute_id = db.Column(db.Integer, nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc)


class Transaction(db.Model):
    __tablename__ = "transactions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, index=True)
    type = db.Column(db.String(120), nullable=False)  # ex: 'credit', 'debit', 'frais de compte'
    montant = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc)
