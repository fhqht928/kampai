# ============================================
# Kampai 결제 시스템
# 토스페이먼츠 API 연동
# ============================================

import os
import requests
import base64
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

# 설정 (.env에서 로드)
TOSS_SECRET_KEY = os.environ.get("TOSS_SECRET_KEY", "test_sk_zXLkKEypNArWmo50nX3lmeaxYG5R")
TOSS_CLIENT_KEY = os.environ.get("TOSS_CLIENT_KEY", "test_ck_D5GePWvyJnrK0W0k6q8gLzN97Eoq")
TOSS_API_URL = "https://api.tosspayments.com/v1"

DB_PATH = Path(os.environ.get("DB_PATH", "D:/AI_Work/kampai.db"))

# 플랜별 가격 (VAT 별도)
PLAN_PRICES = {
    "basic": 4900,
    "pro": 19900,
    "business": 99000
}


def get_auth_header():
    """토스페이먼츠 인증 헤더 생성"""
    credentials = f"{TOSS_SECRET_KEY}:"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def create_payment_order(user_id: int, plan: str) -> dict:
    """결제 주문 생성"""
    if plan not in PLAN_PRICES:
        return {"success": False, "error": "유효하지 않은 플랜입니다"}
    
    amount = PLAN_PRICES[plan]
    order_id = f"KAMPAI_{user_id}_{plan}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 결제 기록 생성
    c.execute('''
        INSERT INTO payments (user_id, order_id, amount, plan, status)
        VALUES (?, ?, ?, ?, 'pending')
    ''', (user_id, order_id, amount, plan))
    
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "orderId": order_id,  # camelCase for frontend
        "order_id": order_id,
        "amount": amount,
        "plan": plan,
        "client_key": TOSS_CLIENT_KEY,
        "order_name": f"Kampai {plan.capitalize()} 플랜 (1개월)"
    }


def confirm_payment(payment_key: str, order_id: str, amount: int) -> dict:
    """결제 승인 (토스페이먼츠 API 호출)"""
    
    # 주문 정보 확인
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, plan, amount, status FROM payments WHERE order_id = ?", (order_id,))
    payment = c.fetchone()
    
    if not payment:
        conn.close()
        return {"success": False, "error": "주문을 찾을 수 없습니다"}
    
    if payment[3] != 'pending':
        conn.close()
        return {"success": False, "error": "이미 처리된 결제입니다"}
    
    # 금액 검증 (VAT 포함 금액과 비교)
    base_amount = payment[2]
    expected_with_vat = base_amount + int(base_amount * 0.1)
    if amount != expected_with_vat and amount != base_amount:
        conn.close()
        return {"success": False, "error": f"결제 금액이 일치하지 않습니다 (예상: {expected_with_vat}, 받은: {amount})"}
    
    user_id = payment[0]
    plan = payment[1]
    
    # 테스트 결제 처리 (test_payment_ 로 시작하면 테스트 모드)
    is_test = payment_key.startswith('test_payment_')
    
    if is_test:
        # 테스트 모드: API 호출 없이 바로 성공 처리
        c.execute('''
            UPDATE payments 
            SET status = 'approved', payment_key = ?, approved_at = CURRENT_TIMESTAMP 
            WHERE order_id = ?
        ''', (payment_key, order_id))
        
        # 사용자 플랜 업데이트
        c.execute("UPDATE users SET plan = ? WHERE id = ?", (plan, user_id))
        
        # 구독 기록 추가
        expires_at = datetime.now() + timedelta(days=30)
        c.execute('''
            INSERT OR REPLACE INTO subscriptions (user_id, plan, status, expires_at, payment_key, order_id)
            VALUES (?, ?, 'active', ?, ?, ?)
        ''', (user_id, plan, expires_at, payment_key, order_id))
        
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "message": f"{plan.capitalize()} 플랜 결제가 완료되었습니다! (테스트)",
            "plan": plan,
            "expires_at": expires_at.isoformat(),
            "testMode": True
        }
    
    # 실제 토스페이먼츠 결제 승인 API 호출
    try:
        response = requests.post(
            f"{TOSS_API_URL}/payments/confirm",
            headers={
                **get_auth_header(),
                "Content-Type": "application/json"
            },
            json={
                "paymentKey": payment_key,
                "orderId": order_id,
                "amount": amount
            },
            timeout=30
        )
        
        result = response.json()
        
        if response.status_code == 200:
            # 결제 성공
            c.execute('''
                UPDATE payments 
                SET status = 'approved', payment_key = ?, approved_at = CURRENT_TIMESTAMP 
                WHERE order_id = ?
            ''', (payment_key, order_id))
            
            # 사용자 플랜 업데이트
            c.execute("UPDATE users SET plan = ? WHERE id = ?", (plan, user_id))
            
            # 구독 기록 추가
            expires_at = datetime.now() + timedelta(days=30)
            c.execute('''
                INSERT INTO subscriptions (user_id, plan, status, expires_at, payment_key, order_id)
                VALUES (?, ?, 'active', ?, ?, ?)
            ''', (user_id, plan, expires_at, payment_key, order_id))
            
            conn.commit()
            conn.close()
            
            return {
                "success": True,
                "message": f"{plan.capitalize()} 플랜 결제가 완료되었습니다!",
                "plan": plan,
                "expires_at": expires_at.isoformat()
            }
        else:
            # 결제 실패
            c.execute("UPDATE payments SET status = 'failed' WHERE order_id = ?", (order_id,))
            conn.commit()
            conn.close()
            
            return {
                "success": False,
                "error": result.get("message", "결제에 실패했습니다"),
                "code": result.get("code")
            }
            
    except requests.exceptions.Timeout:
        conn.close()
        return {"success": False, "error": "결제 서버 응답 시간 초과"}
    except Exception as e:
        conn.close()
        return {"success": False, "error": f"결제 처리 중 오류: {str(e)}"}


def cancel_payment(payment_key: str, cancel_reason: str = "고객 요청") -> dict:
    """결제 취소"""
    try:
        response = requests.post(
            f"{TOSS_API_URL}/payments/{payment_key}/cancel",
            headers={
                **get_auth_header(),
                "Content-Type": "application/json"
            },
            json={"cancelReason": cancel_reason},
            timeout=30
        )
        
        result = response.json()
        
        if response.status_code == 200:
            # 결제 취소 성공 - DB 업데이트
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            c.execute('''
                UPDATE payments SET status = 'cancelled' WHERE payment_key = ?
            ''', (payment_key,))
            
            # 사용자 플랜 다운그레이드
            c.execute('''
                SELECT user_id FROM payments WHERE payment_key = ?
            ''', (payment_key,))
            result_row = c.fetchone()
            
            if result_row:
                c.execute("UPDATE users SET plan = 'free' WHERE id = ?", (result_row[0],))
                c.execute('''
                    UPDATE subscriptions SET status = 'cancelled' WHERE payment_key = ?
                ''', (payment_key,))
            
            conn.commit()
            conn.close()
            
            return {"success": True, "message": "결제가 취소되었습니다"}
        else:
            return {
                "success": False,
                "error": result.get("message", "결제 취소에 실패했습니다")
            }
            
    except Exception as e:
        return {"success": False, "error": f"결제 취소 중 오류: {str(e)}"}


def get_payment_history(user_id: int) -> list:
    """결제 내역 조회"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        SELECT order_id, amount, plan, status, created_at, approved_at
        FROM payments
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 20
    ''', (user_id,))
    
    payments = []
    for row in c.fetchall():
        payments.append({
            "order_id": row[0],
            "amount": row[1],
            "plan": row[2],
            "status": row[3],
            "created_at": row[4],
            "approved_at": row[5]
        })
    
    conn.close()
    return payments


# ============================================
# 웹훅 처리
# ============================================

def handle_webhook(payload: dict) -> dict:
    """토스페이먼츠 웹훅 처리"""
    event_type = payload.get("eventType")
    data = payload.get("data", {})
    
    if event_type == "PAYMENT_STATUS_CHANGED":
        payment_key = data.get("paymentKey")
        status = data.get("status")
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        if status == "DONE":
            c.execute("UPDATE payments SET status = 'approved' WHERE payment_key = ?", (payment_key,))
        elif status == "CANCELED":
            c.execute("UPDATE payments SET status = 'cancelled' WHERE payment_key = ?", (payment_key,))
        elif status == "EXPIRED":
            c.execute("UPDATE payments SET status = 'expired' WHERE payment_key = ?", (payment_key,))
        
        conn.commit()
        conn.close()
        
        return {"success": True, "message": f"Webhook processed: {event_type}"}
    
    return {"success": True, "message": "Webhook received"}
