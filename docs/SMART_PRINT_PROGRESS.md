# 진행 상황
- [x] 1단계 설계: pdf-print-expert 는 세션 미로드 → general-purpose(model=opus)로 대체 위임. 결과 반영.
- [x] 2단계 엔진 (units/model/source/layouts/render/verify): tests/test_print_engine_core.py 9개 통과 (PDF 생성 테스트만, 실제 프린터 미검증)
  - 확정: extra_rotate 양수 = 시계방향 (show_pdf_page rotate는 반시계이므로 place에서 부호 반전)
  - 회전(0/90/180/270)·cropbox 원본의 분할 출력 토큰 누락 없음 확인
  - A4→A3 배율은 규격비 297/210(≈1.41429), √2 아님
- [x] 3단계 UI: app/tools/smart_print.py(탭), app/common/print_output.py(QPrintDialog), main_window에 smart_print 등록. 오프스크린 스모크 테스트 통과(tests/test_smart_print_widget.py). 실제 프린터 출력은 미검증.
- [x] 4단계: Opus 설계안 §4(연속 스트림)를 그대로 채택(별도 재검토 생략, 6단계 리뷰에 포함)
- [x] 5단계: app/print_engine/stream.py + app/tools/smart_print_side.py. tests/test_print_engine_stream.py 5개 통과 (기준선 정렬 ±0.1pt, 미세조정 mm 이동, 200회 랜덤 커버리지 틈 없음, 토큰 누락 없음, 미리보기=출력)
  - 의미: adjust_mm 는 해당 변의 상대 이동. 두 변의 상대 정렬이 의미. 음수는 위쪽 잘림 방지를 위해 baseline이 같이 이동(양쪽 -5 = 0), 양수는 양쪽 모두 실제로 아래로 이동
- 전체 회귀: 89 tests, 기존 HFCompareWidget 오류 3건(Windows 임시파일 권한)은 본 작업 이전부터 동일 발생
- [ ] 6단계 Opus 최종 리뷰 (진행 중)
- [x] UX 개편: 사이드바 '스마트 인쇄' 메뉴 제거, 공통 대화상자 app/shell/print_dialog.py (미리보기 65%/설정 35%/하단 취소·PDF 저장·인쇄).
  PDF 보기(툴바 🖨 인쇄, Ctrl+P)와 두 PDF 동시보기(툴바 🖨 인쇄, Ctrl+P)에서 열린 문서를 그대로 전달. 엔진/정렬 엔진 재사용. tests/test_print_dialog.py
- [x] 시작 위치 정렬 UX 분리: app/shell/alignment_dialog.py(AlignmentDialog: 입력/시각화 전용, 좌표=엔진 '보이는 좌표 pt'), print_dialog는 요약+'시작 위치 조정...'만 표시.
  1mm 버튼은 시작 기준선(start_y)을 mm→pt로 이동(Shift=5mm). 좌우 미리보기 배율 동일(기본 '맞춤'). tests/test_alignment_dialog.py
- [x] 정리: 사용하지 않는 옛 탭 UI(app/tools/smart_print.py, smart_print_side.py)와 tests/test_smart_print_widget.py 삭제. 위 3·5단계의 해당 파일 언급은 이력이며, 현재 UI는 app/shell/print_dialog.py + alignment_dialog.py.
- [x] (2026-11-10) 오피스형 확장 Phase 1: 분석 + Opus 아키텍처 검토 → PLAN.md 반영. 구현 1단계: app/print_engine/pagespec.py (parse/parse_multi) + tests/test_print_pagespec.py. print 관련 25 tests OK. 아직 UI 미연결.
  - 미완료: Cell 모델, N-split/N-up, 영역/여백, 소책자, 교차/앞뒤, SmartPrintPage 전환, 비동기, 프리셋. 실제 프린터 출력 미검증.
- [x] (2026-11-10) 구현 2~3단계(엔진): layouts.plan_grid_split(cols×rows+겹침, build_plan 'split'), plan_n_up 일반화(n=2~16, order Z/N/*_rtl, border/numbers, 혼합크기 종횡비 유지, meta.min_scale), units에 B4/B5/A5(JIS). tests/test_print_engine_grid.py 13개 + 기존 엔진 테스트 통과(합 28). UI 미연결. 실제 프린터 미검증.
- [x] (2026-11-10) Phase 2 일부: SmartPrintDialog를 QWidget 페이지(별칭 SmartPrintPage)로 전환. MainWindow.show_print_page/_leave_print_page/_drop_print_page(mode_stack, 이전 위젯 보존 복귀, 다른 화면 이동 시 release). 상단 '← PDF 보기로/두 PDF 동시보기로 돌아가기', Esc, 페이지 내 Ctrl+P=인쇄. 진입 시 항상 bytes 스냅샷. tests/test_print_page_transition.py 3개(뷰어 왕복, 동시보기 좌우 문서·스크롤 위치 보존, 이동 시 release).
- [x] 설정 패널 연결: 확대분할 2/4/6/9, 모아찍기 2/4/6/8/9/16(순서·간격·경계선·번호), 용지 A4/A3/B4, 페이지 조합 입력(오류 표시), 16-up 가독성 안내. test_print_dialog 확장.
- 전체 회귀: 142 tests, 실패/오류 10건은 변경 전(stash 비교 121 tests)에도 동일 → 신규 실패 없음. 
- [ ] 미완료: 영역 지정, 여백 자동 감지, 소책자, 긴 페이지 분할, 교차/앞뒤 출력, 시작 위치 탭(미리보기 통합), 프리셋, 비동기 렌더/취소, 미리보기 확대/썸네일, 사이드바 접기, 하드웨어 여백 반영, 예상 매수(양면). 실제 프린터 출력 미검증. Opus 최종 코드 리뷰 미실시.
- [x] (2026-11-10) Phase 4/5 엔진+UI: layouts.plan_booklet/booklet_order(왼/오른쪽 제본, 4의 배수 패딩, duplex=short), plan_long_split(겹침, 누락 없음), plan_region(fit/original/scale, 용지 초과 시 오류), trim.detect_content_box(렌더 기반, 회전 반영, 비파괴 클리핑), pairs.py(교차 interleave tail append/stop, 앞뒤 front_back 빈 면 삽입, duplex=long).
  UI: 모드 영역 지정(미리보기 드래그→pt 변환, 초기화), 여백 제거(자동 감지+상하좌우 mm 보정), 소책자, 긴 페이지 분할, 대상 '교차 출력/앞뒤 비교 출력'(시작 페이지는 정렬 값 사용), 예상 매수(단면/양면).
  테스트: test_print_engine_advanced.py 18개, test_print_dialog 확장(드래그 좌표, 영역 필수, 여백 보정, 교차/앞뒤). 전체 163 tests, 실패 10건은 기존과 동일.
  주의/미검증: 소책자 급지 방향·양면 실제 출력, 프린터 하드웨어 여백, 배경색 문서 자동 여백 오탐(보정 UI로 대응), 영역 선택은 단일 영역을 선택 페이지 전체에 적용.
- [ ] 남음: 시작 위치 맞춤 탭(미리보기 통합), 프리셋, 비동기 렌더/취소, 확대/썸네일/장별 이동 보강, 사이드바 접기, 하드웨어 여백, Opus 최종 코드 리뷰, 빌드(MSIX/Portable) 검증.
- [x] (2026-11-10) Phase 6 일부: app/services/print_presets.py(내장 7종+사용자 정의, 문서별 값 제외) + 인쇄 페이지 프리셋 콤보/저장/삭제, 비호환 항목은 건너뛰고 안내. 미리보기 −/+/너비 맞춤/전체 맞춤 + 시트 캐시(계획 변경 시 무효화). PDF 저장/인쇄용 생성은 _BuildWorker(QThread)로 비동기(스냅샷 bytes로 자체 SourceDoc, 중복 요청 무시, release 시 안전 종료).
  tests/test_print_presets.py 3개, test_print_dialog 확장(줌/캐시, 비동기 출력, 생성 중 release). 전체 169 tests, 실패 10건은 기존과 동일.
- [ ] 남음: 시작 위치 맞춤 탭, 썸네일 탐색, 사이드바 접기, 하드웨어 여백, 미리보기 렌더 비동기(현재는 현재 시트 동기), Opus 코드 리뷰 반영(진행 중), 빌드(MSIX/Portable) 검증.
- [x] (2026-11-10) Opus 코드 리뷰 반영(11건): ①closeEvent에서 인쇄 페이지/워커 정리(+wait_orphan_workers) ②release 시 실행 중 워커는 분리·보관(UI 무정지, 부모 파괴 방지) ③생성 중 설정·미리보기 잠금(PyMuPDF 스레드 동시 사용 방지) ④분할 라벨 ASCII화(Helvetica 한글 깨짐) ⑤출력은 화면에 표시된 self._plan 사용(대기 중 변경 먼저 확정) ⑥release 후 늦은 콜백 무시 ⑦독립 창 참조 유지+DeleteOnClose ⑧영역이 페이지 크기를 벗어나면 '{n}페이지:' 오류 ⑨프리셋이 기존 안내문을 지우지 않음 ⑩재진입 시 원래 복귀 대상 유지 ⑪긴 페이지 scale 너비 초과 방지/빈 꼬리 장 방지, bake 실패 시 주석 누락 경고.
  전체 회귀 확인: 아래 최종 보고 참조.
- [x] (2026-11-10) 시작 위치 맞춤 탭: AlignmentDialog(QDialog 팝업) → AlignmentView(QWidget, applied/cancelled 신호)로 전환, 인쇄 페이지 미리보기 상단 탭 [인쇄 미리보기 | 시작 위치 맞춤](두 PDF일 때만 표시, 나란히/교차/앞뒤 대상에서만 활성). 정렬 적용→미리보기 탭 복귀+즉시 반영, 변경 취소/Esc→취소, 탭만 전환하면 미적용 편집 보관. 뷰어 캔버스/스크롤 동기화에는 접근하지 않음(독립 문서 사본). 생성 중 탭 잠금.
  버그 수정: release 직후 지연된 _relayout이 닫힌 문서를 접근해 슬롯 예외→앱 중단(테스트로 발견) → 가드 추가.
  tests/test_alignment_dialog.py 12개(흐름 5 + UI 4 + 탭 3). 
- [x] (2026-11-10) 마무리 3종:
  ① 썸네일 탐색(좌측 QListWidget, 현재 장 기준 거리순 지연 렌더, 클릭=장 이동, '썸네일' 토글) + 사이드바 접기(인쇄 진입 시 아이콘형 compact, 모든 이탈 경로에서 원래 사용자 설정 복원; 복귀 시 캔버스 스크롤 위치를 배율 독립 좌표로 재적용).
  ② 프린터 인쇄 불가 영역: print_output.available_printers/min_margin_mm/supports_paper. 프린터 선택+'인쇄 불가 영역 반영' 시 유효 여백=max(사용자 여백, 프린터 최소 여백) 을 엔진 배치/미리보기/PDF 저장이 동일하게 사용. 미지원 용지(A3/B4 등) 경고. 기본 프린터는 자동 조회하지 않음(이 환경에서 QPrinter(QPrinterInfo) 생성 시 COM 오류 0x80040155 관찰 → 사용자가 선택·반영을 켠 경우에만 조회). 하드웨어 여백은 방향 무관 네 변 최댓값(보수적).
  ③ 미리보기 비동기: _PreviewRenderer(QThread, 자체 SourceDoc 재사용) + 세대 번호로 오래된 요청/결과 폐기, PYMUPDF_LOCK으로 이 모듈의 PyMuPDF 사용 직렬화(렌더/출력 생성/영역 선택/여백 감지), 렌더 중 해제 시 스레드 분리·보관.
  tests: 전체 183 tests, 실패/오류 10건은 변경 전부터 동일(HFCompare 3, 브랜딩/테마/뷰어셸 등 import 오류 6, 포커스 모드 1).
## 최종 미검증/미완 항목
- 실제 프린터 물리 출력(소책자 급지 방향, 양면, 인쇄 불가 영역 실측), min_margin_mm 의 실제 드라이버 값
- 빌드(MSIX/Portable) 검증 미실시, 100페이지+ 대용량 성능 실측 미실시(렌더는 비동기이나 SourceDoc bake는 첫 요청 시 렌더 스레드에서 수행)
- 영역 지정은 단일 영역을 선택 페이지 전체에 적용 / 향후 전체비교 연동은 stream.py·pairs.py·pagespec.py 인터페이스 유지만 했고 차이점 출력은 미구현(범위 외)
