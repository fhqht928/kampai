# ============================================
# Kampai 결제 시스템
# 토스페이먼츠 API 연동
# PostgreSQL (프로덕션) / SQLite (개발) 지원
# ============================================

import os
import requests
import base64
import json
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

# auth.py에서 DB 연결 함수 import
from auth import get_db_connection, get_placeholder, IS_POSTGRES

# 설정 (.env에서 로드)
TOSS_SECRET_KEY = os.environ.get("TOSS_SECRET_KEY", "test_sk_zXLkKEypNArWmo50nX3lmeaxYG5R")
TOSS_CLIENT_KEY = os.environ.get("TOSS_CLIENT_KEY", "test_ck_D5GePWvyJnrK0W0k6q8gLzN97Eoq")
TOSS_API_URL = "https://api.tosspayments.com/v1"

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
    
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    # 결제 기록 생성
    c.execute(f'''
        INSERT INTO payments (user_id, order_id, amount, plan, status)
        VALUES ({ph}, {ph}, {ph}, {ph}, 'pending')
    ''', (user_id, order_id, amount, plan))
    
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "orderId": order_id,
        "order_id": order_id,
        "amount": amount,
        "plan": plan,
        "client_key": TOSS_CLIENT_KEY,
        "order_name": f"Kampai {plan.capitalize()} 플랜 (1개월)"
    }


def confirm_payment(payment_key: str, order_id: str, amount: int) -> dict:
    """결제 승인 (토스페이먼츠 API 호출)"""
    
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    # 주문 정보 확인
    c.execute(f"SELECT user_id, plan, amount, status FROM payments WHERE order_id = {ph}", (order_id,))
    payment = c.fetchone()
    
    if not payment:
        conn.close()
        return {"success": False, "error": "주문을 찾을 수 없습니다"}
    
    # Row에서 값 추출
    if IS_POSTGRES:
        user_id, plan, base_amount, status = payment
    else:
        user_id = payment['user_id']
        plan = payment['plan']
        base_amount = payment['amount']
        status = payment['status']
    
    if status != 'pending':
        conn.close()
        return {"success": False, "error": "이미 처리된 결제입니다"}
    
    # 금액 검증 (VAT 포함 금액과 비교)
    expected_with_vat = base_amount + int(base_amount * 0.1)
    if amount != expected_with_vat and amount != base_amount:
        conn.close()
        return {"success": False, "error": f"결제 금액이 일치하지 않습니다 (예상: {expected_with_vat}, 받은: {amount})"}
    
    # 테스트 결제 처리
    is_test = payment_key.startswith('test_payment_')
    
    if is_test:
        # 테스트 모드: API 호출 없이 바로 성공 처리
        c.execute(f'''
            UPDATE payments 
            SET status = 'approved', payment_key = {ph}, approved_at = CURRENT_TIMESTAMP 
            WHERE order_id = {ph}
        ''', (payment_key, order_id))
        
        # 사용자 플랜 업데이트
        c.execute(f"UPDATE users SET plan = {ph} WHERE id = {ph}", (plan, user_id))
        
        # 구독 기록 추가
        expires_at = datetime.now() + timedelta(days=30)
        
        if IS_POSTGRES:
            c.execute(f'''
                INSERT INTO subscriptions (user_id, plan, status, expires_at, payment_key, order_id)
                VALUES ({ph}, {ph}, 'active', {ph}, {ph}, {ph})
                ON CONFLICT (user_id, plan) DO UPDATE SET
                    status = 'active', expires_at = {ph}, payment_key = {ph}, order_id = {ph}
            ''', (user_id, plan, expires_at, payment_key, order_id, expires_at, payment_key, order_id))
        else:
            c.execute(f'''
                INSERT OR REPLACE INTO subscriptions (user_id, plan, status, expires_at, payment_key, order_id)
                VALUES ({ph}, {ph}, 'active', {ph}, {ph}, {ph})
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
            c.execute(f'''
                UPDATE payments 
                SET status = 'approved', payment_key = {ph}, approved_at = CURRENT_TIMESTAMP 
                WHERE order_id = {ph}
            ''', (payment_key, order_id))
            
            # 사용자 플랜 업데이트
            c.execute(f"UPDATE users SET plan = {ph} WHERE id = {ph}", (plan, user_id))
            
            # 구독 기록 추가
            expires_at = datetime.now() + timedelta(days=30)
            c.execute(f'''
                INSERT INTO subscriptions (user_id, plan, status, expires_at, payment_key, order_id)
                VALUES ({ph}, {ph}, 'active', {ph}, {ph}, {ph})
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
            c.execute(f"UPDATE payments SET status = 'failed' WHERE order_id = {ph}", (order_id,))
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
            conn = get_db_connection()
            c = conn.cursor()
            ph = get_placeholder()
            
            c.execute(f'''
                UPDATE payments SET status = 'cancelled' WHERE payment_key = {ph}
            ''', (payment_key,))
            
            # 사용자 플랜 다운그레이드
            c.execute(f'''
                SELECT user_id FROM payments WHERE payment_key = {ph}
            ''', (payment_key,))
            result_row = c.fetchone()
            
            if result_row:
                user_id = result_row[0] if IS_POSTGRES else result_row['user_id']
                c.execute(f"UPDATE users SET plan = 'free' WHERE id = {ph}", (user_id,))
                c.execute(f'''
                    UPDATE subscriptions SET status = 'cancelled' WHERE payment_key = {ph}
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
    conn = get_db_connection()
    c = conn.cursor()
    ph = get_placeholder()
    
    c.execute(f'''
        SELECT order_id, amount, plan, status, created_at, approved_at
        FROM payments
        WHERE user_id = {ph}
        ORDER BY created_at DESC
        LIMIT 20
    ''', (user_id,))
    
    payments = []
    for row in c.fetchall():
        if IS_POSTGRES:
            payments.append({
                "order_id": row[0],
                "amount": row[1],
                "plan": row[2],
                "status": row[3],
                "created_at": str(row[4]) if row[4] else None,
                "approved_at": str(row[5]) if row[5] else None
            })
        else:
            payments.append({
                "order_id": row['order_id'],
                "amount": row['amount'],
                "plan": row['plan'],
                "status": row['status'],
                "created_at": row['created_at'],
                "approved_at": row['approved_at']
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
        
        conn = get_db_connection()
        c = conn.cursor()
        ph = get_placeholder()
        
        if status == "DONE":
            c.execute(f"UPDATE payments SET status = 'approved' WHERE payment_key = {ph}", (payment_key,))
        elif status == "CANCELED":
            c.execute(f"UPDATE payments SET status = 'cancelled' WHERE payment_key = {ph}", (payment_key,))
        elif status == "EXPIRED":
            c.execute(f"UPDATE payments SET status = 'expired' WHERE payment_key = {ph}", (payment_key,))
        
        conn.commit()
        conn.close()
        
        return {"success": True, "message": f"Webhook processed: {event_type}"}
    
    return {"success": True, "message": "Webhook received"}
