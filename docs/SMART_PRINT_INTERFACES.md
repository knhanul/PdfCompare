# 확정 인터페이스 (설계 오류 확인 전 변경 금지)
패키지 app/print_engine/: units, model, source, layouts, render, verify, (stream: 4~5단계)
- units: PT_PER_MM, mm(v), paper(name, landscape)->(w,h)
- model: Box(x0,y0,x1,y1; w,h), PageInfo(index,width,height,rotation), Placement(source_id,page,clip,dst,extra_rotate),
  Mark(kind,p0,p1,text), Sheet(width,height,placements,marks), PrintPlan(sheets,meta), Margins
- source.SourceDoc(path_or_bytes, source_id, bake=False): page_info(i), infos(), place(out_page, Placement), close()
- layouts: plan_tile_split(info, sheet, tiles, margins, overlap_mm, marks, src_id)->list[Sheet];
  plan_fit_to_paper(info, sheet, margins, allow_rotate, src_id)->Sheet;
  plan_n_up(infos, sheet, n, margins, gutter_mm, auto_rotate, src_id)->list[Sheet];
  build_plan(mode, infos, **opts)->PrintPlan  (mode: split2 | fit | nup)
- render.build_pdf(plan, sources, sheet_indices=None)->bytes
- verify.coverage(plan)->{(source_id,page): [(y0,y1)...]}
- stream(4단계): StreamSide/StreamLayout/Segment/build_segments/plan_side_by_side/src_to_out/out_to_src
