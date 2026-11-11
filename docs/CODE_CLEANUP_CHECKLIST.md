# Posid PDF — 소스 정리 검증 체크리스트

모든 명령은 저장소 루트(`E:\Pjt\PdfCompare`)의 PowerShell에서 실행한다.

## 1. 정리 전 기준선 (2026-11-11, 커밋 `ad1835e`)

```powershell
git status -s          # 비어 있어야 함
.\.venv\Scripts\python.exe -m unittest discover -s tests 2>&1 | Select-String -Pattern "^(ERROR|FAIL):|^Ran |^FAILED|^OK"
```

기준 결과: **Ran 222 tests — FAILED (failures=1, errors=9, skipped=1)**

| 종류 | 테스트 | 원인(정리와 무관) |
| --- | --- | --- |
| ERROR | `test_brand_icons` (모듈 로드) | Pillow 미설치 |
| ERROR | `test_open_doc_picker` (모듈 로드) | pytest 미설치 |
| ERROR | `test_posid_branding` (모듈 로드) | pytest 미설치 |
| ERROR | `test_themes` (모듈 로드) | pytest 미설치 |
| ERROR | `test_viewer_shell` (모듈 로드) | pytest 미설치 |
| ERROR | `test_workspace_features` (모듈 로드) | pytest 미설치 |
| ERROR ×3 | `test_pdf_comparison_options` 의 `(tool='HFCompareWidget')` 3건 | Windows 임시 PDF 삭제 권한(PyMuPDF 파일 잠금) |
| FAIL | `test_pdf_compare_header.SharedHeaderTests.test_focus_mode_round_trip_and_close_tool_action` | 헤더 ✕ 툴팁 문구 변경(기대값 "현재 도구 닫기 …") |

> 정리 후 결과는 **위와 정확히 같아야** 한다(테스트 수 222, 같은 실패·에러 목록). 하나라도 늘면 해당 단계를 되돌린다.
> pytest/Pillow를 사용자 승인하에 설치한 경우, 설치 직후 정리 전에 기준선을 다시 측정한다.

## 2. 단계별 검증

모든 단계 공통:

```powershell
.\.venv\Scripts\python.exe -m compileall -q app configs main.py build.py
.\.venv\Scripts\python.exe -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from PyQt6.QtWidgets import QApplication; a=QApplication([]); from app.main_window import MdiMainWindow; w=MdiMainWindow(); print('OK', w.windowTitle())"
```

### A1 (과거 도구 파일 삭제)
- [ ] `git ls-files app/tools` 결과가 `__init__.py, file_rename.py, pdf_compare.py, pdf_create.py, pdf_editor.py, pdf_form.py, pdf_header_footer_compare.py` 7개
- [ ] 활성 도구 동적 import 확인:
  ```powershell
  .\.venv\Scripts\python.exe -c "import importlib; [importlib.import_module('app.tools.'+m) for m in ('pdf_compare','pdf_header_footer_compare','pdf_editor','pdf_create','file_rename','pdf_form')]; print('tools OK')"
  ```
- [ ] 소스에 잔여 참조 없음: 검색어 `pdf_split|pdf_merge|pdf_page_editor|PdfSplitWidget|PdfMergeWidget|PdfPageEditorWidget` → `app/`, `tests/`, `build.py`에서 0건(`pdf_form.py`의 `pdf_split_page`는 무관)

### A2 (loading_dialog)
- [ ] 검색어 `LoadingDialog|LoadingManager` → 0건
- [ ] `.\.venv\Scripts\python.exe -c "from app.common.loading_dialog import make_overlay_progress, update_overlay_progress, style_task_progress, note_progress; print('OK')"`
- [ ] `.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_file_rename_rules.py 2>&1 | Select-Object -Last 5`

### A3·A4 (비교 도구)
- [ ] 검색어 `show_legend_caution_dialog` → `pdf_compare.py`, `pdf_header_footer_compare.py`, `main_window.py`에 남아 있음
- [ ] `.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_pdf_compare_multipage.py 2>&1 | Select-Object -Last 20`
- [ ] `.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_pdf_comparison_options.py 2>&1 | Select-Object -Last 20` (기존 HFCompareWidget 3 ERROR만 허용)
- [ ] `.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_pdf_compare_header.py 2>&1 | Select-Object -Last 20` (기존 1 FAIL만 허용)

### A5·A6·A7 (resources / styles / theme)
- [ ] `.\.venv\Scripts\python.exe -c "from app.common.resources import get_icon_path, get_logo_path, get_about_image_path, get_about_icon_path, get_timer_gif_path as g; print(get_icon_path(), get_logo_path(), get_about_image_path(), get_about_icon_path(), g())"` → 모두 None이 아님
- [ ] `.\.venv\Scripts\python.exe -c "from app.common.styles import MODERN_QSS; from app.shell.theme import build_shell_qss; print(len(MODERN_QSS), len(build_shell_qss('gold')))"`
- [ ] `.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_about_dialog.py 2>&1 | Select-Object -Last 5`
- [ ] `.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_sidebar_quiet_brand.py 2>&1 | Select-Object -Last 5`

### A8·A9·A10 (셸 / 인쇄 / 폼)
- [ ] 검색어 `hide_search|work_mode\(\)|_full_pdf|leaf_name` → 0건 (`toggle_work_mode`/`open_work_mode`/`close_work_mode`는 남아야 함)
- [ ] `.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_print_*.py" 2>&1 | Select-Object -Last 10`
- [ ] `.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_alignment_dialog.py 2>&1 | Select-Object -Last 5`
- [ ] `.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_pdf_form.py 2>&1 | Select-Object -Last 5`
- [ ] `.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_presentation.py 2>&1 | Select-Object -Last 5`
- [ ] `.\.venv\Scripts\python.exe -m unittest tests.test_scroll_anchor tests.test_split_drop 2>&1 | Select-Object -Last 5`

### A11 (미사용 import)
- [ ] §3 스캔을 다시 실행해 남은 결과가 `annotations`(오탐)와 AUDIT B/C 관련 항목뿐인지 확인
- [ ] `pdf_header_footer_compare.py`에 `SyncScrollToggle  # noqa: F401 (re-export)` 줄이 남아 있음

## 3. 미사용 import 스캔 (읽기 전용)

아래 스크립트를 **저장소 밖**(예: `%TEMP%\unused_imports.py`)에 저장해 실행한다. 저장소에 파일을 만들지 않는다.

```python
import ast, io, sys, tokenize
from pathlib import Path
ROOT = Path(sys.argv[1])
files = [p for d in ('app', 'configs', 'scripts') for p in (ROOT / d).rglob('*.py') if '__pycache__' not in p.parts]
files += [ROOT / 'main.py', ROOT / 'build.py']
for p in sorted(files):
    if p.name == '__init__.py':
        continue
    src = p.read_text(encoding='utf-8'); lines = src.splitlines()
    names = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Import, ast.ImportFrom)) and 'noqa' not in lines[node.lineno - 1]:
            for a in node.names:
                if a.name != '*':
                    names.append(((a.asname or a.name.split('.')[0]), node.lineno, a.name))
    toks = [(t.string, t.start[0]) for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.NAME]
    for bound, ln, full in names:
        if bound != 'annotations' and not [l for s, l in toks if s == bound and l != ln]:
            print(f'{p.relative_to(ROOT)}:{ln}\t{full}')
```

```powershell
.\.venv\Scripts\python.exe $env:TEMP\unused_imports.py E:\Pjt\PdfCompare
```

## 4. 최종 검증

- [ ] 전체 테스트가 §1 기준선과 동일:
  ```powershell
  .\.venv\Scripts\python.exe -m unittest discover -s tests 2>&1 | Select-String -Pattern "^(ERROR|FAIL):|^Ran |^FAILED|^OK"
  ```
  기대: `Ran 222 tests`, `failures=1, errors=9, skipped=1`, 목록 동일
- [ ] 비교 회귀: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_pdf_compare_multipage.py 2>&1 | Select-Object -Last 20`
- [ ] `git status -s` 결과가 PLAN의 대상 파일만 포함(그 외 파일 변경 없음)
- [ ] `git diff --stat`의 변경이 삭제 위주(추가 라인은 import 줄 재작성 정도)
- [ ] B·C 항목 파일이 diff에 없음: `configs/target_qamate.py`, `assets/**`, `build.py`, `scripts/make_icons.py`, `app/print_engine/verify.py`, `app/presentation/navigation.py`, `app/services/print_presets.py`, `app/shell/print_cards.py`, `app/viewer/document_manager.py`
- [ ] (선택, 사용자 요청 시) 빌드: `python build.py --target posid 2>&1 | Select-Object -Last 30` → 성공, `dist/PDFCompare/PDFCompare.exe` 실행 확인

## 5. 수동 확인 (실제 앱, `python main.py`)

| # | 기능 | 확인 내용 | 관련 항목 |
| --- | --- | --- | --- |
| 1 | 기동 | 창 제목 `Posid PDF`, 창/작업표시줄 아이콘, 사이드바 로고 | A5, A6, A7 |
| 2 | PDF 보기 | PDF 열기, 확대/축소/맞춤, 배율 입력, 페이지 이동 | 공통 |
| 3 | 뷰어 검색 | 검색어 입력 시 실시간 강조, 이전/이후, n/N, 검색어 삭제 시 강조 해제, Ctrl+F | A8 |
| 4 | 정보/편집 패널 | 패널 토글, 경로 복사, 편집 패널 버튼(편집/생성/영역지정/전체비교) | A8 |
| 5 | 영역지정비교 | 영역 드래그, 비교 실행, 진행률 오버레이, 검색, '범례 및 주의사항' 팝업 | A2, A3 |
| 6 | 전체비교 | 비교 실행, 하이라이트, 진행률 | A2, A4 |
| 7 | PDF 편집 | 분할/병합/페이지 회전·이동, 진행률 막대 | A1, A2 |
| 8 | PDF 생성 / 파일이름 | 변환 실행, 진행률 막대 | A2 |
| 9 | PDF 입력폼 관리 | 샘플 양식 열기, 필드 목록, 작성/저장 | A10 |
| 10 | 인쇄 | 뷰어 🖨 인쇄 → 미리보기, PDF 저장, (가능 시) 인쇄 | A9 |
| 11 | 두 PDF 동시 보기 / 발표모드 | 동기 스크롤·확대, 인쇄, 발표 시작/종료 | 공통 |
| 12 | 테마 전환 | 설정에서 테마 변경 시 도구 표 헤더·버튼 색 갱신 | A6, A7 |
