# Posid PDF — 소스 정리 실행 결과 (RESULT)

- 실행일: 2026-11-11 / 기준 커밋: `ad1835e` (실행 전 소스 변경 없음, 새로 만든 docs 3개만 untracked)
- 기준 문서: `CODE_CLEANUP_AUDIT.md`, `CODE_CLEANUP_PLAN.md`, `CODE_CLEANUP_CHECKLIST.md`
- 처리 범위: **위험도 A 항목(A1~A11)만**. B·C 항목은 수정하지 않음.
- 커밋: **하지 않음**. 모든 변경은 작업 트리에 있으며 `git diff HEAD`로 확인, `git restore --source=HEAD -- <경로>`(삭제 파일은 `git restore --staged --worktree`)로 항목별 복원 가능.

## 1. 실행 전 확인

- `git status -s`: 소스 변경 없음. 분석 이후 새 참조 관계 없음(Opus 스캔 재실행 결과 30개 무참조 심볼·38개 미사용 import 동일).
- 중단/보류 사유 없음. AUDIT와 실제 소스가 일치했다(라인 범위까지 동일).

## 2. 삭제한 파일과 코드

| 단계 | ID | 대상 | 삭제 규모 |
| --- | --- | --- | --- |
| 1 | A1 | `app/tools/pdf_split.py`, `pdf_merge.py`, `pdf_page_editor.py` 파일 3개 (`git rm`) | -581 |
| 2 | A2 | `app/common/loading_dialog.py`: `LoadingDialog`, `LoadingManager` + 연쇄 import 5줄 → 3줄 | -153 / +2 |
| 3 | A3 | `app/tools/pdf_compare.py`: `add_hl`, `show_caution_dialog`, `show_legend_dialog`, `remove_flash_highlight`, `flash_search_highlight`, `SelectableLabel._clamp_to_image` | -99 |
| 3 | A4 | `app/tools/pdf_header_footer_compare.py`: `HFCompareWidget._add_hl` | -7 |
| 4 | A5 | `app/common/resources.py`: `get_resource_path` | -6 |
| 4 | A6 | `app/common/styles.py`: 상수 10개 (`COLOR_SECONDARY`, `COLOR_SIDEBAR_BG`, `COLOR_MDI_BG`, `COLOR_BORDER_LIGHT`, `COLOR_HOVER`, `_IOS_GREEN`, `_IOS_ORANGE`, `_IOS_ORANGE_HOVER`, `_IOS_ORANGE_PRESSED`, `_IOS_RED`) | -10 |
| 4 | A7 | `app/shell/theme.py`: `SHELL_QSS` | -3 |
| 5 | A8 | `app/shell/viewer_workspace.py`: `hide_search`, `work_mode` | -6 |
| 5 | A9 | `app/shell/print_dialog.py`: `SmartPrintDialog._full_pdf` | -8 |
| 5 | A10 | `app/common/pdf_form/field_models.py`: `LogicalField.leaf_name` | -5 |
| 6 | A11 | 미사용 import **38개 이름**, 15개 파일 (AUDIT §4 A11 표와 일치) | ±1~2줄/파일 |

A11 상세(7+2+2+26+1 = 38): `pdf_compare_worker`(Any), `pdf_search_helper`(QTimer, QPainter), `main_window`(DEVELOPER, get_logo_path, COLOR_PRIMARY), `presentation/canvas`(QCursor), `presentation/overlay`(QPropertyAnimation, QGraphicsOpacityEffect), `presentation/window`(QAction, QApplication), `print_engine/stream`(field, PageInfo), `file_rename`(header_section_qss, COLOR_BORDER), `pdf_compare`(QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QMimeData, QFileDialog, QGraphicsOpacityEffect), `pdf_create`(header_section_qss, COLOR_BORDER, COLOR_PRIMARY), `pdf_editor`(header_section_qss), `pdf_form`(QUrl, QDesktopServices, COLOR_BORDER, COLOR_PRIMARY, try_open_pdf, show_open_error), `pdf_header_footer_compare`(QRectF, try_open_pdf, show_open_error, THEMES, theme_tokens), `pdf_canvas`(QRect), `split_view`(QCheckBox).

### 삭제 근거 (요약)
- A1: 도구 정의(`tool_definitions` 6개)·테스트·빌드·문서 어디에서도 참조 0. 커밋 `d73782d`에서 메뉴 제거, `pdf_editor.py`로 통합. `build.py`는 `app/tools/*.py` glob이라 수정 불필요.
- A2~A10: 소스·테스트·빌드·문자열(`getattr`/`hasattr`) 참조 0. 연쇄 고아(`LoadingDialog`→`LoadingManager`, `remove_flash_highlight`→`flash_search_highlight`)는 함께 제거. 대체 구현 확인(`show_legend_caution_dialog`, `PDFSearchHelper`, `_BuildWorker`).
- A11: AST+토큰 스캔으로 import 줄 외 사용 0. 테스트의 `mock.patch` 대상·테스트가 import하는 이름과 겹치지 않음을 확인.

## 3. 보류·유지 (손대지 않음)

- **B1~B9 전부 보류**: qamate 타겟, posid 아이콘 6개(`icon-44/50/150`, `posid_logo.ico`, `posid_logo_256.png`, `posid_ename.png`), 구독자 없는 Signal 3개, 발표모드/스마트 인쇄의 미사용 함수 3개(`sections_left`, `is_builtin`, `Card.refresh_icon`), `add_radio_option`, 구버전 호환 경로/타겟 플래그, 문서.
- **C 유지**: `show_legend_caution_dialog`(문자열 호출), `SyncScrollToggle` re-export(`# noqa`, 테스트 사용), 테스트 전용 함수들, `build.py`, `scripts/make_icons.py`, `assets/**`, `configs/**`, MSIX 관련 코드·리소스.
- 확인: `git diff HEAD --name-only`에 `assets/`, `configs/`, `build.py`, `scripts/`, `tests/`, B 항목 파일이 **없음**.
- **리소스·빌드 설정·의존성 정리는 A 등급에 해당 항목이 없어 수행하지 않음**(MSIX/Portable 리소스 보존 원칙).

## 4. 테스트 실행 결과

### 기준선 (실행 전) — `unittest discover -s tests`
`Ran 222 tests, FAILED (failures=1, errors=9, skipped=1)`

### 단계별 결과
| 시점 | Ran | failures | errors | skipped | 목록 |
| --- | --- | --- | --- | --- | --- |
| A1 후 | 222 | 1 | 9 | 1 | 기준선과 동일 |
| A2 후 | 222 | 1 | 9 | 1 | 동일(진행률 함수 import 확인) |
| A3·A4 후 | 222 | 1 | 9 | 1 | 동일 |
| A5~A7 후 | 222 | 1 | 9 | 1 | 동일(리소스 5종 경로 모두 존재, `MODERN_QSS`/`build_shell_qss('gold')` 생성 확인) |
| A8~A10 후 | 222 | 1 | 9 | 1 | 동일 |
| A11 후(최종) | 222 | 1 | 9 | 1 | 동일 |

최종 목록(기준선과 동일): 모듈 로드 에러 6(`test_brand_icons`=Pillow, `test_open_doc_picker`/`test_posid_branding`/`test_themes`/`test_viewer_shell`/`test_workspace_features`=pytest 미설치), `HFCompareWidget` 임시파일 권한 에러 3, 실패 1(`test_focus_mode_round_trip_and_close_tool_action`, ✕ 툴팁 문구).

### 추가 검증 (환경 변경 없음)
- pytest·Pillow를 **가상환경이 아닌** `%TEMP%\pdfc_audit\extra`에 설치하고 `PYTHONPATH`로 지정해 실행. 로드되지 않던 6개 모듈 **37개 전부 통과**.
- 같은 방식 전체 스위트: **254 passed, 1 skipped, 4 failed** — 4건은 위 기존 실패(`HFCompareWidget` 3 + 툴팁 1)와 동일. 신규 실패 없음.
- 전체 `app.*` 모듈 import 스모크(`pkgutil.walk_packages`, 오프스크린): 실패 0. `compileall app configs main.py build.py`: 성공. 미사용 import 재스캔: 남은 항목 없음(`annotations` 오탐 제외).

## 5. EXE / MSIX 빌드 결과

- **Portable EXE: 미검증.** `.venv`에 PyInstaller가 설치되어 있지 않아 `python build.py`를 실행하지 못했다(환경 변경은 하지 않음). 또한 `build.py`는 추적 파일 `app/common/build_version.txt`를 덮어쓰고 `make_icons.py`가 `assets`를 재생성하므로, 승인 없이 작업 트리에서 실행하지 않았다.
- **MSIX: 미검증.** 저장소에 AppxManifest/패키징 스크립트가 없고 `makeappx`도 확인되지 않음. MSIX 리소스(`assets/posid/msix/*`)는 변경하지 않았다.
- 빌드 영향 분석(정적): `build.py`의 hidden-import는 `app/tools/*.py` glob이므로 삭제된 3개 파일은 자동 제외. 동적 import 대상 6개 모듈은 import 성공 확인. 삭제 코드 중 PyInstaller `--add-data`/`--splash`/`--icon`가 쓰는 리소스는 없다.
- **GUI 수동 확인(CHECKLIST §5, 12항목): 미검증.** 자동 테스트는 오프스크린 Qt만 사용했다.

## 6. 작업 전후 변경 규모

`git diff HEAD --shortstat -- app tests configs scripts build.py`: **25 files changed, 30 insertions(+), 906 deletions(-)**

- 삭제 파일 3개(-581), 수정 22개 파일(+30 / -325). 순감 876줄.
- `tests/`, `configs/`, `scripts/`, `build.py`, `assets/`: 변경 0.
- 신규 문서: `docs/CODE_CLEANUP_AUDIT.md`, `PLAN.md`, `CHECKLIST.md`, `RESULT.md`. (`git add -N docs`로 intent-to-add 상태이며 커밋은 하지 않았다.)
- 파일 줄바꿈(CRLF)은 모두 보존.

## 7. 향후 검토가 필요한 사항

1. **빌드 검증**: PyInstaller 설치 승인 후 `python build.py --target posid` + 실행 확인. 빌드 전 `git status`로 `build_version.txt` 변경 처리 방침 결정.
2. **테스트 환경**: `requirements.txt`에 개발용 의존성(pytest, Pillow) 부재 → 5개 모듈 + `test_brand_icons`가 기본 환경에서 로드되지 않음. `make_icons.py`/`build.py`도 Pillow 필요(`check=False`로 조용히 실패).
3. **기존 실패 1건**: 테스트 기대값 "현재 도구 닫기 …" vs 현재 "현재 화면 닫기 …"(이전 변경). 테스트 또는 문구 중 어느 쪽을 맞출지 결정 필요.
4. **`HFCompareWidget` 3건**: Windows 임시 PDF 삭제 권한 문제(테스트 정리 순서). 정리와 무관.
5. **nuni 아이콘 불일치**: 설정은 `nuni_icon.ico`, 실제 파일은 `assets/nuni/nuni_ico.ico`.
6. **B 항목 재검토**: qamate 타겟 유지 여부, posid 아이콘 6개의 MSIX 패키징 사용 여부(저장소 밖 도구 확인), 구독자 없는 Signal 3개, 발표모드/스마트 인쇄 완료 후 미사용 헬퍼 재조사.
6-1. `resources._candidate_paths`의 `legacy_aliases['posid_logo.ico']`는 `get_resource_path` 삭제로 더 이상 어떤 호출도 도달하지 못하지만 B6으로 유지(수정하지 않음).
7. **README 오래됨**: posid 앱 이름·테마색, 작업 패널 설명, 프로젝트 구조(viewer/shell/presentation/print_engine 미반영).

## 8. Opus 최종 검토용 근거

- 변경 확인: `git diff HEAD -- app` (코드), `git diff HEAD --stat`.
- 삭제 심볼 잔여 참조 0 확인 검색어: `pdf_split|pdf_merge|pdf_page_editor|LoadingDialog|LoadingManager|get_resource_path|SHELL_QSS|_full_pdf|leaf_name|hide_search|flash_search_highlight|show_legend_dialog|show_caution_dialog|add_hl` (→ `app/`, `tests/` 0건; `toggle_work_mode` 등은 유지).
- 유지 확인: `show_legend_caution_dialog`가 `pdf_compare.py`, `pdf_header_footer_compare.py`, `main_window.py`에 남아 있음. `pdf_header_footer_compare.py`의 `SyncScrollToggle  # noqa: F401 (re-export)` 줄 유지.
- 분석·실행용 스크립트(저장소 밖): `%TEMP%\pdfc_audit\{dead_scan,signal_scan,ownfile_scan,unused_imports,cutlib,run_a*}.py`, 테스트 로그 `t3~t6.txt`, `pytest_all.txt`.
- 실행 중 이슈: A11 적용 스크립트가 다중 행/상대 import에서 두 번 안전하게 중단됨(어설션). 중단 전 적용된 파일은 diff로 확인했고, 해당 구문(`overlay.py`, `split_view.py`)은 정확한 문자열 치환으로 처리, 상대 import는 수준(`.`)을 반영하도록 스크립트를 고쳐 재실행. 최종 재스캔에서 누락·과삭제 없음.
