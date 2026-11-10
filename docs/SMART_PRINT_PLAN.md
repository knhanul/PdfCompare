# 계획
1. 분석/설계(Opus) ✔
2. 엔진: units/model/source → split → A3 fit → 2-up → build_pdf
3. UI: smart_print 위젯, 저장, QPrintDialog
4. 동시보기 정렬 설계 (Opus 설계안 §4 기반, 필요 시 재검토)
5. 동시보기 구현
6. Opus 최종 리뷰 → 수정

# 오피스형 확장 계획 (Opus 아키텍처 검토 반영, 2026-11-10)
검토: general-purpose(model=opus) — pdf-print-expert 미등록 대체.
## 결정
- 인쇄를 모달 QDialog → mode_stack의 SmartPrintPage(QWidget)로 전환. 복귀는 (prev 위젯, header, nav 키, 사이드바 상태)를 저장해 setCurrentWidget(prev)만 호출. open_split_view()를 복귀에 쓰지 않음(피커 재호출 방지). 진입 시 _hide_current_tool 호출 금지, _active_view_key에 'print' 추가, close_current_tool/activate_view에 release() 연결.
- Esc: QShortcut(WidgetWithChildrenShortcut). Ctrl+P는 숨겨진 페이지 단축키가 동작 안 하므로 충돌 없음.
- 문서 수명: 진입 시 항상 bytes 스냅샷(디스크 재오픈으로 인한 불일치 방지). release()에서 SourceDoc 정리.
- 엔진: 입력을 Cell(source_id,page,clip,w,h)로 일반화. N-split은 (cols,rows) 격자+겹침, N-up은 약수쌍 탐색+order(Z/N/rtl)+scale_policy, 소책자/교차/앞뒤는 Cell 순서 문제. pagespec.py 순수 파서, PrintSettings(frozen)를 캐시 키로 사용.
- 영역 좌표: '보이는 좌표'(page_sizes 기준) 사용. 회전 90/270+clip, CropBox 오프셋 테스트 필수.
- bake 실패는 조용히 삼키지 않고 UI 경고. 미리보기/출력은 워커 스레드+세대 번호 취소(후반).
## 구현 순서
1 pagespec+Cell → 2 N-split → 3 N-up/용지 → 4 영역/여백 → 5 소책자/교차/앞뒤 → 6 긴 페이지 → 7 SmartPrintPage 전환 → 8 비동기 → 9 프리셋/최종 리뷰
(순서 조정 가능: 사용자 체감이 큰 7단계를 앞당기는 것도 가능)
