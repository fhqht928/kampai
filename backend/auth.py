# ============================================
# Kampai ?¸ì¦ & êµ¬ë… ?œìŠ¤??
# ?Œì›ê°€?? ë¡œê·¸?? JWT ?¸ì¦, êµ¬ë… ê´€ë¦?
# ============================================

import os
import sqlite3
import hashlib
import secrets
import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify
from pathlib import Path
from dotenv import load_dotenv

# .env ?Œì¼ ë¡œë“œ
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

# ?°ì´?°ë² ?´ìŠ¤ ?¤ì •
# PostgreSQL URL???ˆìœ¼ë©?PostgreSQL ?¬ìš©, ?†ìœ¼ë©?SQLite ?¬ìš©
DATABASE_URL = os.environ.get("DATABASE_URL")
USE_POSTGRES = DATABASE_URL is not None

if USE_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    print("?˜ PostgreSQL ?¬ìš©")
else:
    # ?´ë¼?°ë“œ ?˜ê²½?ì„œ???ë? ê²½ë¡œ ?¬ìš©
    _default_db = Path(__file__).parent / "kampai.db"
    DB_PATH = Path(os.environ.get("DB_PATH", str(_default_db)))
    print(f"?“ SQLite ?¬ìš©: {DB_PATH}")

# JWT_SECRET: .env???¤ì •??ê°??¬ìš©, ?†ìœ¼ë©??œë¤ ?ì„± (?œë²„ ?¬ì‹œ?????¸ì…˜ ë¬´íš¨??
JWT_SECRET = os.environ.get("JWT_SECRET") or secrets.token_hex(32)
JWT_EXPIRY_HOURS = 24 * 7  # 7??

# ?Œëœ ?•ì˜ (4?¨ê³„ + ëª¨ë¸ ì°¨ë“±)
PLANS = {
    "free": {
        "name": "Free",
        "price": 0,
        "daily_limit": 3,
        "model": "flux-schnell",
        "model_name": "FLUX.1 Schnell",
        "resolution": "1024x1024",
        "watermark": True,
        "commercial": False,
        "speed": "2-4ì´?,
        "cost_per_image": 0.003
    },
    "basic": {
        "name": "Basic",
        "price": 4900,
        "daily_limit": 30,
        "model": "flux-schnell",
        "model_name": "FLUX.1 Schnell",
        "resolution": "1024x1024",
        "watermark": False,
        "commercial": True,
        "speed": "2-4ì´?,
        "cost_per_image": 0.003
    },
    "pro": {
        "name": "Pro",
        "price": 19900,
        "daily_limit": 100,
        "model": "qwen-image",
        "model_name": "Qwen-Image",
        "available_models": ["qwen-image", "flux-1.1-pro-ultra"],
        "resolution": "2048x2048",
        "watermark": False,
        "commercial": True,
        "speed": "3-8ì´?,
        "cost_per_image": 0.025,
        "features": ["ëª¨ë¸ ? íƒ", "?ìŠ¤???Œë”ë§?, "4K ì§€??]
    },
    "business": {
        "name": "Business",
        "price": 99000,
        "daily_limit": 500,
        "model": "qwen-image",
        "model_name": "Qwen-Image / FLUX Ultra",
        "available_models": ["qwen-image", "flux-1.1-pro-ultra"],
        "resolution": "2048x2048",
        "watermark": False,
        "commercial": True,
        "speed": "3-8ì´?,
        "cost_per_image": 0.025,
        "team_members": 5,
        "api_access": True
    }
}


def get_db_connection():
    """?°ì´?°ë² ?´ìŠ¤ ?°ê²° ë°˜í™˜"""
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        return conn


def db_placeholder():
    """SQL placeholder ë°˜í™˜ (PostgreSQL: %s, SQLite: ?)"""
    return "%s" if USE_POSTGRES else "?"


def init_db():
    """?°ì´?°ë² ?´ìŠ¤ ì´ˆê¸°??""
    conn = get_db_connection()
    c = conn.cursor()
    
    if USE_POSTGRES:
        # PostgreSQL???Œì´ë¸??ì„±
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT,
                plan TEXT DEFAULT 'free',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                plan TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                payment_key TEXT,
                order_id TEXT
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS usage (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                date DATE DEFAULT CURRENT_DATE,
                generation_count INTEGER DEFAULT 0,
                UNIQUE(user_id, date)
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS generations (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                prompt TEXT,
                style TEXT,
                image_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                order_id TEXT UNIQUE NOT NULL,
                payment_key TEXT,
                amount INTEGER NOT NULL,
                plan TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP
            )
        ''')
    else:
        # SQLite???Œì´ë¸??ì„± (ê¸°ì¡´ ì½”ë“œ)
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT,
                plan TEXT DEFAULT 'free',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                payment_key TEXT,
                order_id TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date DATE DEFAULT (DATE('now')),
                generation_count INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, date)
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                prompt TEXT,
                style TEXT,
                image_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                order_id TEXT UNIQUE NOT NULL,
                payment_key TEXT,
                amount INTEGER NOT NULL,
                plan TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
    
    conn.commit()
    conn.close()
    print("??Database initialized")


def hash_password(password: str) -> str:
    """ë¹„ë?ë²ˆí˜¸ ?´ì‹±"""
    salt = "kampai_salt_2025"  # ?„ë¡œ?•ì…˜?ì„œ??ê°œë³„ salt ?¬ìš©
    return hashlib.sha256(f"{password}{salt}".encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """ë¹„ë?ë²ˆí˜¸ ê²€ì¦?""
    return hash_password(password) == password_hash


def create_token(user_id: int, email: str) -> str:
    """JWT ? í° ?ì„±"""
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def verify_token(token: str) -> dict:
    """JWT ? í° ê²€ì¦?""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def token_required(f):
    """?¸ì¦ ?„ìˆ˜ ?°ì½”?ˆì´??""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({"success": False, "error": "? í°???„ìš”?©ë‹ˆ??}), 401
        
        payload = verify_token(token)
        if not payload:
            return jsonify({"success": False, "error": "? íš¨?˜ì? ?Šì? ? í°?…ë‹ˆ??}), 401
        
        # ?¬ìš©???•ë³´ ì¡°íšŒ
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id, email, plan, is_active FROM users WHERE id = ?", (payload['user_id'],))
        user = c.fetchone()
        conn.close()
        
        if not user or not user[3]:
            return jsonify({"success": False, "error": "ë¹„í™œ?±í™”??ê³„ì •?…ë‹ˆ??}), 401
        
        request.user = {
            "id": user[0],
            "email": user[1],
            "plan": user[2]
        }
        
        return f(*args, **kwargs)
    return decorated


def optional_token(f):
    """? íƒ???¸ì¦ ?°ì½”?ˆì´??(ë¹„ë¡œê·¸ì¸???ˆìš©)"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        request.user = None
        
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        if token:
            payload = verify_token(token)
            if payload:
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("SELECT id, email, plan FROM users WHERE id = ?", (payload['user_id'],))
                user = c.fetchone()
                conn.close()
                
                if user:
                    request.user = {
                        "id": user[0],
                        "email": user[1],
                        "plan": user[2]
                    }
        
        return f(*args, **kwargs)
    return decorated


# ============================================
# ?Œì›ê°€??/ ë¡œê·¸??
# ============================================

def register_user(email: str, password: str, name: str = None) -> dict:
    """?Œì›ê°€??""
    if len(password) < 8:
        return {"success": False, "error": "ë¹„ë?ë²ˆí˜¸??8???´ìƒ?´ì–´???©ë‹ˆ??}
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # ?´ë©”??ì¤‘ë³µ ?•ì¸
    c.execute("SELECT id FROM users WHERE email = ?", (email,))
    if c.fetchone():
        conn.close()
        return {"success": False, "error": "?´ë? ê°€?…ëœ ?´ë©”?¼ì…?ˆë‹¤"}
    
    # ?¬ìš©???ì„±
    password_hash = hash_password(password)
    c.execute(
        "INSERT INTO users (email, password_hash, name, plan) VALUES (?, ?, ?, 'free')",
        (email, password_hash, name)
    )
    user_id = c.lastrowid
    
    # ?¤ëŠ˜ ?¬ìš©??ì´ˆê¸°??
    c.execute(
        "INSERT OR IGNORE INTO usage (user_id, date, generation_count) VALUES (?, DATE('now'), 0)",
        (user_id,)
    )
    
    conn.commit()
    conn.close()
    
    # ? í° ë°œê¸‰
    token = create_token(user_id, email)
    
    return {
        "success": True,
        "message": "?Œì›ê°€?…ì´ ?„ë£Œ?˜ì—ˆ?µë‹ˆ??,
        "user": {
            "id": user_id,
            "email": email,
            "name": name,
            "plan": "free"
        },
        "token": token
    }


def login_user(email: str, password: str) -> dict:
    """ë¡œê·¸??""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute("SELECT id, email, password_hash, name, plan, is_active FROM users WHERE email = ?", (email,))
    user = c.fetchone()
    
    if not user:
        conn.close()
        return {"success": False, "error": "?´ë©”???ëŠ” ë¹„ë?ë²ˆí˜¸ê°€ ?¬ë°”ë¥´ì? ?ŠìŠµ?ˆë‹¤"}
    
    if not user[5]:
        conn.close()
        return {"success": False, "error": "ë¹„í™œ?±í™”??ê³„ì •?…ë‹ˆ??}
    
    if not verify_password(password, user[2]):
        conn.close()
        return {"success": False, "error": "?´ë©”???ëŠ” ë¹„ë?ë²ˆí˜¸ê°€ ?¬ë°”ë¥´ì? ?ŠìŠµ?ˆë‹¤"}
    
    # ë§ˆì?ë§?ë¡œê·¸???…ë°?´íŠ¸
    c.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user[0],))
    conn.commit()
    conn.close()
    
    # ? í° ë°œê¸‰
    token = create_token(user[0], user[1])
    
    return {
        "success": True,
        "message": "ë¡œê·¸???±ê³µ",
        "user": {
            "id": user[0],
            "email": user[1],
            "name": user[3],
            "plan": user[4]
        },
        "token": token
    }


# ============================================
# ?¬ìš©??ê´€ë¦?
# ============================================

def get_user_usage(user_id: int) -> dict:
    """?¬ìš©???¬ìš©??ì¡°íšŒ"""
    conn = get_db_connection()
    c = conn.cursor()
    
    # ?¬ìš©???Œëœ ì¡°íšŒ
    c.execute("SELECT plan FROM users WHERE id = ?", (user_id,))
    result = c.fetchone()
    if not result:
        conn.close()
        return None
    
    plan = result[0]
    plan_info = PLANS.get(plan, PLANS['free'])
    
    # ?¤ëŠ˜ ?¬ìš©??ì¡°íšŒ
    c.execute(
        "SELECT generation_count FROM usage WHERE user_id = ? AND date = DATE('now')",
        (user_id,)
    )
    result = c.fetchone()
    today_count = result[0] if result else 0
    
    # ì´??ì„± ??ì¡°íšŒ
    c.execute("SELECT COUNT(*) FROM generations WHERE user_id = ?", (user_id,))
    total_count = c.fetchone()[0]
    
    conn.close()
    
    daily_limit = plan_info['daily_limit']
    remaining = daily_limit - today_count if daily_limit > 0 else -1
    
    return {
        "plan": plan,
        "plan_info": plan_info,
        "today_count": today_count,
        "daily_limit": daily_limit,
        "remaining": remaining,
        "total_generated": total_count,
        "can_generate": daily_limit < 0 or today_count < daily_limit
    }


def check_can_generate(user_id: int) -> dict:
    """?ì„± ê°€???¬ë? ?•ì¸"""
    usage = get_user_usage(user_id)
    if not usage:
        return {"can_generate": False, "error": "?¬ìš©?ë? ì°¾ì„ ???†ìŠµ?ˆë‹¤"}
    
    if not usage['can_generate']:
        return {
            "can_generate": False,
            "error": f"?¤ëŠ˜??ë¬´ë£Œ ?ì„± ?Ÿìˆ˜({usage['daily_limit']}??ë¥?ëª¨ë‘ ?¬ìš©?ˆìŠµ?ˆë‹¤. Proë¡??…ê·¸?ˆì´?œí•˜?¸ìš”!",
            "usage": usage
        }
    
    return {"can_generate": True, "usage": usage}


def increment_usage(user_id: int, action: str = 'generate', prompt: str = None, style: str = None, image_path: str = None):
    """?¬ìš©??ì¦ê?"""
    conn = get_db_connection()
    c = conn.cursor()
    
    # ?¤ëŠ˜ ?¬ìš©??ì¦ê? (?†ìœ¼ë©??ì„±)
    c.execute('''
        INSERT INTO usage (user_id, date, generation_count) 
        VALUES (?, DATE('now'), 1)
        ON CONFLICT(user_id, date) 
        DO UPDATE SET generation_count = generation_count + 1
    ''', (user_id,))
    
    # ?ì„± ê¸°ë¡ ?€??
    if prompt or action:
        c.execute(
            "INSERT INTO generations (user_id, prompt, style, image_path) VALUES (?, ?, ?, ?)",
            (user_id, prompt or f'[{action}]', style, image_path)
        )
    
    conn.commit()
    conn.close()


# ============================================
# êµ¬ë… ê´€ë¦?
# ============================================

def update_user_plan(user_id: int, plan: str, payment_key: str = None, order_id: str = None):
    """?¬ìš©???Œëœ ?…ë°?´íŠ¸"""
    if plan not in PLANS:
        return {"success": False, "error": "? íš¨?˜ì? ?Šì? ?Œëœ?…ë‹ˆ??}
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # ?¬ìš©???Œëœ ?…ë°?´íŠ¸
    c.execute("UPDATE users SET plan = ? WHERE id = ?", (plan, user_id))
    
    # êµ¬ë… ê¸°ë¡ ì¶”ê?
    expires_at = datetime.now() + timedelta(days=30)  # 30??êµ¬ë…
    c.execute('''
        INSERT INTO subscriptions (user_id, plan, status, expires_at, payment_key, order_id)
        VALUES (?, ?, 'active', ?, ?, ?)
    ''', (user_id, plan, expires_at, payment_key, order_id))
    
    conn.commit()
    conn.close()
    
    return {"success": True, "message": f"{PLANS[plan]['name']} ?Œëœ?¼ë¡œ ?…ê·¸?ˆì´?œë˜?ˆìŠµ?ˆë‹¤"}


def get_subscription_status(user_id: int) -> dict:
    """êµ¬ë… ?íƒœ ì¡°íšŒ"""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('''
        SELECT plan, status, started_at, expires_at 
        FROM subscriptions 
        WHERE user_id = ? AND status = 'active'
        ORDER BY started_at DESC LIMIT 1
    ''', (user_id,))
    
    sub = c.fetchone()
    conn.close()
    
    if not sub:
        return {"active": False, "plan": "free"}
    
    # ë§Œë£Œ ?•ì¸
    expires_at = datetime.fromisoformat(sub[3]) if sub[3] else None
    is_expired = expires_at and datetime.now() > expires_at
    
    return {
        "active": not is_expired,
        "plan": sub[0],
        "status": sub[1],
        "started_at": sub[2],
        "expires_at": sub[3],
        "is_expired": is_expired
    }


# ì´ˆê¸°??
init_db()
