# 스마트 인쇄 명세
## 기능 A
1. A4 1페이지 → 확대 → A4 2장 분할 (긴 축 분할, 이음 겹침, 이음선 표시)
2. A4 1페이지 → A3 1장 확대 (여백 0일 때 √2)
3. A4 2페이지 → A4/A3 1장 2-up
4. 모든 모드 미리보기 (build_pdf 결과 bytes를 래스터화; 출력과 동일 경로)
5. PDF 저장, OS 표준 인쇄(QPrintDialog)
## 기능 B (동시보기 시작 위치 조정)
좌/우 PDF 독립 시작 페이지 + 시작 y(마우스 지정), 기준선 동일 높이 정렬, 1mm 미세조정,
페이지 경계를 넘는 연속 스트림 출력(누락 없음), 미리보기=출력.
## 제약
엔진은 PyQt 비의존(app/print_engine), 원본 보존(항상 새 문서 출력), 벡터 유지(show_pdf_page), 오프라인.
이번 단계는 자동 텍스트 매칭/전체비교 변경 없음.
## 핵심 사실 (Opus 검증)
- 회전된 원본: 작업 사본에서 rot/derotation_matrix 저장 → set_rotation(0) → clip*D → show_pdf_page(rotate=-rot).
- 원본/대상 동일 문서 불가, 주석·위젯은 show_pdf_page에 그려지지 않음(bake 옵션 미검증).
- paper_size는 반올림 → mm→pt 직접 정의.
