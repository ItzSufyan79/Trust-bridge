import csv
import hmac
import os
import sqlite3
from datetime import datetime, timedelta
from hashlib import pbkdf2_hmac
from typing import Optional
from uuid import uuid4
from pathlib import Path
import os
import requests
from fpdf import FPDF
from fastapi import Depends, FastAPI, HTTPException, Header, Request, Response, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

DB_PATH = "./trustbridge.db"
ADMIN_INVITE_CODE = os.getenv("TB_ADMIN_INVITE")
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL")
APP_BASE_URL = os.getenv("APP_BASE_URL")
AUDIT_CSV_PATH = os.getenv(
    "AUDIT_CSV_PATH", "/Users/sufyanbahauddin/TrustBridge/web/Credentials/Audit.csv"
)

app = FastAPI(title="TrustBridge API", version="0.2.0")

try:
    os.makedirs("uploads", exist_ok=True)
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
except Exception as e:
    print(f"CRITICAL STARTUP ERROR: {e}")
    raise e

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(conn, table: str, column: str, ddl: str) -> None:
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if column not in {row[1] for row in cols}:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tokens (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            id TEXT PRIMARY KEY,
            seller_id TEXT NOT NULL,
            name TEXT NOT NULL,
            sku TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER NOT NULL,
            reserved INTEGER NOT NULL DEFAULT 0,
            market_low REAL,
            market_high REAL,
            image_url TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(seller_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            buyer_id TEXT NOT NULL,
            seller_id TEXT NOT NULL,
            inventory_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            payment_status TEXT NOT NULL,
            stock_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            payment_reference TEXT,
            payment_paid_at TEXT,
            razorpay_order_id TEXT,
            razorpay_payment_id TEXT,
            razorpay_signature TEXT,
            FOREIGN KEY(buyer_id) REFERENCES users(id),
            FOREIGN KEY(seller_id) REFERENCES users(id),
            FOREIGN KEY(inventory_id) REFERENCES inventory(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            reference_id TEXT PRIMARY KEY,
            transaction_id TEXT NOT NULL,
            amount REAL NOT NULL,
            paid_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(transaction_id) REFERENCES transactions(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS disputes (
            id TEXT PRIMARY KEY,
            transaction_id TEXT NOT NULL,
            raised_by TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(transaction_id) REFERENCES transactions(id),
            FOREIGN KEY(raised_by) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS proofs (
            id TEXT PRIMARY KEY,
            transaction_id TEXT NOT NULL,
            uploaded_by TEXT NOT NULL,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(transaction_id) REFERENCES transactions(id),
            FOREIGN KEY(uploaded_by) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS webhook_events (
            id TEXT PRIMARY KEY,
            event TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            email TEXT,
            action TEXT NOT NULL,
            ip TEXT,
            user_agent TEXT,
            metadata TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    ensure_column(conn, "transactions", "razorpay_order_id", "razorpay_order_id TEXT")
    ensure_column(conn, "transactions", "razorpay_payment_id", "razorpay_payment_id TEXT")
    ensure_column(conn, "transactions", "razorpay_signature", "razorpay_signature TEXT")
    ensure_column(conn, "inventory", "image_url", "image_url TEXT")
    ensure_column(conn, "disputes", "resolution_note", "resolution_note TEXT")
    ensure_column(conn, "disputes", "resolved_at", "resolved_at TEXT")
    ensure_column(conn, "disputes", "resolved_by", "resolved_by TEXT")
    conn.commit()
    conn.close()
    Path(AUDIT_CSV_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path("uploads").mkdir(parents=True, exist_ok=True)


@app.on_event("startup")
def on_startup():
    init_db()


class RegisterPayload(BaseModel):
    email: str
    password: str = Field(..., min_length=6)
    role: str = Field(..., pattern="^(buyer|seller|admin)$")
    name: str


class LoginPayload(BaseModel):
    email: str
    password: str


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6)


class InventoryCreate(BaseModel):
    name: str
    sku: str
    price: float = Field(..., gt=0)
    stock: int = Field(..., ge=0)
    market_low: Optional[float] = None
    market_high: Optional[float] = None
    image_url: Optional[str] = None


class TransactionCreate(BaseModel):
    inventory_id: str
    quantity: int = Field(..., gt=0)


class PaymentVerification(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class DisputeCreate(BaseModel):
    transaction_id: str
    reason: str


class DisputeResolve(BaseModel):
    status: str = Field(..., pattern="^(resolved|rejected)$")
    resolution_note: str


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    name: str


class AuthResponse(BaseModel):
    token: str
    user: UserOut


def hash_password(password: str, salt: str) -> str:
    return pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120000).hex()


def create_token(user_id: str) -> str:
    token = uuid4().hex
    expires_at = (datetime.utcnow() + timedelta(days=7)).isoformat()
    conn = db()
    conn.execute(
        "INSERT INTO tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, expires_at),
    )
    conn.commit()
    conn.close()
    return token


def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    conn = db()
    row = conn.execute(
        "SELECT tokens.token, tokens.expires_at, users.* FROM tokens JOIN users ON tokens.user_id = users.id WHERE tokens.token = ?",
        (token,),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid token")
    if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Token expired")
    return row


def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def require_razorpay_keys():
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise HTTPException(status_code=500, detail="Razorpay keys not configured")


def razorpay_request(method: str, path: str, payload: Optional[dict] = None) -> dict:
    require_razorpay_keys()
    url = f"https://api.razorpay.com{path}"
    res = requests.request(
        method,
        url,
        auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
        json=payload,
        timeout=20,
    )
    if res.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Razorpay error: {res.text}")
    return res.json()


def verify_razorpay_signature(order_id: str, payment_id: str, signature: str) -> bool:
    message = f"{order_id}|{payment_id}".encode()
    expected = hmac.new(RAZORPAY_KEY_SECRET.encode(), message, "sha256").hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    if not RAZORPAY_WEBHOOK_SECRET:
        return False
    expected = hmac.new(RAZORPAY_WEBHOOK_SECRET.encode(), body, "sha256").hexdigest()
    return hmac.compare_digest(expected, signature)


def require_sendgrid():
    if not SENDGRID_API_KEY or not SENDGRID_FROM_EMAIL:
        raise HTTPException(status_code=500, detail="SendGrid not configured")


def send_reset_email(to_email: str, token: str) -> None:
    require_sendgrid()
    reset_link = f"{APP_BASE_URL.rstrip('/')}/reset?token={token}"
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": SENDGRID_FROM_EMAIL},
        "subject": "Reset your TrustBridge password",
        "content": [
            {
                "type": "text/plain",
                "value": f"Use this link to reset your password: {reset_link}",
            }
        ],
    }
    res = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=20,
    )
    if res.status_code not in (200, 202):
        raise HTTPException(status_code=502, detail=f"SendGrid error: {res.text}")


def audit_event(
    conn,
    action: str,
    user_id: Optional[str],
    email: Optional[str],
    request: Optional[Request],
    metadata: Optional[str] = None,
):
    ip = None
    user_agent = None
    if request:
        ip = request.headers.get("x-forwarded-for") or request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
    conn.execute(
        """
        INSERT INTO audit_events (id, user_id, email, action, ip, user_agent, metadata, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uuid4().hex,
            user_id,
            email,
            action,
            ip,
            user_agent,
            metadata,
            datetime.utcnow().isoformat(),
        ),
    )
    row = [
        datetime.utcnow().isoformat(),
        user_id,
        email,
        action,
        ip,
        user_agent,
        metadata,
    ]
    file_exists = os.path.exists(AUDIT_CSV_PATH)
    with open(AUDIT_CSV_PATH, "a", newline="") as handle:
        writer = csv.writer(handle)
        if not file_exists:
            writer.writerow(
                ["created_at", "user_id", "email", "action", "ip", "user_agent", "metadata"]
            )
        writer.writerow(row)


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.post("/auth/register", response_model=AuthResponse)
def register(
    payload: RegisterPayload,
    request: Request,
    admin_invite: Optional[str] = Header(None, alias="X-Admin-Invite"),
):
    if payload.role == "admin" and admin_invite != ADMIN_INVITE_CODE:
        raise HTTPException(status_code=403, detail="Invalid admin invite")
    conn = db()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (payload.email,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered")
    user_id = uuid4().hex
    salt = uuid4().hex
    password_hash = hash_password(payload.password, salt)
    conn.execute(
        "INSERT INTO users (id, email, password_hash, salt, role, name, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            user_id,
            payload.email,
            password_hash,
            salt,
            payload.role,
            payload.name,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    audit_event(conn, "auth_register", user_id, payload.email, request, metadata=f"role={payload.role}")
    conn.commit()
    conn.close()
    token = create_token(user_id)
    return {
        "token": token,
        "user": {
            "id": user_id,
            "email": payload.email,
            "role": payload.role,
            "name": payload.name,
        },
    }


@app.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginPayload, request: Request):
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (payload.email,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    password_hash = hash_password(payload.password, row["salt"])
    if password_hash != row["password_hash"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(row["id"])
    conn = db()
    audit_event(conn, "auth_login", row["id"], row["email"], request)
    conn.commit()
    conn.close()
    return {
        "token": token,
        "user": {
            "id": row["id"],
            "email": row["email"],
            "role": row["role"],
            "name": row["name"],
        },
    }


@app.post("/auth/reset-request")
def reset_request(payload: PasswordResetRequest, request: Request):
    conn = db()
    user = conn.execute("SELECT id FROM users WHERE email = ?", (payload.email,)).fetchone()
    if not user:
        audit_event(conn, "password_reset_request", None, payload.email, request, metadata="no_user")
        conn.commit()
        conn.close()
        return {"status": "ok"}
    token = uuid4().hex
    expires_at = (datetime.utcnow() + timedelta(minutes=30)).isoformat()
    conn.execute(
        "INSERT INTO password_reset_tokens (token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (token, user["id"], expires_at, datetime.utcnow().isoformat()),
    )
    audit_event(conn, "password_reset_request", user["id"], payload.email, request)
    conn.commit()
    conn.close()
    send_reset_email(payload.email, token)
    return {"status": "ok"}


@app.post("/auth/reset-confirm")
def reset_confirm(payload: PasswordResetConfirm, request: Request):
    conn = db()
    row = conn.execute(
        "SELECT * FROM password_reset_tokens WHERE token = ?",
        (payload.token,),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid token")
    if row["used_at"] is not None:
        conn.close()
        raise HTTPException(status_code=400, detail="Token already used")
    if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        conn.close()
        raise HTTPException(status_code=400, detail="Token expired")
    salt = uuid4().hex
    password_hash = hash_password(payload.new_password, salt)
    conn.execute(
        "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
        (password_hash, salt, row["user_id"]),
    )
    conn.execute(
        "UPDATE password_reset_tokens SET used_at = ? WHERE token = ?",
        (datetime.utcnow().isoformat(), payload.token),
    )
    audit_event(conn, "password_reset_confirm", row["user_id"], None, request)
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.get("/me", response_model=UserOut)
def me(user=Depends(get_current_user)):
    return {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "name": user["name"],
    }


@app.post("/inventory")
def create_inventory(payload: InventoryCreate, user=Depends(get_current_user)):
    if user["role"] != "seller":
        raise HTTPException(status_code=403, detail="Only sellers can add inventory")
    item_id = uuid4().hex
    conn = db()
    conn.execute(
        """
        INSERT INTO inventory (id, seller_id, name, sku, price, stock, reserved, market_low, market_high, image_url, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
        """,
        (
            item_id,
            user["id"],
            payload.name,
            payload.sku,
            payload.price,
            payload.stock,
            payload.market_low,
            payload.market_high,
            payload.image_url,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    return {"id": item_id}


@app.post("/inventory/upload")
def upload_inventory(
    name: str = Form(...),
    sku: str = Form(...),
    price: float = Form(...),
    stock: int = Form(...),
    market_low: Optional[float] = Form(None),
    market_high: Optional[float] = Form(None),
    image_file: Optional[UploadFile] = File(None),
    google_drive_link: Optional[str] = Form(None),
    user=Depends(get_current_user),
):
    if user["role"] != "seller":
        raise HTTPException(status_code=403, detail="Only sellers can add inventory")

    item_id = uuid4().hex
    image_url = None
    if image_file:
        filename = f"{item_id}_{image_file.filename}"
        path = Path("uploads") / filename
        with open(path, "wb") as f:
            f.write(image_file.file.read())
        image_url = f"/uploads/{filename}"
    elif google_drive_link:
        if "drive.google.com" in google_drive_link:
            # if share URL includes /file/d/ID
            if "/file/d/" in google_drive_link:
                file_id = google_drive_link.split("/file/d/")[1].split("/")[0]
                image_url = f"https://drive.google.com/uc?export=view&id={file_id}"
            elif "id=" in google_drive_link:
                file_id = google_drive_link.split("id=")[1].split("&")[0]
                image_url = f"https://drive.google.com/uc?export=view&id={file_id}"
            else:
                image_url = google_drive_link
        else:
            raise HTTPException(status_code=400, detail="Invalid Google Drive link")

    conn = db()
    conn.execute(
        """
        INSERT INTO inventory (id, seller_id, name, sku, price, stock, reserved, market_low, market_high, image_url, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
        """,
        (
            item_id,
            user["id"],
            name,
            sku,
            price,
            stock,
            market_low,
            market_high,
            image_url,
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    return {"id": item_id}


@app.get("/inventory")
def list_inventory(user=Depends(get_current_user)):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM inventory WHERE seller_id = ? ORDER BY created_at DESC", (user["id"],)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.get("/inventory/public")
def list_public_inventory():
    conn = db()
    rows = conn.execute(
        """
        SELECT inventory.*, users.name as seller_name
        FROM inventory JOIN users ON inventory.seller_id = users.id
        ORDER BY inventory.created_at DESC
        """
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.post("/transactions")
def create_transaction(payload: TransactionCreate, user=Depends(get_current_user)):
    if user["role"] != "buyer":
        raise HTTPException(status_code=403, detail="Only buyers can initiate transactions")
    conn = db()
    item = conn.execute("SELECT * FROM inventory WHERE id = ?", (payload.inventory_id,)).fetchone()
    if not item:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")
    if item["stock"] < payload.quantity:
        conn.close()
        raise HTTPException(status_code=400, detail="Insufficient stock")
    transaction_id = f"TB-{uuid4().hex[:8].upper()}"
    expires_at = datetime.utcnow() + timedelta(minutes=15)
    conn.execute(
        """
        INSERT INTO transactions (id, buyer_id, seller_id, inventory_id, quantity, unit_price, payment_status, stock_status, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            transaction_id,
            user["id"],
            item["seller_id"],
            item["id"],
            payload.quantity,
            item["price"],
            "unverified",
            "reserved",
            datetime.utcnow().isoformat(),
            expires_at.isoformat(),
        ),
    )
    conn.execute(
        "UPDATE inventory SET stock = stock - ?, reserved = reserved + ? WHERE id = ?",
        (payload.quantity, payload.quantity, item["id"]),
    )
    conn.commit()
    conn.close()
    return {"id": transaction_id}


@app.post("/transactions/{transaction_id}/create-order")
def create_order(transaction_id: str, user=Depends(get_current_user)):
    if user["role"] != "buyer":
        raise HTTPException(status_code=403, detail="Only buyers can create orders")
    conn = db()
    tx = conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    if not tx:
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction not found")
    if tx["buyer_id"] != user["id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="Not allowed")
    if tx["razorpay_order_id"]:
        conn.close()
        return {
            "order_id": tx["razorpay_order_id"],
            "key_id": RAZORPAY_KEY_ID,
            "amount": int(tx["unit_price"] * tx["quantity"] * 100),
            "currency": "INR",
        }
    require_razorpay_keys()
    amount_paise = int(tx["unit_price"] * tx["quantity"] * 100)
    order = razorpay_request(
        "POST",
        "/v1/orders",
        {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": tx["id"],
            "payment_capture": 1,
        },
    )
    conn.execute(
        "UPDATE transactions SET razorpay_order_id = ? WHERE id = ?",
        (order["id"], transaction_id),
    )
    conn.commit()
    conn.close()
    return {
        "order_id": order["id"],
        "key_id": RAZORPAY_KEY_ID,
        "amount": amount_paise,
        "currency": "INR",
    }


@app.get("/transactions")
def list_transactions(user=Depends(get_current_user)):
    conn = db()
    if user["role"] == "buyer":
        rows = conn.execute(
            """
            SELECT transactions.*, inventory.name as item_name
            FROM transactions JOIN inventory ON transactions.inventory_id = inventory.id
            WHERE buyer_id = ? ORDER BY created_at DESC
            """,
            (user["id"],),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT transactions.*, inventory.name as item_name
            FROM transactions JOIN inventory ON transactions.inventory_id = inventory.id
            WHERE seller_id = ? ORDER BY created_at DESC
            """,
            (user["id"],),
        ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: str, user=Depends(get_current_user)):
    conn = db()
    row = conn.execute(
        """
        SELECT transactions.*, inventory.name as item_name, inventory.market_low, inventory.market_high
        FROM transactions JOIN inventory ON transactions.inventory_id = inventory.id
        WHERE transactions.id = ?
        """,
        (transaction_id,),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if user["id"] not in (row["buyer_id"], row["seller_id"]):
        raise HTTPException(status_code=403, detail="Not allowed")
    return dict(row)


def _payment_status(amount: float, expected: float, duplicate: bool) -> str:
    if duplicate:
        return "duplicate"
    if abs(amount - expected) > 0.01:
        return "pending"
    return "verified"


@app.post("/transactions/{transaction_id}/verify-payment")
def verify_payment(transaction_id: str, payload: PaymentVerification, user=Depends(get_current_user)):
    conn = db()
    tx = conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    if not tx:
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction not found")
    if user["id"] not in (tx["buyer_id"], tx["seller_id"]):
        conn.close()
        raise HTTPException(status_code=403, detail="Not allowed")
    require_razorpay_keys()
    if not verify_razorpay_signature(
        payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature
    ):
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid Razorpay signature")
    payment = razorpay_request("GET", f"/v1/payments/{payload.razorpay_payment_id}")
    if payment.get("order_id") != payload.razorpay_order_id:
        conn.close()
        raise HTTPException(status_code=400, detail="Payment order mismatch")
    status = payment.get("status", "pending")
    if status in ("authorized", "captured"):
        status = "verified"
    elif status == "failed":
        status = "failed"
    else:
        status = "pending"
    conn.execute(
        "UPDATE transactions SET payment_status = ?, razorpay_order_id = ?, razorpay_payment_id = ?, razorpay_signature = ? WHERE id = ?",
        (
            status,
            payload.razorpay_order_id,
            payload.razorpay_payment_id,
            payload.razorpay_signature,
            transaction_id,
        ),
    )
    conn.commit()
    conn.close()
    return {"payment_status": status}


@app.post("/transactions/{transaction_id}/poll-status")
def poll_status(transaction_id: str, user=Depends(get_current_user)):
    require_razorpay_keys()
    conn = db()
    tx = conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    if not tx:
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction not found")
    if user["id"] not in (tx["buyer_id"], tx["seller_id"]):
        conn.close()
        raise HTTPException(status_code=403, detail="Not allowed")
    status = tx["payment_status"]
    payment_id = tx["razorpay_payment_id"]
    order_id = tx["razorpay_order_id"]
    if payment_id:
        payment = razorpay_request("GET", f"/v1/payments/{payment_id}")
        status = payment.get("status", "pending")
    elif order_id:
        payments = razorpay_request("GET", f"/v1/orders/{order_id}/payments")
        items = payments.get("items", [])
        if items:
            payment = items[0]
            payment_id = payment.get("id")
            status = payment.get("status", "pending")
            if payment_id:
                conn.execute(
                    "UPDATE transactions SET razorpay_payment_id = ? WHERE id = ?",
                    (payment_id, transaction_id),
                )
    if status in ("authorized", "captured"):
        status = "verified"
    elif status == "failed":
        status = "failed"
    else:
        status = "pending"
    conn.execute("UPDATE transactions SET payment_status = ? WHERE id = ?", (status, transaction_id))
    conn.commit()
    conn.close()
    return {"payment_status": status}


@app.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request, x_razorpay_signature: Optional[str] = Header(None)):
    if not x_razorpay_signature:
        raise HTTPException(status_code=400, detail="Missing signature")
    body = await request.body()
    if not verify_webhook_signature(body, x_razorpay_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    payload = await request.json()
    event_id = payload.get("id") or uuid4().hex
    event = payload.get("event", "unknown")
    conn = db()
    existing = conn.execute("SELECT id FROM webhook_events WHERE id = ?", (event_id,)).fetchone()
    if existing:
        conn.close()
        return {"status": "duplicate"}
    conn.execute(
        "INSERT INTO webhook_events (id, event, created_at) VALUES (?, ?, ?)",
        (event_id, event, datetime.utcnow().isoformat()),
    )
    payment_entity = (payload.get("payload", {}) or {}).get("payment", {}).get("entity", {})
    order_entity = (payload.get("payload", {}) or {}).get("order", {}).get("entity", {})
    order_id = payment_entity.get("order_id") or order_entity.get("id")
    payment_id = payment_entity.get("id")
    status = payment_entity.get("status")
    if order_id:
        tx = conn.execute(
            "SELECT id FROM transactions WHERE razorpay_order_id = ?",
            (order_id,),
        ).fetchone()
        if tx:
            if status in ("authorized", "captured"):
                status = "verified"
            elif status == "failed":
                status = "failed"
            else:
                status = "pending"
            conn.execute(
                "UPDATE transactions SET payment_status = ?, razorpay_payment_id = ? WHERE id = ?",
                (status, payment_id, tx["id"]),
            )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/disputes")
def create_dispute(payload: DisputeCreate, user=Depends(get_current_user)):
    conn = db()
    tx = conn.execute("SELECT * FROM transactions WHERE id = ?", (payload.transaction_id,)).fetchone()
    if not tx:
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction not found")
    if user["id"] not in (tx["buyer_id"], tx["seller_id"]):
        conn.close()
        raise HTTPException(status_code=403, detail="Not allowed")
    dispute_id = uuid4().hex
    conn.execute(
        "INSERT INTO disputes (id, transaction_id, raised_by, reason, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (dispute_id, payload.transaction_id, user["id"], payload.reason, "open", datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return {"id": dispute_id}


@app.get("/disputes/{dispute_id}")
def get_dispute(dispute_id: str, user=Depends(get_current_user)):
    conn = db()
    row = conn.execute("SELECT * FROM disputes WHERE id = ?", (dispute_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Dispute not found")
    return dict(row)


@app.get("/admin/disputes")
def list_disputes(admin=Depends(require_admin)):
    conn = db()
    rows = conn.execute(
        """
        SELECT disputes.*, buyers.name as buyer_name, sellers.name as seller_name
        FROM disputes
        JOIN transactions ON disputes.transaction_id = transactions.id
        JOIN users buyers ON transactions.buyer_id = buyers.id
        JOIN users sellers ON transactions.seller_id = sellers.id
        ORDER BY disputes.created_at DESC
        """
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.get("/admin/audits/export")
def export_audits(admin=Depends(require_admin)):
    conn = db()
    rows = conn.execute(
        "SELECT id, user_id, email, action, ip, user_agent, metadata, created_at FROM audit_events ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    with open(AUDIT_CSV_PATH, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["id", "user_id", "email", "action", "ip", "user_agent", "metadata", "created_at"]
        )
        for row in rows:
            writer.writerow(
                [
                    row["id"],
                    row["user_id"],
                    row["email"],
                    row["action"],
                    row["ip"],
                    row["user_agent"],
                    row["metadata"],
                    row["created_at"],
                ]
            )
    return {"status": "ok", "file": AUDIT_CSV_PATH}


@app.post("/admin/disputes/{dispute_id}/resolve")
def resolve_dispute(dispute_id: str, payload: DisputeResolve, admin=Depends(require_admin)):
    conn = db()
    row = conn.execute("SELECT id FROM disputes WHERE id = ?", (dispute_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Dispute not found")
    conn.execute(
        "UPDATE disputes SET status = ?, resolution_note = ?, resolved_at = ?, resolved_by = ? WHERE id = ?",
        (
            payload.status,
            payload.resolution_note,
            datetime.utcnow().isoformat(),
            admin["id"],
            dispute_id,
        ),
    )
    conn.commit()
    conn.close()
    return {"status": payload.status}




@app.get("/ledger/{transaction_id}")
def get_ledger(transaction_id: str, user=Depends(get_current_user)):
    conn = db()
    row = conn.execute(
        """
        SELECT transactions.*, inventory.name as item_name, inventory.market_low, inventory.market_high,
               buyers.name as buyer_name, sellers.name as seller_name
        FROM transactions
        JOIN inventory ON transactions.inventory_id = inventory.id
        JOIN users buyers ON transactions.buyer_id = buyers.id
        JOIN users sellers ON transactions.seller_id = sellers.id
        WHERE transactions.id = ?
        """,
        (transaction_id,),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Ledger not found")
    if user["id"] not in (row["buyer_id"], row["seller_id"]) and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")
    return {
        "id": row["id"],
        "buyer": row["buyer_name"],
        "seller": row["seller_name"],
        "item": row["item_name"],
        "quantity": row["quantity"],
        "unit_price": row["unit_price"],
        "payment_status": row["payment_status"],
        "razorpay_order_id": row["razorpay_order_id"],
        "razorpay_payment_id": row["razorpay_payment_id"],
        "stock_status": row["stock_status"],
        "expires_at": row["expires_at"],
        "market_low": row["market_low"],
        "market_high": row["market_high"],
        "created_at": row["created_at"],
        "ledger_hash": f"ledger_{row['id'].lower()}",
    }


@app.get("/ledger/{transaction_id}/invoice")
def get_ledger_invoice(transaction_id: str, user=Depends(get_current_user)):
    conn = db()
    row = conn.execute(
        """
        SELECT transactions.*, inventory.name as item_name, inventory.market_low, inventory.market_high,
               buyers.name as buyer_name, buyers.email as buyer_email,
               sellers.name as seller_name, sellers.email as seller_email
        FROM transactions
        JOIN inventory ON transactions.inventory_id = inventory.id
        JOIN users buyers ON transactions.buyer_id = buyers.id
        JOIN users sellers ON transactions.seller_id = sellers.id
        WHERE transactions.id = ?
        """,
        (transaction_id,),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Ledger not found")
    if user["id"] not in (row["buyer_id"], row["seller_id"]) and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 18)
    pdf.cell(0, 10, "TrustBridge Invoice", ln=True, align="C")
    pdf.ln(4)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 8, f"Invoice ID: {row['id']}", ln=True)
    pdf.cell(0, 8, f"Generated: {datetime.utcnow().isoformat()}", ln=True)
    pdf.ln(4)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Parties", ln=True)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 7, f"Buyer: {row['buyer_name']} <{row['buyer_email']}>", ln=True)
    pdf.cell(0, 7, f"Seller: {row['seller_name']} <{row['seller_email']}>", ln=True)
    pdf.ln(4)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, "Order Summary", ln=True)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 7, f"Item: {row['item_name']}", ln=True)
    pdf.cell(0, 7, f"Quantity: {row['quantity']}", ln=True)
    pdf.cell(0, 7, f"Unit Price: ₹{row['unit_price']:.2f}", ln=True)
    total = row['quantity'] * row['unit_price']
    pdf.cell(0, 7, f"Total: ₹{total:.2f}", ln=True)
    pdf.cell(0, 7, f"Payment Status: {row['payment_status']}", ln=True)
    pdf.cell(0, 7, f"Razorpay Order ID: {row['razorpay_order_id'] or '-'}", ln=True)
    pdf.cell(0, 7, f"Razorpay Payment ID: {row['razorpay_payment_id'] or '-'}", ln=True)
    pdf.ln(4)
    pdf.cell(0, 7, f"Market Range: ₹{row['market_low'] or '-'} - ₹{row['market_high'] or '-'}", ln=True)
    pdf.ln(4)
    pdf.set_font("Arial", "I", 9)
    pdf.cell(0, 6, "This bill is generated by TrustBridge shared ledger.", ln=True)

    data = pdf.output(dest="S").encode("latin1")
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=ledger_{transaction_id}.pdf"
    })


@app.get("/admin/users")
def admin_users(admin=Depends(require_admin)):
    conn = db()
    rows = conn.execute("SELECT id, email, name, role, created_at FROM users ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.get("/admin/transactions")
def admin_transactions(admin=Depends(require_admin)):
    conn = db()
    rows = conn.execute(
        """
        SELECT transactions.id, transactions.quantity, transactions.unit_price, transactions.payment_status,
               transactions.stock_status, transactions.created_at, inventory.name as item_name,
               buyers.name as buyer_name, sellers.name as seller_name
        FROM transactions
        JOIN inventory ON transactions.inventory_id = inventory.id
        JOIN users buyers ON transactions.buyer_id = buyers.id
        JOIN users sellers ON transactions.seller_id = sellers.id
        ORDER BY transactions.created_at DESC
        """
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
