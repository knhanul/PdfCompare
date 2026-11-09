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
