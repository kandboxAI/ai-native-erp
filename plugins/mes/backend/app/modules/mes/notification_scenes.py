"""制造异常通知；默认仅站内信，内容不携带业务自由文本。"""
SCENES=[]
for key,name in (("assigned","异常待处理"),("review","异常待复核"),("closed","异常已关闭"),("overdue","异常超时提醒")):
    SCENES.append(dict(scene_key=f"mes.exception.{key}",scene_name=name,module_code="mes",severity_code="important",
        description="制造异常责任处理和复核提醒",templates={"in_app":{"title_template":name+"：{case_no}","content_template":"异常单 {case_no}，处理期限 {due_at}。请进入异常处理查看并办理。"}},
        routes=[{"target_type_code":"actor","actor_key":actor,"org_scope_code":"event_organization"} for actor in ("owner","reporter")]
            + ([{"target_type_code":"permission","permission_key":"mes:exception:review","org_scope_code":"event_organization"}] if key == "review" else [])))
