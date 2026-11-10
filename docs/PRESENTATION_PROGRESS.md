# 발표모드 진행 기록

## 구현 (신규/변경)
- 신규: `app/presentation/{navigation,canvas,context,overlay,window}.py`, `tests/test_presentation.py`, `docs/PRESENTATION_*.md`
- 변경: `app/viewer/pdf_canvas.py`(margin/page_gap/bg_color/probe_ratio 인스턴스화, `_emit_scrolled` 훅), `scroll_anchor.py`, `split_view.py`, `shell/viewer_workspace.py`, `main_window.py`(헤더 버튼·팔레트), `services/app_settings.py`

## Subagent
- Opus 서브에이전트(general-purpose, model=opus; `pdf-print-expert` 역할 프롬프트) 1회 호출: 핵심 코드 리뷰.
- 반영: (1) 렌더 상한 16MP로 낮추고 하한 1.0 제거(캐시 스래싱), (2) 구간 이동 누락(페이지 위쪽 미노출/짧은 페이지 어긋남), (3) 자동 스크롤 위치 재동기, (4) 모니터 시그널 중복 연결·showNormal→이동→전체화면, 배율 상한 재적용, (5) 일반 동기화 재개 시 현재 위치 기준 연결, (6) zoom_at 실제 스크롤 위치 기준.
- 미반영: set_zoom(keep_fit=True) 무동작(낮음, 발표 캔버스 내부 호출 없음), scroll_anchor.capture_pos의 page 모드 간격(발표 창은 미사용), 보이는 영역만 타일 렌더링(장기 과제), 오래된 렌더 요청 취소(RenderService 미지원).

## 테스트
- `tests/test_presentation.py` 21건 통과(구간 이동 수학, 폭 맞춤, 가운데 정렬, 줌 지점 고정, 검은 화면, 형광펜 좌표, 120쪽 이동, 동기화/기준점/보류, 집중·전환, 독립 확대).
- 전체 스위트: 기존 실패(pytest 미설치 import 6건, HFCompareWidget 3건, 닫기 툴팁 문구 1건)는 변경 전부터 존재.
- 오프스크린 캡처로 한쪽 집중 + 구간 이동 + 형광펜 렌더링 육안 확인.

## 미검증
실제 다중 모니터/프로젝터, 125·150% 배율, 2560×1440 실기, 장시간 대용량 메모리, 비교·편집·폼·생성·인쇄 UI 수동 회귀(자동 테스트 범위 외).
