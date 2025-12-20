import json
import os
import re
from pathlib import Path

# ==========================================
# 0. 설정: 삭제할 목차 제목 (블랙리스트)
# ==========================================
EXCLUDED_HEADINGS = {
    "개요", "배경", "챔피언 관계", "대사", "영원석", 
    "시리즈 1", "시리즈 2", "역사", "이전 시즌(2012 ~ 2024)", 
    "전략적 팀 전투", "레전드 오브 룬테라", "우르프 모드", 
    "와일드 리프트", "스킨", "기타", "구 설정"
}

# ==========================================
# 1. 텍스트 정제 함수 (Utils)
# ==========================================
def clean_text_content(text):
    if not text: return ""

    # 1. 태그 제거
    text = re.sub(r'\[.*?\]', '', text)

    # 2. 목차 번호 제거
    text = re.sub(r'(^|\s)\d+(\.\d+)+\.?\s+', ' ', text)
    text = re.sub(r'(^|\s)\d+\.\s+', ' ', text)

    # 3. 공백 정규화
    text = re.sub(r'\s+', ' ', text).strip()

    # 4. 참조/참고 관련 문장 제거
    text = _remove_reference_sentences(text)

    # 5. 중복 문장 제거
    text = _remove_duplicate_sentences(text)

    # 6. 말꼬리 반복 제거
    text = _remove_tail_repetitions(text)

    return text

def _remove_reference_sentences(text):
    """특정 키워드(참조, 참고하십시오 등)가 포함된 '문장'만 제거"""
    sentences = re.split(r'(?<=[.?!])\s+', text)
    valid_sentences = []

    for s in sentences:
        s_stripped = s.strip()
        if not s_stripped: continue

        if "참조" in s_stripped: continue
        if "문서를 참고하십시오" in s_stripped: continue
        if re.search(r'자세한 내용은.*?참고하십시오', s_stripped): continue

        valid_sentences.append(s_stripped)

    return ' '.join(valid_sentences)

def _remove_duplicate_sentences(text):
    sentences = re.split(r'(?<=[.?!])\s+', text)
    unique_sentences = []
    seen = set()

    for sentence in sentences:
        s = sentence.strip()
        if not s or (len(s) < 5 and s[-1] not in ['.', '?', '!']): 
            continue
        
        if s not in seen:
            unique_sentences.append(s)
            seen.add(s)
            
    return ' '.join(unique_sentences)

def _remove_tail_repetitions(text):
    while True:
        match = re.search(r'(\s\S.{1,20})(?:\1)+$', text)
        if match:
            text = text[:match.start()].strip()
        else:
            break
    return text

def clean_heading(heading):
    if not heading: return ""
    cleaned = re.sub(r'\[.*?\]', '', heading)
    cleaned = re.sub(r'^\d+(\.\d+)*\.?\s*', '', cleaned)
    return cleaned.strip()

# ==========================================
# 2. 파일 처리 함수 (핵심 로직)
# ==========================================
def process_json_file(input_path, output_path):
    try:
        file_name = Path(input_path).name
        is_general_file = file_name.startswith("리그-오브-레전드")

        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        new_data = data.copy()
        processed_sections = []
        blocked_prefixes = set()

        if "sections" in data:
            for section in data["sections"]:
                original_heading = section.get("heading", "")
                original_text = section.get("text", "")

                # 번호 추출
                match_num = re.match(r'^(\d+(\.\d+)*\.?)', original_heading.strip())
                current_number = match_num.group(1) if match_num else None

                # 계층 삭제 검사
                if current_number:
                    is_child_of_blocked = False
                    for prefix in blocked_prefixes:
                        if current_number.startswith(prefix):
                            is_child_of_blocked = True
                            break
                    if is_child_of_blocked: continue

                # 제목 기반 차단
                if "사건" in original_heading and "사고" in original_heading:
                    if current_number: blocked_prefixes.add(current_number)
                    continue
                if "다른 모드/게임에서의 플레이" in original_heading:
                    if current_number: blocked_prefixes.add(current_number)
                    continue

                # 블랙리스트 제목 차단 (일반 파일 제외)
                cleaned_heading = clean_heading(original_heading)
                if not is_general_file and cleaned_heading in EXCLUDED_HEADINGS:
                    if current_number: blocked_prefixes.add(current_number)
                    continue

                # =======================================================
                # 3. 정제 수행 및 제목 중복 제거
                # =======================================================
                cleaned_text = clean_text_content(original_text)

                if cleaned_heading:
                    # (1) [기존] 텍스트가 제목으로 시작하면 제거
                    # 예: Heading="개요", Text="개요 내용은..." -> "내용은..."
                    pattern_start = r'^(' + re.escape(cleaned_heading) + r'\s*)+'
                    cleaned_text = re.sub(pattern_start, '', cleaned_text).strip()

                    # (2) [NEW] 제목이 텍스트보다 길고, 제목이 텍스트로 시작하면 제거
                    # 예: Heading="내셔 남작 (Baron)", Text="내셔 남작" -> "" (삭제)
                    if cleaned_text and len(cleaned_text) < len(cleaned_heading):
                         if cleaned_heading.startswith(cleaned_text):
                             cleaned_text = ""

                    # (3) [기존] 제목이 텍스트 끝에서 반복되면 제거
                    pattern_end = r'(' + re.escape(cleaned_heading) + r'\s*)+$'
                    cleaned_text = re.sub(pattern_end, '', cleaned_text).strip()
                    
                    cleaned_text = cleaned_text.lstrip('.,- ').strip()

                if cleaned_text:
                    processed_sections.append({
                        "heading": cleaned_heading,
                        "text": cleaned_text
                    })
        
        new_data["sections"] = processed_sections

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(new_data, f, indent=2, ensure_ascii=False)
            
        print(f"✅ 생성 완료: {file_name}")

    except Exception as e:
        print(f"❌ 오류 발생 ({input_path}): {e}")

def process_directory(input_dir, output_dir):
    input_dir_path = Path(input_dir)
    output_dir_path = Path(output_dir)

    if not input_dir_path.exists():
        print(f"❌ 입력 경로를 찾을 수 없습니다: {input_dir_path}")
        return

    files = [f for f in input_dir_path.iterdir() if f.suffix == '.json']
    print(f"📂 총 {len(files)}개의 파일을 발견했습니다. 정제를 시작합니다...\n")

    for file_path in files:
        new_filename = f"preprocessed_{file_path.name}"
        output_file_path = output_dir_path / new_filename
        process_json_file(file_path, output_file_path)

# ==========================================
# 3. 메인 실행 함수 (Pathlib 적용)
# ==========================================
def main() -> None:
    # __file__: 현재 스크립트 파일의 경로
    # .resolve(): 절대 경로로 변환
    # .parents[2]: 현재 위치에서 2단계 상위 폴더(data)를 base_dir로 설정
    base_dir = Path(__file__).resolve().parents[2]

    # 입력 경로 찾기 (data/crawler/namuwiki/outputs/per-article)
    input_dir = base_dir / "crawler" / "namuwiki" / "outputs" / "per-article"

    # 출력 경로 설정 (data/preprocessed/namuwiki/outputs/per-article)
    output_dir = base_dir / "preprocessed" / "namuwiki" / "outputs" / "per-article"

    print(f"🚀 기준 경로(Data): {base_dir}")
    print(f"📂 입력 경로: {input_dir}")
    print(f"💾 출력 경로: {output_dir}")
    print("-" * 50)

    process_directory(input_dir, output_dir)
    print("✨ 모든 작업이 완료되었습니다.")

if __name__ == "__main__":
    main()