# Project Context & Token Optimization Rules

## 1. Agent Behavior & Token Saving (CRITICAL)
- **No Blind Exploration**: 사용자가 `@파일`을 지정했거나 경로가 명확한 경우, 전체 디렉토리 탐색(`find`, `ls -R`, 광범위한 `grep`)을 절대 수행하지 마라. 추가 파일 확인이 필요하면 먼저 경로를 묻거나 최소한의 타겟 파일만 읽어라.
- **Partial File Read**: 300줄 이상의 파일은 전체를 읽지 말고, `grep -n`으로 라인 번호를 먼저 찾은 뒤 필요한 구간만 읽어라.  
  주요 대형 파일: `app/tools/pdf_compare.py`, `app/tools/pdf_header_footer_compare.py`, `app/tools/pdf_editor.py`, `app/main_window.py`, `app/tools/pdf_form.py`
- **Quiet CLI Execution**: 테스트, 빌드, 린트 실행 시 전체 성공 로그가 출력되지 않도록 반드시 `| tail -n 30`으로 출력을 제한해라.
- **Concise Output**: 코드 설명이나 인사말을 생략하고, 변경 사항의 핵심만 3줄 이내로 요약해라. 전체 코드를 다시 출력하지 말고 수정된 부분만 언급해라.
- **Cross-Tool Handoff**: 외부 IDE나 다른 에이전트가 수정한 내역을 파악할 때는 파일을 일일이 읽지 말고 `git status -s` 및 `git diff`만 실행해 변경점을 파악해라.

## 2. Tech Stack & Architecture Map
- **Stack**: Python 3, PyQt6, PyMuPDF, pywin32, PyInstaller (Windows 데스크톱)
- **Entry & Routing**: `main.py` → `app/main_window.py` (`MdiMainWindow`)
- **Core Business Logic**:
  - `app/tools/` — 도구 위젯 (pdf_compare, pdf_header_footer_compare, pdf_editor, pdf_create, file_rename, pdf_form 등)
  - `app/common/` — 워커·헬퍼 (pdf_compare_worker, pdf_convert, pdf_form/, styles, about_dialog, resources)
  - `app/viewer/` — PDF 뷰어 (document_manager, pdf_canvas, render_service, page_cache, split_view)
  - `app/services/` — 설정·최근 문서·작업공간 세션
- **UI Shell**: `app/shell/` (welcome_page, viewer_workspace, theme, sidebar_icons, command_palette, settings_page, work_panel)
- **Targets & Config**: `configs/` (settings.py, target_posid/post/nuni/qamate), `assets/{posid,post,nuni,qamate}/`
- **Build**: `build.py` (타겟별 빌드, `BUILD_TARGET` 환경변수)
- **Tests**: `tests/` (unittest, offscreen Qt)

## 3. Token-Efficient Commands
- **Test (전체)**: `.\.venv\Scripts\python.exe -m unittest discover -s tests | tail -n 30`
- **Test (단일/패턴)**: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_pdf_comparison_options.py | tail -n 20`
- **비교 회귀**: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_pdf_compare_multipage.py | tail -n 20`
- **빌드 확인**: `python build.py --target nuni` (또는 posid/post) — 로그는 `| tail -n 30` 권장
- **버전 주입 확인**: `type app\common\build_version.txt`

## 4. Strict Ignore List (절대 읽거나 탐색하지 말 것)
- `__pycache__/`, `.venv/`, `venv/`, `env/`
- `build/`, `dist/`, `*.spec`, `*.manifest`
- `*.log`, `*.pyc`, `*.pyo`
- `assets/` 내 대용량 이미지·아이콘 (경로만 확인, 내용 읽기 금지)
- `*.tmp`, `*.temp`, local config (`config.local.py`, `settings.local.py`)

## 5. Current Active Task (선택 사항)
- **Focus Files**: `app/tools/pdf_editor.py`, `app/common/about_dialog.py`, `app/shell/viewer_workspace.py`
- **Status**: 뷰어 우선 실행 + 통합 PDF 편집/About 팝업 구조 유지 중. 도구 캐시(LRU 3개), 타겟별 빌드 분리 유지.
