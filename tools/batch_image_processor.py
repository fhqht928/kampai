# AI 이미지 배치 처리 자동화 스크립트
# 업스케일, 배경 제거, 포맷 변환 등

import os
import sys
from pathlib import Path
from PIL import Image
import argparse
from datetime import datetime

# ============================================
# 설정
# ============================================
SUPPORTED_FORMATS = ['.jpg', '.jpeg', '.png', '.webp', '.bmp']
OUTPUT_DIR = "output"

# ============================================
# 유틸리티 함수
# ============================================

def ensure_dir(directory):
    """디렉토리가 없으면 생성"""
    Path(directory).mkdir(parents=True, exist_ok=True)

def get_timestamp():
    """타임스탬프 생성"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def get_image_files(input_path):
    """입력 경로에서 이미지 파일 목록 반환"""
    input_path = Path(input_path)
    
    if input_path.is_file():
        if input_path.suffix.lower() in SUPPORTED_FORMATS:
            return [input_path]
        else:
            print(f"지원하지 않는 형식: {input_path.suffix}")
            return []
    
    elif input_path.is_dir():
        files = []
        for fmt in SUPPORTED_FORMATS:
            files.extend(input_path.glob(f"*{fmt}"))
            files.extend(input_path.glob(f"*{fmt.upper()}"))
        return sorted(files)
    
    else:
        print(f"경로를 찾을 수 없음: {input_path}")
        return []

# ============================================
# 이미지 처리 함수
# ============================================

def resize_image(image, width=None, height=None, scale=None):
    """이미지 리사이즈"""
    orig_width, orig_height = image.size
    
    if scale:
        new_width = int(orig_width * scale)
        new_height = int(orig_height * scale)
    elif width and height:
        new_width, new_height = width, height
    elif width:
        ratio = width / orig_width
        new_width = width
        new_height = int(orig_height * ratio)
    elif height:
        ratio = height / orig_height
        new_height = height
        new_width = int(orig_width * ratio)
    else:
        return image
    
    return image.resize((new_width, new_height), Image.LANCZOS)

def convert_format(image, output_format):
    """이미지 포맷 변환을 위한 준비"""
    if output_format.lower() in ['jpg', 'jpeg']:
        # JPEG는 알파 채널을 지원하지 않으므로 RGB로 변환
        if image.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
            return background
        elif image.mode != 'RGB':
            return image.convert('RGB')
    return image

def add_watermark(image, text="AI Studio", opacity=128):
    """워터마크 추가 (선택사항)"""
    from PIL import ImageDraw, ImageFont
    
    # 복사본 생성
    watermarked = image.copy()
    
    # RGBA로 변환
    if watermarked.mode != 'RGBA':
        watermarked = watermarked.convert('RGBA')
    
    # 텍스트 레이어 생성
    txt_layer = Image.new('RGBA', watermarked.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    # 폰트 설정 (기본 폰트 사용)
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except:
        font = ImageFont.load_default()
    
    # 텍스트 위치 (우하단)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    x = watermarked.width - text_width - 20
    y = watermarked.height - text_height - 20
    
    # 텍스트 그리기
    draw.text((x, y), text, font=font, fill=(255, 255, 255, opacity))
    
    # 합성
    watermarked = Image.alpha_composite(watermarked, txt_layer)
    
    return watermarked

def optimize_for_web(image, max_size=1920, quality=85):
    """웹용 최적화 (크기 제한 + 압축)"""
    # 최대 크기 제한
    if image.width > max_size or image.height > max_size:
        if image.width > image.height:
            image = resize_image(image, width=max_size)
        else:
            image = resize_image(image, height=max_size)
    
    return image

def create_thumbnail(image, size=(300, 300)):
    """썸네일 생성"""
    thumb = image.copy()
    thumb.thumbnail(size, Image.LANCZOS)
    return thumb

# ============================================
# 배치 처리 함수
# ============================================

def batch_process(input_path, output_path=None, operations=None):
    """
    배치 이미지 처리
    
    operations: list of dicts, 예시:
    [
        {"type": "resize", "width": 1920},
        {"type": "format", "format": "webp"},
        {"type": "optimize", "quality": 85}
    ]
    """
    if operations is None:
        operations = []
    
    # 이미지 파일 수집
    image_files = get_image_files(input_path)
    
    if not image_files:
        print("처리할 이미지가 없습니다.")
        return
    
    # 출력 디렉토리 설정
    if output_path is None:
        output_path = Path(input_path).parent / f"{OUTPUT_DIR}_{get_timestamp()}"
    else:
        output_path = Path(output_path)
    
    ensure_dir(output_path)
    
    print(f"\n{'='*50}")
    print(f"배치 처리 시작")
    print(f"입력: {input_path}")
    print(f"출력: {output_path}")
    print(f"파일 수: {len(image_files)}")
    print(f"{'='*50}\n")
    
    # 각 파일 처리
    processed = 0
    failed = 0
    output_format = 'png'  # 기본 출력 포맷
    
    for i, file_path in enumerate(image_files, 1):
        try:
            print(f"[{i}/{len(image_files)}] 처리 중: {file_path.name}")
            
            # 이미지 로드
            image = Image.open(file_path)
            
            # 작업 수행
            for op in operations:
                op_type = op.get("type")
                
                if op_type == "resize":
                    image = resize_image(
                        image, 
                        width=op.get("width"),
                        height=op.get("height"),
                        scale=op.get("scale")
                    )
                
                elif op_type == "format":
                    output_format = op.get("format", "png")
                    image = convert_format(image, output_format)
                
                elif op_type == "optimize":
                    image = optimize_for_web(
                        image,
                        max_size=op.get("max_size", 1920),
                        quality=op.get("quality", 85)
                    )
                
                elif op_type == "thumbnail":
                    size = op.get("size", (300, 300))
                    image = create_thumbnail(image, size)
                
                elif op_type == "watermark":
                    image = add_watermark(
                        image,
                        text=op.get("text", "AI Studio"),
                        opacity=op.get("opacity", 128)
                    )
            
            # 저장
            output_filename = file_path.stem + f".{output_format}"
            output_file = output_path / output_filename
            
            save_kwargs = {}
            if output_format.lower() in ['jpg', 'jpeg']:
                save_kwargs['quality'] = 90
                save_kwargs['optimize'] = True
            elif output_format.lower() == 'webp':
                save_kwargs['quality'] = 85
            elif output_format.lower() == 'png':
                save_kwargs['optimize'] = True
            
            image.save(output_file, **save_kwargs)
            processed += 1
            print(f"    ✓ 저장 완료: {output_filename}")
            
        except Exception as e:
            failed += 1
            print(f"    ✗ 오류: {str(e)}")
    
    # 결과 출력
    print(f"\n{'='*50}")
    print(f"처리 완료!")
    print(f"성공: {processed}개 / 실패: {failed}개")
    print(f"출력 경로: {output_path}")
    print(f"{'='*50}\n")

# ============================================
# 프리셋
# ============================================

PRESETS = {
    "smartstore": [
        {"type": "resize", "width": 1000},
        {"type": "format", "format": "jpg"},
        {"type": "optimize", "quality": 90}
    ],
    "thumbnail": [
        {"type": "thumbnail", "size": (300, 300)},
        {"type": "format", "format": "jpg"}
    ],
    "youtube": [
        {"type": "resize", "width": 1280, "height": 720},
        {"type": "format", "format": "png"}
    ],
    "instagram": [
        {"type": "resize", "width": 1080},
        {"type": "format", "format": "jpg"},
        {"type": "optimize", "quality": 95}
    ],
    "webp": [
        {"type": "optimize", "max_size": 1920},
        {"type": "format", "format": "webp"}
    ],
    "4k": [
        {"type": "resize", "width": 3840},
        {"type": "format", "format": "png"}
    ]
}

# ============================================
# CLI
# ============================================

def main():
    parser = argparse.ArgumentParser(
        description="AI Studio 이미지 배치 처리 도구",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 스마트스토어용 최적화
  python batch_image_processor.py ./images --preset smartstore
  
  # 유튜브 썸네일 크기로 리사이즈
  python batch_image_processor.py ./images --preset youtube
  
  # WebP로 변환
  python batch_image_processor.py ./images --preset webp
  
  # 커스텀 리사이즈
  python batch_image_processor.py ./images --width 800 --format jpg
  
  # 출력 폴더 지정
  python batch_image_processor.py ./images --preset smartstore -o ./output
        """
    )
    
    parser.add_argument("input", help="입력 이미지 파일 또는 폴더 경로")
    parser.add_argument("-o", "--output", help="출력 폴더 경로")
    parser.add_argument("-p", "--preset", choices=list(PRESETS.keys()), 
                        help="사전 정의된 프리셋 사용")
    parser.add_argument("-w", "--width", type=int, help="리사이즈 너비")
    parser.add_argument("-H", "--height", type=int, help="리사이즈 높이")
    parser.add_argument("-s", "--scale", type=float, help="스케일 배율 (예: 0.5, 2.0)")
    parser.add_argument("-f", "--format", choices=['jpg', 'png', 'webp'], 
                        help="출력 포맷")
    parser.add_argument("--watermark", help="워터마크 텍스트")
    
    args = parser.parse_args()
    
    # 작업 목록 구성
    operations = []
    
    if args.preset:
        operations = PRESETS[args.preset].copy()
    else:
        if args.width or args.height or args.scale:
            operations.append({
                "type": "resize",
                "width": args.width,
                "height": args.height,
                "scale": args.scale
            })
        
        if args.format:
            operations.append({"type": "format", "format": args.format})
        
        if args.watermark:
            operations.append({"type": "watermark", "text": args.watermark})
    
    if not operations:
        print("작업이 지정되지 않았습니다. --preset 또는 개별 옵션을 사용하세요.")
        parser.print_help()
        return
    
    # 배치 처리 실행
    batch_process(args.input, args.output, operations)

if __name__ == "__main__":
    main()
