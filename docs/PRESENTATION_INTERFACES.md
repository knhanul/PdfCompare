# 발표모드 인터페이스

```
ViewerWorkspace.start_presentation(from_start) / SplitView.start_presentation(from_start)
   └ context_from_canvas / context_from_split  → PresentationContext(panes[PaneSource], sync, screen, view_mode)
        └ PresentationWindow(context).start()
             ├ PresentationCanvas × 1|2   (app/presentation/canvas.py, PdfCanvas 서브클래스)
             ├ navigation.py              (순수 계산: next_target/prev_target/page_scroll/max_zoom_for/recommend_view/split_stretch)
             └ overlay.py                 (FloatingToolbar, Toast, PageBadge, Curtain)
```
- 좌표: 캔버스 위치 = 페이지 + 페이지 높이 대비 비율(뷰포트 가운데 기준, 확대율 무관). 동기화는 `scroll_anchor.map_position` 재사용.
- 렌더링: 기존 `render_service()`(스레드별 문서 핸들, LRU 캐시, devicePixelRatio 반영) 그대로 사용. 배율 상한은 `max_zoom_for(page_sizes, dpr)`.
- 설정(QSettings): `presentation/ratio_pct`, `presentation/animate`, `presentation/auto_speed`.
- 확장 지점(발표자 화면): PresentationContext + navigation 을 공유하는 별도 PresenterWindow 를 추가하고, PresentationWindow 는 관객용으로 유지. 발표 시간/다음 페이지 미리보기는 canvas.current_page() 와 RenderService 로 구현 가능.
