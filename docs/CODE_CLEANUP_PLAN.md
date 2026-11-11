# Posid PDF — 소스 정리 실행 계획 (PLAN)

- 근거 문서: `docs/CODE_CLEANUP_AUDIT.md` (항목 ID A1~A11, B1~B9, C)
- 검증 목록: `docs/CODE_CLEANUP_CHECKLIST.md`
- 대상: **위험도 A 항목만**. B·C 항목은 건드리지 않는다.

## 0. 공통 규칙

1. 시작 전 `git status -s`가 비어 있는지 확인. 비어 있지 않으면 중단하고 사용자에게 보고.
2. `git reset`, `git clean`, `git rebase`, `git push`, `git checkout -- <file>` 금지. 되돌릴 때는 해당 단계의 파일만 수동으로 복원하거나 사용자에게 문의.
3. 라인 번호는 기준 커밋(`ad1835e`) 기준. **심볼 이름으로 위치를 찾아** 편집하고, 한 파일에서 여러 곳을 지울 때는 아래쪽부터 지운다.
4. 주석·docstring은 해당 심볼에 속한 것만 함께 지운다. 다른 주석은 건드리지 않는다.
5. 각 단계 후 CHECKLIST §2(단계별 검증)를 실행하고, 기준선보다 결과가 나빠지면 그 단계를 되돌리고 중단.
6. 단계마다 별도 커밋(사용자가 커밋을 원할 때만). 커밋 메시지 예: `chore(cleanup): A1 remove legacy split/merge/page tools`.
7. AUDIT에 없는 항목을 "추가로 발견했다"는 이유로 삭제하지 않는다. 발견하면 보고만 한다.

## 1단계 — A1: 과거 도구 파일 삭제

- 삭제: `app/tools/pdf_split.py`, `app/tools/pdf_merge.py`, `app/tools/pdf_page_editor.py` (`git rm` 사용 가능)
- `build.py`는 수정하지 않는다(glob이 자동 반영).
- 검증: CHECKLIST §2-A1

## 2단계 — A2: `app/common/loading_dialog.py`

1. `class LoadingManager:` 블록 전체(파일 끝까지) 삭제.
2. `class LoadingDialog(QDialog):` 블록 전체 삭제(다음 최상위 정의 직전까지).
3. import를 다음과 같이 정리:
   ```python
   from PyQt6.QtCore import QEventLoop
   from PyQt6.QtWidgets import QProgressBar, QApplication
   from app.common.styles import COLOR_PRIMARY
   ```
   (`import os`, `Qt`, `QMovie`, `QDialog`, `QVBoxLayout`, `QLabel`, `get_timer_gif_path` 제거)
4. `_progress_qss`, `make_overlay_progress`, `update_overlay_progress`, `style_task_progress`, `note_progress`는 그대로 둔다.
- 검증: CHECKLIST §2-A2

## 3단계 — A3·A4: 비교 도구 미사용 메서드

`app/tools/pdf_compare.py` (아래쪽부터):
1. `PdfCompareWidget.add_hl`
2. `PdfCompareWidget.show_caution_dialog`
3. `PdfCompareWidget.show_legend_dialog`
4. `PDFViewer.remove_flash_highlight`
5. `PDFViewer.flash_search_highlight`
6. `SelectableLabel._clamp_to_image`

`app/tools/pdf_header_footer_compare.py`:
7. `HFCompareWidget._add_hl`

- `show_legend_caution_dialog`는 절대 삭제하지 않는다(`main_window`가 문자열로 호출).
- 삭제 후 CHECKLIST §3 스캔으로 `QDialog`/`QTimer` 등 연쇄 미사용 import가 생겼는지 확인하고, 생겼으면 그 이름만 제거.
- 검증: CHECKLIST §2-A3

## 4단계 — A5·A6·A7: 리소스/스타일/테마

1. `app/common/resources.py`: `def get_resource_path(...)` 함수만 삭제. `_candidate_paths`/`legacy_aliases`는 수정 금지.
2. `app/common/styles.py`: 상수 10개 삭제 — `COLOR_SECONDARY`, `COLOR_SIDEBAR_BG`, `COLOR_MDI_BG`, `COLOR_BORDER_LIGHT`, `COLOR_HOVER`, `_IOS_GREEN`, `_IOS_ORANGE`, `_IOS_ORANGE_HOVER`, `_IOS_ORANGE_PRESSED`, `_IOS_RED`. 그 외 상수는 유지.
3. `app/shell/theme.py`: 마지막 줄 `SHELL_QSS = build_shell_qss()  # compatibility for existing imports` 삭제.
- 검증: CHECKLIST §2-A5~A7

## 5단계 — A8·A9·A10: 셸/인쇄/폼 미사용 메서드

1. `app/shell/viewer_workspace.py`: `def hide_search(self)`, `def work_mode(self)` 삭제.
2. `app/shell/print_dialog.py`: `def _full_pdf(self)` 삭제. 위의 `# ── 출력 ──` 주석은 남긴다. `build_pdf` import는 다른 사용처가 있으면 유지.
3. `app/common/pdf_form/field_models.py`: `leaf_name` property(데코레이터 포함) 삭제.
- 검증: CHECKLIST §2-A8~A10

## 6단계 — A11: 미사용 import

- AUDIT §4 A11 표의 이름만 제거. 한 import 문에 다른 이름이 남으면 그 이름들은 유지.
- 제외: `from __future__ import annotations`, `# noqa`가 붙은 줄(특히 `SyncScrollToggle` re-export), `__init__.py` 재수출.
- `pdf_compare_worker.py`의 `Any`는 문자열 타입 주석에서 쓰이지 않는지 확인 후 제거.
- 3단계에서 연쇄로 생긴 미사용 import도 여기서 함께 정리(CHECKLIST §3 결과 기준).
- 검증: CHECKLIST §2-A11, 이후 §4 최종 검증.

## 7단계 — 문서 동기화 (선택, 사용자 승인 시)

- 이번 정리로 사라진 항목을 언급하는 문서가 있는지만 확인(`README.md`, `Claude.md`). 현재 README는 삭제 대상 파일을 언급하지 않으므로 기본적으로 수정 불필요.
- AUDIT §7의 README 오래된 정보는 정리 범위 밖 → 수정하지 말고 보고.

---

## Sonnet 실행 지시문

아래를 그대로 Sonnet에게 전달한다.

```
너는 Posid PDF(PyQt6/PyMuPDF, Windows) 저장소 E:\Pjt\PdfCompare에서 소스 정리를 실행한다.
판단은 이미 끝났다. 새로 판단하지 말고 문서대로만 실행하라.

읽을 문서(이 순서로):
1) docs/CODE_CLEANUP_AUDIT.md  — 삭제 대상(A)과 금지 대상(B, C)
2) docs/CODE_CLEANUP_PLAN.md   — 실행 순서(1~6단계)
3) docs/CODE_CLEANUP_CHECKLIST.md — 단계별/최종 검증

규칙:
- 위험도 A 항목만 삭제한다. B와 C는 어떤 이유로도 수정·삭제하지 않는다.
- AUDIT에 없는 코드는 지우지 않는다. 새로 발견한 미사용 코드는 목록으로 보고만 한다.
- 라인 번호 대신 심볼 이름으로 위치를 찾는다. 한 파일 안에서는 아래쪽부터 지운다.
- 관련 없는 주석·포맷·로직은 바꾸지 않는다. 리팩터링, 이름 변경, 코드 이동 금지.
- git reset/clean/rebase/push/checkout -- 금지. 커밋은 사용자가 요청할 때만 단계별로 한다.
- 시작 전 git status -s가 비어 있지 않으면 멈추고 보고한다.
- 각 단계 후 CHECKLIST §2의 해당 검증을 실행한다. 테스트 결과가 기준선
  (222 tests / failures=1 / errors=9 / skipped=1, 실패·에러 목록은 CHECKLIST §1)보다 나빠지면
  그 단계 변경만 되돌리고 멈춘 뒤 원인을 보고한다.
- 테스트 출력은 마지막 30줄 정도로 줄여서 본다(PowerShell: | Select-Object -Last 30).
- pytest/Pillow 설치 등 환경 변경은 사용자 승인 없이 하지 않는다.

완료 보고 형식:
- 단계별 삭제한 파일/심볼 목록과 줄 수
- 최종 테스트 결과(기준선 대비)
- CHECKLIST §5 수동 확인 항목 중 수행/미수행
- 실행 중 발견했지만 손대지 않은 항목
```
