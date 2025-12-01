# ============================================
# AI Studio - 고객 주문 자동 처리 시스템
# ComfyUI + 이미지 배치 처리 통합
# ============================================

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

# 내부 모듈
from comfyui_api import ComfyUIClient, generate_product_image, generate_thumbnail, generate_banner
from batch_image_processor import batch_process, PRESETS


class OrderProcessor:
    """고객 주문 자동 처리"""
    
    def __init__(self):
        self.comfy = ComfyUIClient()
        self.work_dir = Path("D:/AI_Work")
        self.work_dir.mkdir(exist_ok=True)
    
    def create_order_folder(self, order_id: str, customer_name: str) -> Path:
        """주문별 작업 폴더 생성"""
        today = datetime.now().strftime("%Y-%m")
        folder_name = f"{order_id}_{customer_name}"
        
        order_path = self.work_dir / today / folder_name
        
        # 하위 폴더 생성
        (order_path / "01_원본").mkdir(parents=True, exist_ok=True)
        (order_path / "02_생성").mkdir(parents=True, exist_ok=True)
        (order_path / "03_편집").mkdir(parents=True, exist_ok=True)
        (order_path / "04_납품").mkdir(parents=True, exist_ok=True)
        
        return order_path
    
    def process_product_image_order(
        self,
        order_id: str,
        customer_name: str,
        product_description: str,
        count: int = 5,
        style: str = "professional product photography"
    ) -> dict:
        """
        제품 이미지 주문 처리
        
        Returns:
            처리 결과 딕셔너리
        """
        print(f"\n{'='*50}")
        print(f"📦 제품 이미지 주문 처리: {order_id}")
        print(f"{'='*50}")
        
        # 작업 폴더 생성
        order_path = self.create_order_folder(order_id, customer_name)
        generated_dir = order_path / "02_생성"
        delivery_dir = order_path / "04_납품"
        
        generated_images = []
        
        # 이미지 생성
        print(f"\n🎨 {count}장 이미지 생성 중...")
        
        for i in range(count):
            print(f"\n  [{i+1}/{count}] 생성 중...")
            
            try:
                output_path = generated_dir / f"product_{i+1:02d}.png"
                
                images = generate_product_image(
                    product_description=product_description,
                    style=style,
                    output_path=str(output_path)
                )
                
                generated_images.extend(images)
                print(f"  ✅ 완료: {output_path.name}")
                
            except Exception as e:
                print(f"  ❌ 오류: {e}")
        
        # 납품용 최적화 (스마트스토어 규격)
        if generated_images:
            print(f"\n📐 납품용 최적화 중...")
            batch_process(
                str(generated_dir),
                str(delivery_dir),
                PRESETS["smartstore"]
            )
        
        return {
            "order_id": order_id,
            "customer": customer_name,
            "generated_count": len(generated_images),
            "order_path": str(order_path),
            "delivery_path": str(delivery_dir)
        }
    
    def process_thumbnail_order(
        self,
        order_id: str,
        customer_name: str,
        themes: list,
        size: tuple = (1280, 720)
    ) -> dict:
        """
        썸네일 주문 처리
        
        Args:
            themes: 썸네일 주제 리스트
        """
        print(f"\n{'='*50}")
        print(f"🎬 썸네일 주문 처리: {order_id}")
        print(f"{'='*50}")
        
        order_path = self.create_order_folder(order_id, customer_name)
        generated_dir = order_path / "02_생성"
        delivery_dir = order_path / "04_납품"
        
        generated_images = []
        
        for i, theme in enumerate(themes, 1):
            print(f"\n  [{i}/{len(themes)}] 생성 중: {theme[:30]}...")
            
            try:
                output_path = generated_dir / f"thumbnail_{i:02d}.png"
                
                images = generate_thumbnail(
                    title=theme,
                    output_path=str(output_path)
                )
                
                generated_images.extend(images)
                print(f"  ✅ 완료")
                
            except Exception as e:
                print(f"  ❌ 오류: {e}")
        
        # 납품용 최적화
        if generated_images:
            print(f"\n📐 유튜브 규격 최적화 중...")
            batch_process(
                str(generated_dir),
                str(delivery_dir),
                PRESETS["youtube"]
            )
        
        return {
            "order_id": order_id,
            "customer": customer_name,
            "generated_count": len(generated_images),
            "order_path": str(order_path),
            "delivery_path": str(delivery_dir)
        }
    
    def process_batch_editing(
        self,
        order_id: str,
        customer_name: str,
        input_images: list,
        preset: str = "smartstore"
    ) -> dict:
        """
        이미지 일괄 편집 주문 처리
        (고객이 원본 이미지를 제공한 경우)
        """
        print(f"\n{'='*50}")
        print(f"✏️ 이미지 편집 주문 처리: {order_id}")
        print(f"{'='*50}")
        
        order_path = self.create_order_folder(order_id, customer_name)
        original_dir = order_path / "01_원본"
        edited_dir = order_path / "03_편집"
        delivery_dir = order_path / "04_납품"
        
        # 원본 이미지 복사
        import shutil
        for img_path in input_images:
            shutil.copy(img_path, original_dir)
        
        # 배치 처리
        print(f"\n📐 {preset} 프리셋으로 편집 중...")
        batch_process(
            str(original_dir),
            str(delivery_dir),
            PRESETS.get(preset, PRESETS["smartstore"])
        )
        
        return {
            "order_id": order_id,
            "customer": customer_name,
            "processed_count": len(input_images),
            "order_path": str(order_path),
            "delivery_path": str(delivery_dir)
        }


# ============================================
# CLI 인터페이스
# ============================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="AI Studio 주문 처리 시스템")
    
    subparsers = parser.add_subparsers(dest="command", help="명령어")
    
    # 제품 이미지 명령
    product_parser = subparsers.add_parser("product", help="제품 이미지 생성")
    product_parser.add_argument("--order-id", required=True, help="주문 번호")
    product_parser.add_argument("--customer", required=True, help="고객명")
    product_parser.add_argument("--description", required=True, help="제품 설명")
    product_parser.add_argument("--count", type=int, default=5, help="생성 개수")
    product_parser.add_argument("--style", default="professional product photography")
    
    # 썸네일 명령
    thumb_parser = subparsers.add_parser("thumbnail", help="썸네일 생성")
    thumb_parser.add_argument("--order-id", required=True, help="주문 번호")
    thumb_parser.add_argument("--customer", required=True, help="고객명")
    thumb_parser.add_argument("--themes", nargs="+", required=True, help="썸네일 주제들")
    
    # 편집 명령
    edit_parser = subparsers.add_parser("edit", help="이미지 편집")
    edit_parser.add_argument("--order-id", required=True, help="주문 번호")
    edit_parser.add_argument("--customer", required=True, help="고객명")
    edit_parser.add_argument("--input", required=True, help="입력 이미지 폴더")
    edit_parser.add_argument("--preset", default="smartstore", 
                            choices=list(PRESETS.keys()), help="편집 프리셋")
    
    args = parser.parse_args()
    
    # ComfyUI 서버 확인
    processor = OrderProcessor()
    
    if args.command in ["product", "thumbnail"]:
        if not processor.comfy.is_server_running():
            print("❌ ComfyUI 서버가 실행 중이 아닙니다!")
            print("   run_comfyui.bat 을 먼저 실행해주세요.")
            return
    
    # 명령 실행
    if args.command == "product":
        result = processor.process_product_image_order(
            order_id=args.order_id,
            customer_name=args.customer,
            product_description=args.description,
            count=args.count,
            style=args.style
        )
        
    elif args.command == "thumbnail":
        result = processor.process_thumbnail_order(
            order_id=args.order_id,
            customer_name=args.customer,
            themes=args.themes
        )
        
    elif args.command == "edit":
        from pathlib import Path
        input_path = Path(args.input)
        
        if input_path.is_dir():
            input_images = list(input_path.glob("*.png")) + list(input_path.glob("*.jpg"))
        else:
            input_images = [input_path]
        
        result = processor.process_batch_editing(
            order_id=args.order_id,
            customer_name=args.customer,
            input_images=[str(p) for p in input_images],
            preset=args.preset
        )
    
    else:
        parser.print_help()
        return
    
    # 결과 출력
    print(f"\n{'='*50}")
    print("✅ 처리 완료!")
    print(f"{'='*50}")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
