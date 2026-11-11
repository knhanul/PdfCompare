# Posid PDF — 소스 정리 사전 분석 (AUDIT)

- 분석일: 2026-11-11 / 기준 커밋: `ad1835e` (작업 트리 clean)
- 분석 범위: `app/`, `configs/`, `scripts/`, `main.py`, `build.py`, `tests/`, `assets/`(경로만), `docs/`, README/build.md
- 이 문서는 **분석 결과만** 담는다. 이 단계에서는 소스를 수정하지 않았다.
- 참고: 앞서 언급된 'Posid PDF — 전체 소스 정리 및 미사용 기능·리소스 안전 제거' 요구사항 원문은 저장소/대화에 없었다. 일반적인 기준(미사용 기능·코드·리소스를 안전하게 제거, 활성 기능과 과거 제거 기능 구분)으로 분석했다.

## 1. 분석 방법

| 항목 | 방법 |
| --- | --- |
| 정적 참조 | AST로 모든 최상위 함수/클래스/메서드/대문자 상수를 수집하고, 소스+테스트 전체에서 식별자 토큰 수(주석·docstring 제외)를 셈 |
| 동적 import | `main_window.tool_definitions`의 `module_path`/`class_name` → `importlib.import_module`, 지연 import(`# lazy`), `build.py`의 `app/tools/*.py` glob hidden-import, `configs.settings.TARGET_MODULES` |
| 문자열 기반 호출 | `getattr/hasattr/setattr` 전수 확인. 모두 리터럴 이름(`'_style_file_table'`, `'show_legend_caution_dialog'`, `'viewer1'`, `'add_paths'`, `'load_pdf'` 등)이므로 토큰 스캔에 포함됨. 변수 기반 동적 접근은 후보 심볼과 무관 |
| Signal/Slot | 모든 `pyqtSignal` 정의의 `.emit(`/`.emit` 슬롯 연결/`.connect(` 수를 확인 |
| Qt 리소스 | `.qrc`/`.ui` 파일 없음. 이미지·아이콘은 `app/common/resources.py`의 파일 경로 탐색으로만 로딩 |
| 패키징 | `build.py`(PyInstaller `--add-data assets`, `--splash`, `--icon`, hidden-import), `scripts/make_icons.py`(ICO/MSIX 자산 생성), `main_window._set_app_user_model_id`(MSIX AUMID) |
| 테스트 | `mock.patch('app....')` 문자열 패치 대상 확인(제거 대상 import와 충돌 없음) |
| 이력 | `git log -S`로 과거 제거된 메뉴 확인 (`d73782d Register unified PDF editor tool and remove separate split/merge/page menus`) |

## 2. 기능 현황 (활성 vs 과거 제거)

| 구분 | 기능 | 진입점 | 상태 |
| --- | --- | --- | --- |
| 활성 | PDF 보기(탭 뷰어) | `app/shell/viewer_workspace.py` | 유지 |
| 활성 | 두 PDF 동시 보기 | `app/viewer/split_view.py` (lazy) | 유지 |
| 활성 | 영역지정비교 / 전체비교 | `app.tools.pdf_compare` / `app.tools.pdf_header_footer_compare` (동적 import) | 유지 |
| 활성 | PDF 편집 / PDF 생성 / 파일이름 / PDF 입력폼 관리 | `app.tools.pdf_editor` / `pdf_create` / `file_rename` / `pdf_form` (동적 import) | 유지 |
| 활성(개발 중) | 스마트 인쇄 | `app/shell/print_dialog.py`, `print_cards.py`, `alignment_dialog.py`, `app/print_engine/*`, `app/services/print_presets.py` | 유지. `docs/SMART_PRINT_PROGRESS.md`에 미완 항목·"향후 연동 인터페이스 유지" 명시 |
| 활성(신규) | 발표모드 | `app/presentation/*` (lazy) | 유지 |
| 활성 | 설정/명령 팔레트/전체 찾기/작업 패널 | `app/shell/*` | 유지 |
| **과거 제거** | 개별 분할/병합/페이지 편집 메뉴 | `app/tools/pdf_split.py`, `pdf_merge.py`, `pdf_page_editor.py` | 메뉴 등록 해제됨(`d73782d`). `pdf_editor.py`로 통합. 파일만 남음 |
| 빌드 타겟 | posid(기본), post, nuni | `configs/settings.TARGET_MODULES`, `build.py TARGETS` | 유지 |
| 빌드 타겟(비활성) | qamate | `configs/target_qamate.py` | `TARGET_MODULES`/`build.py`에 없음. README에 "빌드 대상 아님"으로 명시 → 보류 |

## 3. 위험도 기준

- **A (낮음)**: 소스·테스트·빌드·문자열 참조가 모두 0이며, 대체 구현이 확인됨. 제거해도 동작 변화 없음.
- **B (보류)**: 참조는 없지만 외부(패키징 도구·향후 기능·공개 API) 사용 가능성이 있거나 개발 중 기능의 일부. **이번 정리에서 삭제하지 않는다.**
- **C (유지)**: 테스트·빌드·런타임에서 사용 중. 삭제 금지.

---

## 4. 삭제 후보 — 위험도 A

> 라인 번호는 기준 커밋(`ad1835e`) 기준이다. 편집 후 번호가 바뀌므로 **반드시 심볼 이름으로 위치를 다시 찾아** 작업한다.

### A1. 과거 제거된 개별 편집 도구 파일 3개 (파일 삭제)

| 파일 | 클래스 | 현재 참조 |
| --- | --- | --- |
| `app/tools/pdf_split.py` | `PdfSplitWidget` (15–219) | 없음 |
| `app/tools/pdf_merge.py` | `PdfMergeWidget` (14–143) | 없음 |
| `app/tools/pdf_page_editor.py` | `PdfPageEditorWidget` (14–219) | 없음 |

- 근거: `main_window.tool_definitions`(6개: pdf_compare, pdf_hf_compare, pdf_editor, pdf_create, file_rename, pdf_form)에 없음. 소스·테스트·문서 어디에서도 모듈명/클래스명 참조 0. 커밋 `d73782d`에서 메뉴 제거, 기능은 `pdf_editor.py`로 통합(README "하나의 창에서 분할·병합·페이지 편집").
- 유일한 연결: `build.py` 103–105행이 `app/tools/*.py`를 glob해 hidden-import로 추가 → 파일 삭제 시 자동으로 빠지므로 `build.py` 수정 불필요.
- `pdf_form.py`의 `self.pdf_split_page`는 이름만 비슷한 내부 위젯으로 무관.
- 관련 테스트: 없음.
- 제거 후 확인: 앱 실행, 사이드바 6개 도구 모두 열림, `PDF 편집`의 분할/병합/페이지 편집 동작, `python -c "import app.tools.pdf_editor"`.

### A2. `app/common/loading_dialog.py` — `LoadingDialog`, `LoadingManager`

- 삭제 구간: `class LoadingDialog(QDialog)` (83–198), `class LoadingManager` (201–228, 파일 끝까지).
- 현재 참조: `LoadingManager`는 자기 docstring 외 0회. `LoadingDialog`는 `LoadingManager.__init__`에서만 사용 → 연쇄 고아.
- 유지: `_progress_qss`, `make_overlay_progress`, `update_overlay_progress`, `style_task_progress`, `note_progress` (비교·편집·생성·파일이름 도구에서 사용).
- 삭제 후 미사용이 되는 import(같은 파일, 함께 제거): `import os`, `Qt`(`from PyQt6.QtCore import Qt, QEventLoop`에서 `Qt`만), `from PyQt6.QtGui import QMovie` 전체, `QDialog`, `QVBoxLayout`, `QLabel`, `from app.common.resources import get_timer_gif_path` 전체.
  - 남는 import: `from PyQt6.QtCore import QEventLoop`, `from PyQt6.QtWidgets import QProgressBar, QApplication`, `from app.common.styles import COLOR_PRIMARY`.
- `get_timer_gif_path` 자체는 `pdf_compare.py`·`pdf_header_footer_compare.py`에서 계속 사용 → 유지.
- 관련 테스트: 직접 없음(비교/편집 테스트가 진행률 함수 사용).
- 제거 후 확인: 비교 실행 시 오버레이 진행률 막대, PDF 편집/생성/파일이름 진행률 막대.

### A3. `app/tools/pdf_compare.py` — 미사용 메서드 6개

| 심볼 | 라인 | 근거 |
| --- | --- | --- |
| `SelectableLabel._clamp_to_image` | 108–114 | 호출 0 (`_image_rect`는 다른 곳에서 사용 → 유지) |
| `PDFViewer.flash_search_highlight` | 1006–1014 | 호출 0. 검색 강조는 `PDFSearchHelper.highlight_current_result`로 대체 |
| `PDFViewer.remove_flash_highlight` | 1016–1024 | `flash_search_highlight` 내부 람다에서만 호출 → 연쇄 고아 |
| `PdfCompareWidget.show_legend_dialog` | 1835–1867 | 호출 0. `show_legend_caution_dialog`(1779, `main_window`가 `hasattr` 문자열로 호출)로 통합됨 |
| `PdfCompareWidget.show_caution_dialog` | 1869–1897 | 위와 동일 |
| `PdfCompareWidget.add_hl` | 1899–1904 | 호출 0 |

- 유지(C): `show_legend_caution_dialog`, `comparison_caution_html`, `on_selection_complete`, `extract_and_process_text`(테스트 사용).
- 삭제 후 import 확인: `QDialog`, `QTimer`는 같은 파일 다른 곳에서 계속 사용될 가능성이 높음 → 삭제 후 미사용 import 스캔(CHECKLIST §3)으로 확인하고 미사용일 때만 제거.
- 관련 테스트: `tests/test_pdf_compare_multipage.py`, `tests/test_pdf_comparison_options.py`, `tests/test_pdf_compare_header.py`.
- 제거 후 확인: 영역지정비교 검색(이전/이후, 강조), 헤더 '📋 범례 및 주의사항' 팝업, 영역 드래그 선택.

### A4. `app/tools/pdf_header_footer_compare.py` — `HFCompareWidget._add_hl`

- 삭제 구간: 1371–1376. 호출 0. (A3 `add_hl`과 동일한 복제 코드)
- 관련 테스트: `test_pdf_compare_multipage.py`, `test_pdf_comparison_options.py`.
- 제거 후 확인: 전체비교 실행·하이라이트 표시.

### A5. `app/common/resources.py` — `get_resource_path`

- 삭제 구간: 71–75. 호출 0 (소스·테스트·빌드).
- 유지: `_candidate_paths`, `legacy_aliases` 딕셔너리 전체(`get_logo_path`·`get_icon_path`가 `'posid_logo.png'`, `'icon.ico'` 키를 사용). `'posid_logo.ico'` 키는 `get_resource_path` 삭제 후 미사용이 되지만 **B로 보류**(B6) — 딕셔너리는 수정하지 않는다.
- 관련 테스트: `test_about_dialog.py`, `test_brand_icons.py`(PIL 필요), `test_posid_branding.py`(pytest 필요).
- 제거 후 확인: 창 아이콘, 사이드바 로고, 정보 팝업 이미지.

### A6. `app/common/styles.py` — 미사용 상수 10개

| 라인 | 상수 |
| --- | --- |
| 5 | `COLOR_SECONDARY` |
| 6 | `COLOR_SIDEBAR_BG` |
| 25 | `COLOR_MDI_BG` |
| 31 | `COLOR_BORDER_LIGHT` |
| 32 | `COLOR_HOVER` |
| 52–56 | `_IOS_GREEN`, `_IOS_ORANGE`, `_IOS_ORANGE_HOVER`, `_IOS_ORANGE_PRESSED`, `_IOS_RED` |

- 근거: 전체 토큰 스캔에서 정의 1회 외 0회(`MODERN_QSS` f-string 포함 확인). `import *` 없음.
- 주의: `_IOS_GRAY_BG`, `_IOS_GROUPED_BG`, `_IOS_SEPARATOR`, `_IOS_FILL`, `_PRIMARY*`, `_SIDEBAR_*`는 `MODERN_QSS`에서 사용 → 유지.
- 관련 테스트: `test_themes.py`(pytest 필요), `test_sidebar_quiet_brand.py`.
- 제거 후 확인: 앱 기동(모듈 import 시 f-string 평가 오류가 없어야 함), 기본 테마 외관.

### A7. `app/shell/theme.py` — `SHELL_QSS`

- 삭제 구간: 519행 `SHELL_QSS = build_shell_qss()  # compatibility for existing imports` (1줄).
- 근거: import하는 곳 0. 모든 호출부가 `build_shell_qss(theme_id)`를 직접 사용. 모듈 import 시 불필요한 QSS 생성 비용도 제거됨.
- 관련 테스트: `test_themes.py`, `test_sidebar_quiet_brand.py`, `test_posid_branding.py`.
- 제거 후 확인: 테마 전환(설정 → 테마).

### A8. `app/shell/viewer_workspace.py` — `work_mode`, `hide_search`

| 심볼 | 라인 | 근거 |
| --- | --- | --- |
| `ViewerWorkspace.work_mode` | 246–247 | 호출 0 (`self.work_panel.mode`를 직접 사용) |
| `ViewerWorkspace.hide_search` | 461–462 | 호출 0. 별도 검색 바 제거 후 남은 함수(툴바 검색창은 `textChanged`로 정리) |

- 유지: `show_search`(Ctrl+F, `main_window` 명령 팔레트에서 호출), `toggle_work_mode`/`open_work_mode`/`close_work_mode`.
- 관련 테스트: `test_workspace_features.py`, `test_viewer_shell.py`(pytest 필요), `test_print_dialog.py`, `test_open_doc_picker.py`.
- 제거 후 확인: Ctrl+F 포커스, 검색어 지우면 하이라이트·카운트 초기화, 정보/편집 패널 토글.

### A9. `app/shell/print_dialog.py` — `SmartPrintDialog._full_pdf`

- 삭제 구간: 1306–1312 (`# ── 출력 ──` 주석은 유지, 바로 아래 `_full_pdf` 메서드만 삭제).
- 근거: 호출 0. `docs/SMART_PRINT_PROGRESS.md` 30행: "PDF 저장/인쇄용 생성은 `_BuildWorker(QThread)`로 비동기"로 대체됨.
- 삭제 후 확인: `build_pdf` import가 `_BuildWorker` 등에서 계속 쓰이는지 확인(쓰이면 import 유지).
- 관련 테스트: `test_print_dialog.py`, `test_print_presets.py`, `test_print_page_transition.py`, `test_alignment_dialog.py`.
- 제거 후 확인: 인쇄 화면의 'PDF 저장', '인쇄' 버튼.

### A10. `app/common/pdf_form/field_models.py` — `LogicalField.leaf_name`

- 삭제 구간: 164–167 (`@property` 데코레이터 포함 4줄).
- 근거: 호출 0, 문자열 접근 0, dataclass 직렬화 대상 아님(property). `parent_group`/`hierarchy_path`는 사용 중 → 유지.
- 관련 테스트: `test_pdf_form.py`.
- 제거 후 확인: 입력폼 관리 – 양식 열기/작성/필드 목록.

### A11. 미사용 import (파일별)

`from __future__ import annotations`는 **제외**(오탐). A1에서 삭제되는 파일도 제외.

| 파일 | 제거할 이름 (해당 import 문에서 이 이름만 제거) |
| --- | --- |
| `app/common/pdf_compare_worker.py` | `Any` (10행) |
| `app/common/pdf_search_helper.py` | `QTimer` (5행), `QPainter` (6행) |
| `app/main_window.py` | `DEVELOPER`, `get_logo_path` (11행), `COLOR_PRIMARY` (12행) |
| `app/presentation/canvas.py` | `QCursor` (9행) |
| `app/presentation/overlay.py` | `QPropertyAnimation` (2행), `QGraphicsOpacityEffect` (3행) |
| `app/presentation/window.py` | `QAction` (8행), `QApplication` (9행) |
| `app/print_engine/stream.py` | `field` (9행), `PageInfo` (11행) |
| `app/tools/file_rename.py` | `header_section_qss` (19행), `COLOR_BORDER` (20행) |
| `app/tools/pdf_compare.py` | `QEasingCurve`, `QParallelAnimationGroup`, `QPropertyAnimation`, `QMimeData` (5행), `QFileDialog`, `QGraphicsOpacityEffect` (7행) |
| `app/tools/pdf_create.py` | `header_section_qss` (20행), `COLOR_BORDER`, `COLOR_PRIMARY` (21행) |
| `app/tools/pdf_editor.py` | `header_section_qss` (18행) |
| `app/tools/pdf_form.py` | `QUrl` (3행), `QDesktopServices` (4행), `COLOR_BORDER`, `COLOR_PRIMARY` (28행), `try_open_pdf`, `show_open_error` (50행) |
| `app/tools/pdf_header_footer_compare.py` | `QRectF` (5행), `try_open_pdf`, `show_open_error` (20행), `THEMES`, `theme_tokens` (27행) |
| `app/viewer/pdf_canvas.py` | `QRect` (2행) |
| `app/viewer/split_view.py` | `QCheckBox` (7행) |

- 근거: 각 파일에서 import 줄 외 토큰 사용 0. 테스트의 `mock.patch` 대상(`app.tools.pdf_compare.QMenu`, `app.tools.pdf_header_footer_compare.QMessageBox`, `app.tools.file_rename.QMessageBox`, `app.shell.print_dialog.QInputDialog`)과 겹치지 않음. 테스트가 이 이름들을 해당 모듈에서 import하지 않음.
- **절대 제거 금지**: `pdf_header_footer_compare.py` 24행 `SyncScrollToggle  # noqa: F401 (re-export)` — `tests/test_pdf_compare_multipage.py` 150행이 이 모듈에서 import함.
- `pdf_compare_worker.py`의 `Any`가 타입 주석 문자열 안에서 쓰이는지 삭제 전 한 번 더 확인(`"Any"` 문자열 검색).
- 제거 후 확인: 각 모듈 `py_compile`, 전체 테스트.

---

## 5. 보류 — 위험도 B (이번 정리에서 삭제 금지)

| ID | 대상 | 참조 현황 | 보류 사유 |
| --- | --- | --- | --- |
| B1 | `configs/target_qamate.py`, `assets/qamate/.gitkeep` | `TARGET_MODULES`·`build.py`에 없음 | README·Claude.md에 타겟으로 명시("빌드 대상 아님"). 향후 타겟일 수 있음 → 사용자 확인 필요 |
| B2 | `assets/posid/icon-44x44.png`, `icon-50x50.png`, `icon-150x150.png` | 코드 참조 0 | MSIX AppxManifest(Square44x44/StoreLogo 50/Square150x150) 규격 크기. 저장소 밖 MSIX 패키징 도구에서 사용 가능성 |
| B3 | `assets/posid/posid_logo.ico`, `posid_logo_256.png`, `posid_ename.png` | 코드 참조 0 | 브랜드 원본 자산. 외부 패키징/문서/스토어 등록용일 수 있음 |
| B4 | `ViewerWorkspace.tab_count_changed`, `DocumentManager.document_opened`, `document_closed` (Signal) | emit만 있고 connect 0 | 뷰어 코어의 공개 이벤트. 제거 이득 작고 확장 지점 |
| B5 | `PresentationCanvas.sections_left` (canvas.py 293–304), `print_presets.is_builtin` (52–53), `print_cards.Card.refresh_icon` (192–193) | 호출 0 | 발표모드·스마트 인쇄는 진행 중 기능(PROGRESS 문서에 미완 항목) |
| B6 | `resources.legacy_aliases['posid_logo.ico']` 항목, `get_timer_gif_path`의 `nuni_timer_w.gif` 후보 경로 | 실질 미도달 | 구버전 번들 호환 폴백. 실행 환경별 차이 검증 비용 대비 이득 작음 |
| B7 | `FormDocumentSession.add_radio_option` (form_service.py 499–519) | 호출 0 | 폼 서비스 공개 API(라디오 항목 추가). UI 확장 시 필요 |
| B8 | 타겟 플래그 `ENABLE_LICENSE_MENU`, `ENABLE_INTERNAL_REPORT`, `SETTINGS['LOGO_PATH'/'ICON_PATH'/'ASSET_DIR_PATH']` | 코드 소비 0 | README '라이선스 메뉴/내부 보고서' 절에 문서화된 설정 계약 |
| B9 | `docs/SMART_PRINT_*.md`, `docs/PRESENTATION_*.md`, `Info_popup.md`, `.claude/agents/pdf-print-expert.md` | — | 문서·에이전트 설정. 코드 정리 범위 외 |

## 6. 유지 — 위험도 C (참조 없어 보여도 삭제 금지)

| 대상 | 사용처 |
| --- | --- |
| `print_engine/verify.py` `coverage` | `test_print_engine_core.py`, `test_print_engine_stream.py` |
| `print_engine/pagespec.py` `parse_multi`, `stream.py` `src_to_out`/`out_to_src` | 테스트 + PROGRESS "향후 전체비교 연동 인터페이스 유지" |
| `PresentationCanvas.to_view`, `navigation.sections_in_page` | `test_presentation.py` |
| `SmartPrintDialog.render_idle` | `test_print_dialog.py` |
| `PDFViewer.on_selection_complete`, `extract_and_process_text` | `test_pdf_compare_multipage.py` |
| `PageCache.size_bytes` | `test_viewer_shell.py` |
| `pdf_header_footer_compare.SyncScrollToggle` re-export | `test_pdf_compare_multipage.py` |
| `app/tools/*` 활성 6개 모듈 | 문자열 기반 동적 import (`tool_definitions`) |
| `configs.target_posid/post/nuni` | `TARGET_MODULES` 동적 import + `build.py` hidden-import |
| `build.py`의 app/tools glob | 동적 import 도구 번들링에 필수 |
| `assets/AIKickOff.png`, `about_blue.svg`, `nuni_icon_orange_spin.gif` | `resources.get_about_image_path/get_about_icon_path/get_timer_gif_path` |
| `assets/posid_signature.png` | `build.py --splash` |
| `assets/sample_form.pdf` | `form_service.get_sample_form_pdf_path` |
| `assets/posid/posid_logo.png`, `posid_icon.ico`, `posid_logo_512.png`, `msix/*` | 로고/아이콘 런타임 로딩, `make_icons.py` 원본, `test_brand_icons.py` |
| `assets/post/*`, `assets/nuni/*` | post/nuni 빌드 타겟 |
| `app/common/build_version.txt` | 런타임 버전·타겟 감지, `build.py`가 덮어씀 |
| `main_window._set_app_user_model_id` | MSIX 실행 시 AUMID 처리 |
| 모든 `pyqtSignal`(B4 제외) | emit/connect 쌍 확인됨(`xxx.emit`을 슬롯으로 연결하는 패턴 포함) |

## 7. 정리 범위 밖 발견사항 (수정하지 말고 사용자에게 보고)

1. **nuni 아이콘 파일명 불일치**: `configs/target_nuni.py`·`build.py`는 `nuni_icon.ico`를 기대하지만 실제 파일은 `assets/nuni/nuni_ico.ico`. nuni 빌드에 아이콘이 적용되지 않을 가능성.
2. **README 타겟 표 오래됨**: `posid` 앱 이름 "Posid 데스크"/테마색 `#004b93` → 실제 `Posid PDF`/`#FF6B00`. README 프로젝트 구조에 viewer/shell/presentation/print_engine 미반영.
3. **README 작업 패널 설명 오래됨**: "상황형 툴바와 패널 표시" → 현재는 패널만 표시.
4. **테스트 환경**: `pytest` 미설치로 5개 모듈(`test_open_doc_picker`, `test_posid_branding`, `test_themes`, `test_viewer_shell`, `test_workspace_features`), `Pillow` 미설치로 `test_brand_icons`가 로드되지 않음. `build.py`가 호출하는 `scripts/make_icons.py`도 Pillow 필요(`check=False`라 실패해도 조용히 진행).
5. **기존 실패 1건**: `test_pdf_compare_header.SharedHeaderTests.test_focus_mode_round_trip_and_close_tool_action` — 테스트 68–69행은 `close_tool_btn` 툴팁을 `"현재 도구 닫기 (프로그램은 종료되지 않습니다)"`로 기대하지만, 이전 작업에서 `"현재 화면 닫기 (...)"`로 변경됨(확인 완료). 정리 작업과 무관하며 테스트 기대값 갱신 여부는 사용자 결정 사항.
