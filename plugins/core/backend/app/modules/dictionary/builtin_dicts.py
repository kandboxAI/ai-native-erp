"""Core dictionaries plus definitions and values registered by selected modules."""
import json
from pathlib import Path
from app.framework.catalog import iter_module_attr

CORE_DICTS = json.loads(Path(__file__).with_name("core_dicts.json").read_text(encoding="utf-8"))

BUILTIN_DICTS: list[dict] = [
    {'dict_code': 'sys_org_type', 'dict_name': '组织类型', 'scope': 'global', 'items': [('group', '集团'), ('school', '学校'), ('campus', '校区')]},
    {'dict_code': 'sys_data_scope', 'dict_name': '数据范围', 'scope': 'global', 'items': [('all', '全部'), ('organization', '本组织'), ('department', '本部门'), ('self', '本人'), ('related', '关联关系（如班主任与本班学生、家长与子女）')]},
    {'dict_code': 'sys_org_access_mode', 'dict_name': '组织访问方式', 'scope': 'global', 'items': [('primary_only', '仅主组织'), ('assigned', '授权的组织'), ('all', '全部组织')]},
    {'dict_code': 'sys_user_org_access_type', 'dict_name': '组织授权类型', 'scope': 'global', 'items': [('primary', '主组织'), ('assigned', '额外授权')]},
    {'dict_code': 'sys_menu_type', 'dict_name': '菜单类型', 'scope': 'global', 'items': [('directory', '目录'), ('menu', '菜单'), ('button', '按钮')]},
    {'dict_code': 'sys_open_target', 'dict_name': '打开方式', 'scope': 'global', 'items': [('self', '当前页'), ('blank', '新窗口'), ('iframe', '内嵌')]},
    {'dict_code': 'sys_miniapp_portal', 'dict_name': '小程序门户', 'scope': 'global', 'items': [('student', '学生'), ('parent', '家长'), ('teacher', '教师'), ('staff', '科室'), ('principal', '校长')]},
    {'dict_code': 'sys_module', 'dict_name': '系统模块', 'scope': 'global', 'items': [('system', '系统管理'), ('education', '教务'), ('student_affairs', '学生事务'), ('admission', '招生'), ('ar', '应收计费'), ('hr', '人事'), ('inventory', '物资'), ('canteen', '食堂后勤'), ('logistics', '后勤管理'), ('workflow', '审批'), ('notify', '通知')]},
    {'dict_code': 'sys_setting_group', 'dict_name': '参数分组', 'scope': 'global', 'items': [('security', '安全'), ('notify', '通知'), ('education', '教务'), ('ar', '应收计费'), ('hr', '人事'), ('inventory', '物资'), ('ai', '智能体')]},
    {'dict_code': 'sys_value_type', 'dict_name': '参数值类型', 'scope': 'global', 'items': [('string', '文本'), ('number', '数值'), ('boolean', '是否'), ('json', '结构化')]},
    {'dict_code': 'md_party_type', 'dict_name': '主体类型', 'scope': 'global', 'items': [('person', '自然人'), ('organization', '机构')]},
    {'dict_code': 'md_gender', 'dict_name': '性别', 'scope': 'global', 'items': [('male', '男'), ('female', '女'), ('unknown', '未说明')]},
    {'dict_code': 'md_identity_type', 'dict_name': '证件类型', 'scope': 'global', 'items': [('id_card', '居民身份证'), ('passport', '护照'), ('hk_macao_pass', '港澳居民来往内地通行证'), ('taiwan_pass', '台湾居民来往大陆通行证'), ('residence_permit', '外国人永久居留身份证')]},
    {'dict_code': 'md_contact_type', 'dict_name': '联系方式类型', 'scope': 'global', 'items': [('mobile', '手机'), ('phone', '固定电话'), ('email', '邮箱'), ('wechat', '微信'), ('home_address', '家庭住址'), ('household_address', '户籍地址')]},
    {'dict_code': 'md_contact_purpose', 'dict_name': '联系方式用途', 'scope': 'global', 'items': [('notify', '接收通知'), ('emergency', '紧急联系'), ('general', '一般联系')]},
    {'dict_code': 'md_organization_type', 'dict_name': '外部机构类型', 'scope': 'global', 'items': [('school', '学校'), ('enterprise', '企业'), ('government', '政府机关'), ('other', '其他')]},
    {'dict_code': 'md_unit', 'dict_name': '计量单位', 'scope': 'global', 'items': [('piece', '件'), ('box', '箱'), ('pack', '包'), ('set', '套'), ('ream', '令'), ('bottle', '瓶'), ('kg', '千克'), ('meter', '米')]},
    {'dict_code': 'md_currency', 'dict_name': '币种', 'scope': 'global', 'items': [('CNY', '人民币')]},
    {'dict_code': 'md_settlement_method', 'dict_name': '结算方式', 'scope': 'tenant', 'items': [('bank_transfer', '银行转账'), ('cash', '现金'), ('online', '线上支付')]},
    {'dict_code': 'md_settlement_cycle', 'dict_name': '结算周期', 'scope': 'tenant', 'items': [('per_order', '按单'), ('monthly', '月结'), ('quarterly', '季结')]},
    {'dict_code': 'edu_slot_type', 'dict_name': '节次类型', 'scope': 'tenant', 'items': [('class', '上课'), ('self_study', '自习'), ('break', '课间'), ('activity', '活动')]},
    {'dict_code': 'edu_room_type', 'dict_name': '场地类型', 'scope': 'tenant', 'items': [('classroom', '普通教室'), ('computer_lab', '机房'), ('training_room', '实训室'), ('playground', '操场'), ('hall', '礼堂')]},
    {'dict_code': 'edu_course_type', 'dict_name': '课程类型', 'scope': 'tenant', 'items': [('professional', '专业课'), ('public', '公共基础课'), ('activity', '活动课'), ('self_study', '自习')]},
    {'dict_code': 'edu_study_mode', 'dict_name': '学习形式', 'scope': 'tenant', 'items': [('full_time', '全日制'), ('part_time', '非全日制'), ('enterprise', '校企合作')]},
    {'dict_code': 'edu_student_status', 'dict_name': '学生在校状态', 'scope': 'global', 'items': [('enrolled', '在校'), ('suspended', '休学'), ('left', '已离校'), ('graduated', '已毕业')]},
    {'dict_code': 'edu_registration_status', 'dict_name': '学籍状态', 'scope': 'global', 'items': [('enrolled', '在籍'), ('suspended', '休学'), ('transferred_out', '转出'), ('withdrawn', '退学'), ('graduated', '毕业')]},
    {'dict_code': 'edu_registration_change_type', 'dict_name': '学籍异动类型', 'scope': 'global', 'items': [('suspend', '休学'), ('resume', '复学'), ('transfer_class', '转班'), ('transfer_major', '转专业'), ('transfer_out', '转出'), ('transfer_in', '转入'), ('withdraw', '退学'), ('graduate', '毕业')]},
    {'dict_code': 'edu_class_type', 'dict_name': '班级类型', 'scope': 'tenant', 'items': [('administrative', '行政班'), ('teaching', '教学班')]},
    {'dict_code': 'edu_class_member_role', 'dict_name': '班级成员角色', 'scope': 'tenant', 'items': [('student', '学生'), ('monitor', '班长'), ('league_secretary', '团支书'), ('committee', '班委')]},
    {'dict_code': 'edu_teacher_type', 'dict_name': '教师类型', 'scope': 'tenant', 'items': [('full_time', '专任'), ('part_time', '兼职'), ('enterprise', '企业导师'), ('external', '外聘')]},
    {'dict_code': 'edu_teacher_capability', 'dict_name': '课程能力', 'scope': 'tenant', 'items': [('primary', '主讲'), ('qualified', '可讲'), ('substitute', '可代课')]},
    {'dict_code': 'edu_teacher_role', 'dict_name': '任课角色', 'scope': 'tenant', 'items': [('lead', '主讲'), ('assistant', '协助')]},
    {'dict_code': 'edu_delivery_mode', 'dict_name': '授课方式', 'scope': 'tenant', 'items': [('offline', '线下'), ('online', '线上'), ('online_joint', '线上联班')]},
    {'dict_code': 'edu_offering_target_scope', 'dict_name': '授课对象范围', 'scope': 'global', 'items': [('whole_class', '整班'), ('major_group', '专业方向组')]},
    {'dict_code': 'edu_offering_status', 'dict_name': '开课计划状态', 'scope': 'global', 'items': [('draft', '草稿'), ('ready', '已确认'), ('disabled', '已停用')]},
    {'dict_code': 'edu_curriculum_status', 'dict_name': '培养方案状态', 'scope': 'global', 'items': [('draft', '草稿'), ('published', '已发布'), ('disabled', '已停用')]},
    {'dict_code': 'edu_curriculum_course_nature', 'dict_name': '培养方案课程性质', 'scope': 'tenant', 'items': [('required', '必修'), ('limited_elective', '限选'), ('elective', '选修')]},
    {'dict_code': 'edu_teaching_plan_status', 'dict_name': '学期教学计划状态', 'scope': 'global', 'items': [('draft', '草稿'), ('confirmed', '已确认'), ('archived', '已归档')]},
    {'dict_code': 'edu_plan_task_status', 'dict_name': '教学任务状态', 'scope': 'global', 'items': [('planned', '待生成开课'), ('converted', '已生成开课'), ('cancelled', '已取消')]},
    # 教师坐班（需求 10 / 批次 P1-3）：规则、门禁点位、打卡事件、日汇总、离岗预警
    {'dict_code': 'edu_duty_point_type', 'dict_name': '门禁点位类型', 'scope': 'tenant', 'items': [('gate', '校门'), ('dorm', '宿舍'), ('teaching', '教学楼'), ('other', '其他')]},
    {'dict_code': 'edu_duty_access_direction', 'dict_name': '打卡进出方向', 'scope': 'global', 'items': [('enter', '进入'), ('leave', '离开')]},
    {'dict_code': 'edu_duty_access_method', 'dict_name': '打卡识别方式', 'scope': 'tenant', 'items': [('face', '刷脸'), ('fingerprint', '指纹'), ('card', '刷卡'), ('manual', '手工')]},
    {'dict_code': 'edu_duty_access_result', 'dict_name': '打卡识别结果', 'scope': 'global', 'items': [('success', '成功'), ('fail', '失败')]},
    {'dict_code': 'edu_duty_access_source', 'dict_name': '打卡数据来源', 'scope': 'global', 'items': [('manual', '手工录入'), ('import', '批量导入'), ('device', '设备同步')]},
    {'dict_code': 'edu_duty_status', 'dict_name': '坐班结果', 'scope': 'global', 'items': [('on_duty', '在岗'), ('left', '离岗'), ('late', '迟到'), ('absent', '未到岗'), ('early_leave', '早退'), ('exempt', '有效例外'), ('finished', '已结束')]},
    {'dict_code': 'edu_duty_exception_type', 'dict_name': '坐班有效例外', 'scope': 'tenant', 'items': [('normal_teaching', '正常上课'), ('leave', '已请假'), ('business_trip', '出差'), ('official_out', '公务外出')]},
    {'dict_code': 'edu_duty_warning_type', 'dict_name': '离岗预警类型', 'scope': 'global', 'items': [('late', '迟到'), ('absent', '未到岗'), ('temporary_leave', '中途离岗'), ('early_leave', '早退')]},
    {'dict_code': 'edu_duty_warning_severity', 'dict_name': '离岗预警程度', 'scope': 'global', 'items': [('normal', '一般'), ('major', '重要')]},
    {'dict_code': 'edu_duty_warning_status', 'dict_name': '离岗预警处置状态', 'scope': 'global', 'items': [('pending', '待核实'), ('handled', '已处置')]},
    # 教学质量评估（需求 16 / 批次 P2-1）：任务状态、周期、指标分组与取数来源、等级
    {'dict_code': 'edu_quality_period_type', 'dict_name': '质量评估周期类型', 'scope': 'global', 'items': [('semester', '学期'), ('academic_year', '学年')]},
    {'dict_code': 'edu_quality_task_status', 'dict_name': '质量评估任务状态', 'scope': 'global', 'items': [('draft', '草稿'), ('aggregating', '聚合中'), ('pending', '待发布'), ('published', '已发布'), ('archived', '已归档')]},
    {'dict_code': 'edu_quality_metric_group', 'dict_name': '质量评估指标分组', 'scope': 'global', 'items': [('quality', '教学质量指标'), ('performance', '绩效辅助指标')]},
    {'dict_code': 'edu_quality_metric_source', 'dict_name': '质量评估取数来源', 'scope': 'global', 'items': [('lesson_evaluation', '听评课管理'), ('survey', '授课满意度调查'), ('lesson_plan', '教案检查'), ('exam', '考试成绩管理'), ('homework', '作业收集与抽检'), ('duty', '教师坐班'), ('employment', '就业升学统计'), ('manual', '教务人工评分'), ('derived', '派生计算')]},
    {'dict_code': 'edu_quality_level', 'dict_name': '质量评估等级', 'scope': 'global', 'items': [('A', 'A 优秀'), ('B', 'B 良好'), ('C', 'C 合格'), ('D', 'D 待改进'), ('E', 'E 不合格')]},
    # 教师画像（需求 2 / 批次 P2-2）：维度分组、取数来源、对教师可见范围、状态、成长任务
    {'dict_code': 'edu_portrait_dimension_group', 'dict_name': '画像维度分组', 'scope': 'global', 'items': [('ability', '能力维度'), ('structure', '结构维度')]},
    {'dict_code': 'edu_portrait_metric_source', 'dict_name': '画像指标取数来源', 'scope': 'global', 'items': [('lesson_evaluation', '听评课管理'), ('survey', '授课满意度调查'), ('lesson_plan', '教案检查'), ('exam', '考试成绩管理'), ('homework', '作业收集与抽检'), ('duty', '教师坐班'), ('employment', '就业升学统计'), ('quality', '教学质量评估结果'), ('profile', '教师档案与任职'), ('manual', '教务人工录入'), ('derived', '派生计算')]},
    {'dict_code': 'edu_portrait_visibility', 'dict_name': '画像对教师可见范围', 'scope': 'global', 'items': [('full', '完整画像（含考核打分）'), ('scoreless', '不含考核打分'), ('hidden', '不向教师展示')]},
    {'dict_code': 'edu_portrait_status', 'dict_name': '画像状态', 'scope': 'global', 'items': [('draft', '草稿'), ('published', '已发布'), ('archived', '已归档')]},
    {'dict_code': 'edu_portrait_growth_source', 'dict_name': '成长任务来源', 'scope': 'global', 'items': [('auto', '系统生成'), ('manual', '教务录入'), ('teacher', '教师自建')]},
    {'dict_code': 'edu_portrait_growth_status', 'dict_name': '成长任务状态', 'scope': 'global', 'items': [('pending', '待开始'), ('doing', '进行中'), ('done', '已完成'), ('closed', '已关闭')]},
    # 实训室管理（需求 18 / 批次 P2-3）：实训室开放状态、设备类型/状态/分配、使用类型/状态、故障对象/类型/紧急度/状态
    {'dict_code': 'edu_lab_open_status', 'dict_name': '实训室开放状态', 'scope': 'tenant', 'items': [('open', '开放使用'), ('maintenance', '维护中'), ('closed', '停止开放')]},
    {'dict_code': 'edu_lab_device_type', 'dict_name': '实训室设备类型', 'scope': 'tenant', 'items': [('computer', '计算机'), ('projector', '投影设备'), ('network', '网络设备'), ('printer', '打印设备'), ('other', '其他')]},
    {'dict_code': 'edu_lab_device_status', 'dict_name': '实训室设备状态', 'scope': 'global', 'items': [('available', '可用'), ('fault_pending', '故障待处理'), ('repairing', '维修中'), ('waiting_parts', '待配件'), ('disabled', '停用'), ('scrapped', '报废')]},
    {'dict_code': 'edu_lab_device_allocation', 'dict_name': '实训室设备分配状态', 'scope': 'tenant', 'items': [('assigned', '已分配'), ('unassigned', '待分配')]},
    {'dict_code': 'edu_lab_usage_type', 'dict_name': '实训室使用类型', 'scope': 'tenant', 'items': [('fixed', '固定教学'), ('temporary', '临时使用')]},
    {'dict_code': 'edu_lab_usage_status', 'dict_name': '实训室使用状态', 'scope': 'global', 'items': [('planned', '已排期'), ('active', '使用中'), ('finished', '已完成'), ('cancelled', '已取消')]},
    {'dict_code': 'edu_lab_fault_target', 'dict_name': '实训室报障对象', 'scope': 'tenant', 'items': [('device', '单台机器'), ('facility', '公共设备')]},
    {'dict_code': 'edu_lab_fault_type', 'dict_name': '实训室故障类型', 'scope': 'tenant', 'items': [('hardware', '硬件故障'), ('software', '软件故障'), ('network', '网络故障'), ('power', '供电故障'), ('facility', '场地设施'), ('other', '其他')]},
    {'dict_code': 'edu_lab_fault_urgency', 'dict_name': '实训室故障紧急程度', 'scope': 'tenant', 'items': [('low', '一般'), ('normal', '较急'), ('urgent', '紧急')]},
    {'dict_code': 'edu_lab_fault_status', 'dict_name': '实训室故障状态', 'scope': 'global', 'items': [('reported', '待受理'), ('accepted', '已受理'), ('repairing', '维修中'), ('waiting_parts', '待配件'), ('completed', '已完成'), ('cancelled', '已取消')]},
    {'dict_code': 'edu_schedule_plan_status', 'dict_name': '课表方案状态', 'scope': 'global', 'items': [('draft', '草稿'), ('published', '已发布'), ('archived', '已归档')]},
    {'dict_code': 'edu_schedule_entry_source', 'dict_name': '课表条目来源', 'scope': 'global', 'items': [('manual', '手工'), ('automatic', '自动排课'), ('adjustment', '调整'), ('import', '导入')]},
    {'dict_code': 'edu_week_pattern', 'dict_name': '周次规则', 'scope': 'global', 'items': [('every', '每周'), ('odd', '单周'), ('even', '双周')]},
    {'dict_code': 'edu_scheduling_rule_type', 'dict_name': '排课规则类型', 'scope': 'global', 'items': [('hard', '硬约束'), ('soft', '软约束')]},
    {'dict_code': 'edu_schedule_change_type', 'dict_name': '调代课类型', 'scope': 'global', 'items': [('swap', '调课'), ('substitute', '代课'), ('self_study', '改自习')]},
    {'dict_code': 'edu_schedule_change_status', 'dict_name': '调代课状态', 'scope': 'global', 'items': [('draft', '草稿'), ('pending_counterpart', '待对方确认'), ('pending_approval', '待审批'), ('approved', '已通过'), ('rejected', '已驳回'), ('withdrawn', '已撤回')]},
    # 需求 84 后半段 / B-1：教师薪酬与工资核算
    {'dict_code': 'hr_pay_cycle', 'dict_name': '薪酬发放周期', 'scope': 'global', 'items': [('monthly', '月薪（按月发放）')]},
    {'dict_code': 'hr_deduct_exception', 'dict_name': '扣款考勤异常类型', 'scope': 'global', 'items': [('absent', '缺勤'), ('forget_punch', '忘打卡'), ('late', '迟到'), ('early_leave', '早退'), ('personal_leave', '事假'), ('sick_leave', '病假')]},
    {'dict_code': 'hr_deduct_mode', 'dict_name': '扣款方式', 'scope': 'global', 'items': [('none', '不扣款'), ('fixed', '固定金额'), ('per_day', '按天扣'), ('per_period', '按课时扣')]},
    {'dict_code': 'hr_payroll_sheet_status', 'dict_name': '工资核算单状态', 'scope': 'global', 'items': [('draft', '草稿'), ('calculated', '已核算'), ('submitted', '待审批'), ('approved', '已通过'), ('rejected', '已驳回'), ('voided', '已作废')]},
    # 需求 4：教师请假（不复用学生请假 edu_leave_type —— 主体与审批流都不同）
    {'dict_code': 'edu_teacher_leave_type', 'dict_name': '教师请假类型', 'scope': 'tenant', 'items': [('sick', '病假'), ('personal', '事假'), ('annual', '年假'), ('marriage', '婚假'), ('bereavement', '丧假'), ('maternity', '产假'), ('official', '公假/出差'), ('other', '其他')]},
    {'dict_code': 'edu_teacher_leave_status', 'dict_name': '教师请假状态', 'scope': 'global', 'items': [('draft', '草稿'), ('submitted', '待审批'), ('approved', '已批准'), ('rejected', '已驳回'), ('withdrawn', '已撤回')]},
    {'dict_code': 'edu_teacher_leave_arrange', 'dict_name': '请假课次处置方式', 'scope': 'global', 'items': [('pending', '待安排'), ('substitute', '已指定代课'), ('self_study', '改自习'), ('cancel', '取消本节')]},
    {'dict_code': 'edu_attendance_session_type', 'dict_name': '点名类型', 'scope': 'tenant', 'items': [('class', '课堂'), ('morning_reading', '早读'), ('evening_study', '晚自习'), ('activity', '活动'), ('dormitory', '宿舍')]},
    {'dict_code': 'edu_attendance_status', 'dict_name': '考勤结果', 'scope': 'global', 'items': [('present', '出勤'), ('late', '迟到'), ('early_leave', '早退'), ('absent', '缺勤'), ('on_leave', '请假')]},
    {'dict_code': 'edu_leave_type', 'dict_name': '请假类型', 'scope': 'tenant', 'items': [('sick_leave', '病假'), ('personal_leave', '事假'), ('public_leave', '公假'), ('other', '其他')]},
    {'dict_code': 'edu_leave_status', 'dict_name': '请假状态', 'scope': 'global', 'items': [('draft', '草稿'), ('submitted', '待审批'), ('approved', '已批准'), ('rejected', '已驳回'), ('cancelled', '已撤销'), ('returned', '已销假')]},
    {'dict_code': 'edu_leave_applicant_type', 'dict_name': '请假申请人类型', 'scope': 'global', 'items': [('student', '学生本人'), ('parent', '家长'), ('homeroom', '班主任代填')]},
    {'dict_code': 'edu_exam_type', 'dict_name': '考试类型', 'scope': 'tenant', 'items': [('midterm', '期中'), ('final', '期末'), ('monthly', '月考'), ('makeup', '补考'), ('quiz', '随堂测验')]},
    {'dict_code': 'edu_exam_scope', 'dict_name': '考试范围', 'scope': 'global', 'items': [('school', '全校'), ('grade', '年级'), ('class', '班级')]},
    {'dict_code': 'edu_score_sheet_status', 'dict_name': '成绩单状态', 'scope': 'global', 'items': [('draft', '草稿'), ('pending_review', '待审核'), ('published', '已发布'), ('returned', '已退回'), ('withdrawn', '已撤回')]},
    {'dict_code': 'edu_score_sheet_source', 'dict_name': '成绩来源', 'scope': 'global', 'items': [('manual', '手工录入'), ('import', '导入'), ('exam_schedule', '排考自动生成')]},
    # 需求 3 / B-3：排考场次状态（考试按一节课排入课表 → 生成成绩单 → 开考 → 结束）
    {'dict_code': 'edu_exam_session_status', 'dict_name': '排考场次状态', 'scope': 'global', 'items': [('draft', '草稿'), ('scheduled', '已排定'), ('in_progress', '进行中'), ('closed', '已结束'), ('cancelled', '已取消')]},
    {'dict_code': 'edu_score_level', 'dict_name': '成绩等级', 'scope': 'tenant', 'items': [('excellent', '优秀'), ('good', '良好'), ('pass', '及格'), ('fail', '不及格')]},
    # 需求 6：成绩分项类型。取「卷面（理论 + 实操）/ 平时表现（课堂表现）」两大类，
    # 再细分便于教师直接选用；分项名称允许教师自定义，此处只是常用预设。
    {'dict_code': 'edu_score_item_type', 'dict_name': '成绩分项类型', 'scope': 'tenant', 'items': [('paper', '卷面'), ('theory', '理论'), ('practical', '实操'), ('class_performance', '课堂表现'), ('homework', '平时作业'), ('skill', '技能考核'), ('work', '作品评分'), ('other', '其他')]},
    {'dict_code': 'edu_guardian_relation', 'dict_name': '监护关系', 'scope': 'global', 'items': [('father', '父亲'), ('mother', '母亲'), ('grandparent', '祖父母或外祖父母'), ('other_relative', '其他亲属'), ('other', '其他')]},
    {'dict_code': 'edu_evaluation_type', 'dict_name': '听评课类型', 'scope': 'tenant', 'items': [('academic_supervision', '教学督导'), ('leadership', '领导听课'), ('peer', '同行互评')]},
    {'dict_code': 'edu_evaluation_task_status', 'dict_name': '听评课任务状态', 'scope': 'global', 'items': [('draft', '草稿'), ('pending_evaluation', '待评课'), ('evaluating', '评课中'), ('pending_review', '待审核'), ('approved', '已通过'), ('returned', '已退回'), ('voided', '已作废')]},
    {'dict_code': 'edu_evaluation_assignment_status', 'dict_name': '评课记录状态', 'scope': 'global', 'items': [('pending_evaluation', '待评课'), ('evaluating', '评课中'), ('pending_review', '待审核'), ('approved', '已通过'), ('returned', '已退回'), ('voided', '已作废')]},
    {'dict_code': 'edu_survey_status', 'dict_name': '调查状态', 'scope': 'global', 'items': [('draft', '草稿'), ('published', '进行中'), ('closed', '已结束'), ('cancelled', '已取消')]},
    {'dict_code': 'edu_survey_identity_mode', 'dict_name': '提交方式', 'scope': 'global', 'items': [('real_name', '实名'), ('anonymous', '匿名')]},
    {'dict_code': 'edu_satisfaction_rating', 'dict_name': '满意度', 'scope': 'global', 'items': [('very_satisfied', '非常满意'), ('satisfied', '满意'), ('dissatisfied', '不满意'), ('very_dissatisfied', '非常不满意')]},
    {'dict_code': 'edu_student_work_status', 'dict_name': '学生作品状态', 'scope': 'global', 'items': [('pending', '待评分'), ('scored', '已评分'), ('published', '已发布')]},
    {'dict_code': 'edu_student_work_material_type', 'dict_name': '学生作品资料类型', 'scope': 'global', 'items': [('image', '图片'), ('video', '视频'), ('sheet', '表格'), ('document', '文档')]},
    {'dict_code': 'edu_offboarding_status', 'dict_name': '离职交接总体状态', 'scope': 'global', 'items': [('pending', '待交接'), ('handing_over', '交接中'), ('awaiting_receipt', '待接收'), ('completed', '已完成')]},
    {'dict_code': 'edu_offboarding_procedure_status', 'dict_name': '离职手续状态', 'scope': 'global', 'items': [('pending', '待办理'), ('done', '已完成')]},
    {'dict_code': 'edu_offboarding_item_status', 'dict_name': '交接数据状态', 'scope': 'global', 'items': [('pending', '待移交'), ('awaiting', '待接收'), ('received', '已接收')]},
    {'dict_code': 'edu_offboarding_asset_status', 'dict_name': '交接资产状态', 'scope': 'global', 'items': [('pending', '待处理'), ('awaiting', '待接收'), ('received', '已接收'), ('returned', '已归还')]},
    {'dict_code': 'edu_offboarding_asset_disposition', 'dict_name': '交接资产处理方式', 'scope': 'global', 'items': [('transfer', '移交接任教师'), ('return', '归还学校')]},
    {'dict_code': 'edu_offboarding_apply_type', 'dict_name': '离职类型', 'scope': 'global', 'items': [('resign', '离职'), ('transfer', '调离'), ('retire', '退休')]},
    {'dict_code': 'edu_inspection_type', 'dict_name': '迎检类型', 'scope': 'global', 'items': [('opening', '开学检查'), ('annual', '年度检查'), ('special', '专项检查'), ('quality', '教学质量检查')]},
    {'dict_code': 'edu_inspection_task_status', 'dict_name': '迎检任务状态', 'scope': 'global', 'items': [('pending_generate', '待生成'), ('generating', '生成中'), ('pending_confirm', '待确认'), ('confirmed', '已确认'), ('archived', '已归档')]},
    {'dict_code': 'edu_inspection_material_source', 'dict_name': '迎检材料来源', 'scope': 'global', 'items': [('uploaded', '人工上传'), ('ai', 'AI 生成'), ('system', '系统生成')]},
    {'dict_code': 'edu_inspection_material_status', 'dict_name': '迎检材料状态', 'scope': 'global', 'items': [('existing', '已有'), ('generated', '已生成'), ('missing', '缺失'), ('confirmed', '已确认')]},
    {'dict_code': 'edu_employment_destination_type', 'dict_name': '毕业去向', 'scope': 'global', 'items': [('employed', '就业'), ('further_study', '升学'), ('flexible', '灵活就业'), ('entrepreneurship', '自主创业'), ('unemployed', '待业'), ('not_seeking', '暂不就业')]},
    {'dict_code': 'edu_employment_material_status', 'dict_name': '就业材料状态', 'scope': 'global', 'items': [('none', '未提交'), ('submitted', '待审核'), ('approved', '已通过'), ('rejected', '已驳回')]},
    {'dict_code': 'edu_employment_confirm_status', 'dict_name': '去向确认状态', 'scope': 'global', 'items': [('pending', '待确认'), ('confirmed', '已确认')]},
    {'dict_code': 'edu_employment_followup_type', 'dict_name': '就业跟进方式', 'scope': 'global', 'items': [('superior_check', '上级核查'), ('phone_follow_up', '电话回访'), ('onsite_follow_up', '实地回访')]},
    {'dict_code': 'edu_employment_followup_status', 'dict_name': '就业跟进状态', 'scope': 'global', 'items': [('pending_visit', '待回访'), ('rectifying', '整改中'), ('corrected', '已整改'), ('verified', '已核实')]},
    {'dict_code': 'edu_adm_residence_type', 'dict_name': '招生意向住宿类型', 'scope': 'global', 'items': [('boarding', '寄宿'), ('day', '走读')]},
    {'dict_code': 'edu_adm_category', 'dict_name': '招生类别', 'scope': 'global', 'items': [('unified', '统招生'), ('independent', '单招生')]},
    {'dict_code': 'edu_lesson_plan_task_status', 'dict_name': '教案检查任务状态', 'scope': 'global', 'items': [('draft', '草稿'), ('published', '进行中'), ('closed', '已结束')]},
    {'dict_code': 'edu_lesson_plan_requirement_status', 'dict_name': '应交教案状态', 'scope': 'global', 'items': [('pending', '待提交'), ('submitted', '已提交'), ('rejected', '未通过')]},
    {'dict_code': 'edu_homework_task_status', 'dict_name': '作业收集任务状态', 'scope': 'global', 'items': [('published', '收集中'), ('closed', '已截止')]},
    {'dict_code': 'edu_homework_recipient_status', 'dict_name': '学生作业任务状态', 'scope': 'global', 'items': [('pending', '未提交'), ('submitted', '已提交'), ('reviewed', '已批阅')]},
    {'dict_code': 'edu_homework_score_level', 'dict_name': '作业评价等级', 'scope': 'tenant', 'items': [('excellent', '优秀'), ('good', '良好'), ('pass', '合格'), ('revise', '需订正')]},
    {'dict_code': 'edu_homeroom_ledger_type', 'dict_name': '班主任考核账本类型', 'scope': 'global', 'items': [('quant', '班级量化'), ('routine', '常规工作')]},
    {'dict_code': 'edu_homeroom_record_source', 'dict_name': '班主任考核登记来源', 'scope': 'global', 'items': [('pc', '管理端'), ('mobile', '小程序')]},
    {'dict_code': 'edu_homeroom_category', 'dict_name': '班主任类别', 'scope': 'tenant', 'items': [('unassigned', '未设置'), ('full_time_first', '专职班主任（首班）'), ('part_time', '兼职班主任')]},
    {'dict_code': 'edu_homeroom_performance_level', 'dict_name': '班主任绩效档次', 'scope': 'global', 'items': [('A', 'A档'), ('B', 'B档'), ('C', 'C档')]},
    {'dict_code': 'asset_device_category', 'dict_name': '设备资产类别', 'scope': 'tenant', 'items': [('teaching', '教学设备'), ('office', '办公设备'), ('it', '信息化设备'), ('utilities', '水电设施'), ('furniture', '门窗家具'), ('security', '消防安防'), ('other', '其他')]},
    {'dict_code': 'asset_disposal_status', 'dict_name': '设备报废处置状态', 'scope': 'global', 'items': [('pending_disposal', '待处置'), ('disposed', '已处置'), ('voided', '已作废')]},
    {'dict_code': 'asset_disposal_method', 'dict_name': '设备报废处置方式', 'scope': 'tenant', 'items': [('recycle', '回收'), ('destroy', '销毁'), ('transfer', '移交'), ('other', '其他')]},
    {'dict_code': 'asset_type', 'dict_name': '资产类型', 'scope': 'tenant', 'items': [('furniture', '家具'), ('equipment', '设备'), ('instrument', '器材'), ('dormitory_facility', '宿舍设施'), ('teaching_equipment', '教学设备'), ('it_equipment', '信息化设备'), ('other', '其他')]},
    {'dict_code': 'asset_status', 'dict_name': '资产状态', 'scope': 'global', 'items': [('in_use', '在用'), ('idle', '闲置'), ('maintenance', '维修中'), ('disposed', '已报废')]},
    {'dict_code': 'asset_location_type', 'dict_name': '资产位置类型', 'scope': 'tenant', 'items': [('campus', '校区'), ('building', '楼栋'), ('floor', '楼层'), ('room', '房间'), ('training_room', '实训室'), ('dormitory', '宿舍'), ('office', '办公室'), ('warehouse', '仓库'), ('public_area', '公共区域'), ('other', '其他')]},
    {'dict_code': 'asset_change_event_type', 'dict_name': '资产变更类型', 'scope': 'global', 'items': [('created', '建档'), ('updated', '信息修改'), ('quantity_adjusted', '数量调整'), ('transfer_out', '调拨出'), ('transfer_in', '调拨入'), ('handover', '责任移交'), ('transfer', '位置调拨'), ('status_changed', '状态变更')]},
    {'dict_code': 'asset_change_source_type', 'dict_name': '资产变更来源类型', 'scope': 'global', 'items': [('manual', '人工操作'), ('repair_order', '维修工单'), ('asset_disposal', '报废处置')]},
    {'dict_code': 'adm_campaign_status', 'dict_name': '招生计划状态', 'scope': 'global', 'items': [('draft', '草稿'), ('active', '进行中'), ('closed', '已结束')]},
    {'dict_code': 'adm_channel', 'dict_name': '招生渠道', 'scope': 'tenant', 'items': [('school_visit', '进校宣讲'), ('referral', '老生推荐'), ('online', '网络咨询'), ('open_day', '开放日'), ('agent', '合作机构'), ('walk_in', '自行到访')]},
    {'dict_code': 'adm_lead_status', 'dict_name': '线索状态', 'scope': 'global', 'items': [('new', '新线索'), ('contacted', '已联系'), ('visited', '已到校'), ('applied', '已报名'), ('offered', '已录取'), ('enrolled', '已报到'), ('lost', '流失')]},
    {'dict_code': 'adm_follow_up_type', 'dict_name': '跟进方式', 'scope': 'tenant', 'items': [('phone', '电话'), ('visit', '到校参观'), ('home_visit', '家访'), ('message', '微信或短信')]},
    {'dict_code': 'adm_application_status', 'dict_name': '报名状态', 'scope': 'global', 'items': [('submitted', '已报名'), ('reviewing', '审核中'), ('approved', '审核通过'), ('rejected', '未通过'), ('cancelled', '已取消')]},
    {'dict_code': 'adm_offer_status', 'dict_name': '录取状态', 'scope': 'global', 'items': [('offered', '已录取'), ('enrolled', '已报到'), ('declined', '放弃')]},
    # 文件与附件（L1 file_）
    {'dict_code': 'file_kind', 'dict_name': '文件类别', 'scope': 'global', 'items': [('image', '图片'), ('document', '文档'), ('video', '视频'), ('other', '其他')]},
    {'dict_code': 'file_attachment_status', 'dict_name': '附件状态', 'scope': 'global', 'items': [('uploading', '上传中'), ('pending', '待绑定'), ('bound', '已绑定')]},
    # 人力资源（L2 hr_）与部门岗位（L1 sys_position）
    {'dict_code': 'hr_employee_type', 'dict_name': '员工类型', 'scope': 'tenant', 'items': [('regular', '正式'), ('contract', '合同制'), ('part_time', '兼职'), ('intern', '实习'), ('dispatched', '劳务派遣'), ('rehired', '返聘')]},
    {'dict_code': 'hr_employment_status', 'dict_name': '在职状态', 'scope': 'tenant', 'items': [('probation', '试用'), ('active', '在职'), ('suspended', '停薪留职'), ('resigned', '离职'), ('retired', '退休')]},
    {'dict_code': 'hr_leave_reason', 'dict_name': '离职原因', 'scope': 'tenant', 'items': [('resignation', '辞职'), ('dismissal', '辞退'), ('contract_end', '合同到期'), ('retirement', '退休'), ('other', '其他')]},
    {'dict_code': 'hr_education_level', 'dict_name': '学历', 'scope': 'global', 'items': [('high_school', '高中及以下'), ('junior_college', '大专'), ('bachelor', '本科'), ('master', '硕士'), ('doctor', '博士')]},
    {'dict_code': 'hr_title_series', 'dict_name': '职称系列', 'scope': 'tenant', 'items': [('economics', '经济'), ('accounting', '会计'), ('engineering', '工程')]},
    {'dict_code': 'hr_title_level', 'dict_name': '职称等级', 'scope': 'global', 'items': [('none', '无'), ('staff', '员级'), ('assistant', '助理级'), ('intermediate', '中级'), ('associate_senior', '副高级'), ('senior', '正高级')]},
    {'dict_code': 'hr_assignment_change_reason', 'dict_name': '任职变动原因', 'scope': 'global', 'items': [('hire', '入职'), ('transfer', '调动'), ('promotion', '晋升'), ('concurrent', '兼任'), ('removal', '免职'), ('leave', '离职')]},
    # 应收与计费（L2 ar_）：只内置行业无关的取值；行业取值由模块 catalog.py 的 DICT_ITEMS 登记（如教育的学费、学期）
    {'dict_code': 'ar_account_type', 'dict_name': '收费账户类型', 'scope': 'tenant', 'items': [('general', '普通账户')]},
    {'dict_code': 'ar_account_status', 'dict_name': '收费账户状态', 'scope': 'global', 'items': [('active', '正常'), ('suspended', '冻结'), ('closed', '已销户')]},
    {'dict_code': 'ar_fee_item_type', 'dict_name': '收费项目类型', 'scope': 'tenant', 'items': [('deposit', '押金'), ('other', '其他')]},
    {'dict_code': 'ar_price_model', 'dict_name': '计价方式', 'scope': 'global', 'items': [('flat', '固定金额'), ('per_unit', '单价乘数量'), ('tiered', '阶梯价')]},
    {'dict_code': 'ar_billing_cycle', 'dict_name': '计费周期', 'scope': 'tenant', 'items': [('once', '一次性'), ('month', '月'), ('quarter', '季'), ('year', '年')]},
    {'dict_code': 'ar_charge_status', 'dict_name': '计费明细状态', 'scope': 'global', 'items': [('pending', '待出账'), ('billed', '已出账'), ('cancelled', '已取消')]},
    {'dict_code': 'ar_source_type', 'dict_name': '计费来源类型', 'scope': 'tenant', 'items': [('manual', '手工计费')]},
    {'dict_code': 'ar_payment_term', 'dict_name': '付款条件', 'scope': 'tenant', 'items': [('immediate', '即付')]},
    {'dict_code': 'ar_bill_status', 'dict_name': '账单状态', 'scope': 'global', 'items': [('draft', '草稿'), ('unpaid', '未缴'), ('partially_paid', '部分缴纳'), ('paid', '已缴清'), ('waived', '已免除'), ('refunded', '已退费'), ('voided', '已作废')]},
    {'dict_code': 'ar_adjustment_type', 'dict_name': '账单调整类型', 'scope': 'tenant', 'items': [('waiver', '减免'), ('discount', '折扣'), ('correction', '更正'), ('write_off', '坏账核销')]},
    {'dict_code': 'ar_pay_method', 'dict_name': '缴费方式', 'scope': 'tenant', 'items': [('wechat', '微信'), ('alipay', '支付宝'), ('bank_transfer', '银行转账'), ('cash', '现金'), ('pos', '刷卡')]},
    {'dict_code': 'ar_payment_status', 'dict_name': '收款状态', 'scope': 'global', 'items': [('pending', '待确认'), ('succeeded', '已到账'), ('failed', '失败'), ('voided', '已作废')]},
    {'dict_code': 'ar_refund_status', 'dict_name': '退费状态', 'scope': 'global', 'items': [('pending_approval', '待审批'), ('approved', '已批准'), ('refunded', '已退款'), ('rejected', '已驳回')]},
    {'dict_code': 'ar_approval_status', 'dict_name': '审批状态', 'scope': 'global', 'items': [('pending_approval', '待审批'), ('approved', '已批准'), ('rejected', '已驳回')]},
    {'dict_code': 'inv_stock_status', 'dict_name': '库存状态', 'scope': 'global', 'items': [('available', '可用'), ('lent', '借出'), ('quarantine', '待检'), ('blocked', '冻结'), ('defective', '不合格')]},
    {'dict_code': 'inv_stock_direction', 'dict_name': '库存方向', 'scope': 'global', 'items': [('in', '入库'), ('out', '出库'), ('move', '移位'), ('status', '状态转换'), ('adjust', '调整')]},
    {'dict_code': 'inv_stock_order_status', 'dict_name': '库存单据状态', 'scope': 'global', 'items': [('draft', '草稿'), ('submitted', '待审批'), ('approved', '已审批'), ('confirmed', '已确认'), ('voided', '已作废')]},
    {'dict_code': 'inv_material_requisition_status', 'dict_name': '物资领用申请状态', 'scope': 'global', 'items': [('submitted', '待审批'), ('approved', '待发放'), ('rejected', '已驳回'), ('issued', '已发放'), ('withdrawn', '已撤回')]},
    {'dict_code': 'inv_material_requisition_event_type', 'dict_name': '物资领用申请操作类型', 'scope': 'global', 'items': [('submit', '提交'), ('approve', '审批通过'), ('reject', '驳回'), ('withdraw', '撤回'), ('issue', '发放')]},
    {'dict_code': 'inv_handling_method', 'dict_name': '报损处理方式', 'scope': 'tenant', 'items': [('scrap', '报废'), ('repair', '维修'), ('return_supplier', '退回供应商'), ('other', '其他')]},
    {'dict_code': 'inv_source_doc_type', 'dict_name': '上游业务单据类型', 'scope': 'global', 'items': [('pur_order', '采购订单'), ('canteen_plan', '菜谱采购计划'), ('inv_requisition', '领用申请'), ('inv_lend_request', '借用申请'), ('mes_work_order', '生产工单')]},
    {'dict_code': 'inv_transaction_type', 'dict_name': '库存流水方向', 'scope': 'global', 'items': [('in', '入库'), ('out', '出库'), ('move', '移位'), ('status', '状态转换'), ('adjust', '调整')]},
    {'dict_code': 'inv_requisition_status', 'dict_name': '物资领用申请状态', 'scope': 'global', 'items': [('submitted', '待审批'), ('approved', '待发放'), ('rejected', '已驳回'), ('issued', '已发放'), ('withdrawn', '已撤回')]},
    {'dict_code': 'inv_requisition_event_type', 'dict_name': '物资领用操作类型', 'scope': 'global', 'items': [('submit', '提交'), ('approve', '审批通过'), ('reject', '驳回'), ('withdraw', '撤回'), ('issue', '发放')]},
    {'dict_code': 'wf_business_type', 'dict_name': '审批业务类型', 'scope': 'tenant', 'items': [('student_leave', '学生请假'), ('schedule_change', '调代课'), ('score_change', '成绩修改'), ('ar_adjustment', '账单调整'), ('ar_refund', '退费'), ('inventory_order', '库存单据'), ('registration_change', '学籍异动')]},
    {'dict_code': 'wf_definition_version_status', 'dict_name': '流程版本状态', 'scope': 'global', 'items': [('draft', '草稿'), ('published', '已发布'), ('offline', '已下线')]},
    {'dict_code': 'wf_instance_status', 'dict_name': '流程实例状态', 'scope': 'global', 'items': [('running', '进行中'), ('completed', '已完成'), ('rejected', '已驳回'), ('cancelled', '已撤销')]},
    {'dict_code': 'wf_ai_analysis_status', 'dict_name': '待办AI分析状态', 'scope': 'global', 'items': [('not_applicable', '未接入'), ('pending', '待分析'), ('processing', '分析中'), ('succeeded', '已生成'), ('failed', '分析失败')]},
    {'dict_code': 'wf_task_status', 'dict_name': '审批任务状态', 'scope': 'global', 'items': [('pending', '待处理'), ('completed', '已处理'), ('cancelled', '已取消')]},
    {'dict_code': 'wf_assignee_type', 'dict_name': '审批人类型', 'scope': 'global', 'items': [('user', '指定用户'), ('department_manager', '部门负责人'), ('business_owner', '业务负责人'), ('initiator_leader', '发起人上级'), ('permission', '拥有权限的用户'), ('starter', '发起人本人'), ('starter_select', '发起人自选')]},
    {'dict_code': 'wf_approval_mode', 'dict_name': '多人审批方式', 'scope': 'global', 'items': [('single', '单人'), ('any', '任一人通过'), ('all', '全部通过')]},
    {'dict_code': 'wf_task_outcome', 'dict_name': '审批结果', 'scope': 'global', 'items': [('approved', '同意'), ('rejected', '驳回'), ('returned', '退回')]},
    {'dict_code': 'wf_action', 'dict_name': '审批动作', 'scope': 'global', 'items': [('submit', '提交'), ('approve', '同意'), ('reject', '驳回'), ('return', '退回'), ('transfer', '转办'), ('add_sign', '加签'), ('withdraw', '撤回'), ('cc', '抄送'), ('comment', '评论')]},
    {'dict_code': 'wf_cc_type', 'dict_name': '抄送对象类型', 'scope': 'global', 'items': [('user', '用户'), ('department_manager', '部门负责人'), ('business_owner', '业务负责人'), ('initiator_leader', '发起人上级'), ('permission', '拥有权限的用户'), ('starter', '发起人本人'), ('starter_select', '发起人自选')]},
    {'dict_code': 'wf_read_status', 'dict_name': '阅读状态', 'scope': 'global', 'items': [('unread', '未读'), ('read', '已读')]},
    {'dict_code': 'ntf_notice_type', 'dict_name': '公告类型', 'scope': 'tenant', 'items': [('notice', '通知'), ('announcement', '公告')]},
    {'dict_code': 'ntf_notice_status', 'dict_name': '公告状态', 'scope': 'global', 'items': [('draft', '草稿'), ('published', '已发布'), ('offline', '已下线')]},
    {'dict_code': 'ntf_target_type', 'dict_name': '接收对象类型', 'scope': 'global', 'items': [('all', '全部'), ('role', '角色'), ('user', '用户'), ('permission', '权限'), ('actor', '业务相关人')]},
    {'dict_code': 'ntf_severity', 'dict_name': '重要程度', 'scope': 'global', 'items': [('normal', '普通'), ('important', '重要'), ('urgent', '紧急')]},
    {'dict_code': 'ntf_channel', 'dict_name': '通知渠道', 'scope': 'global', 'items': [('in_app', '站内信'), ('wechat_service', '微信服务号'), ('wechat_miniapp_subscribe', '小程序订阅消息'), ('sms', '短信'), ('email', '邮件')]},
    {'dict_code': 'ntf_fallback_policy', 'dict_name': '渠道降级策略', 'scope': 'global', 'items': [('none', '不降级'), ('all', '全部渠道')]},
    {'dict_code': 'ntf_route_org_scope', 'dict_name': '通知组织范围', 'scope': 'global', 'items': [('none', '不限'), ('event_organization', '事件所属组织')]},
    {'dict_code': 'ntf_notification_status', 'dict_name': '通知状态', 'scope': 'global', 'items': [('created', '已创建'), ('cancelled', '已取消')]},
    {'dict_code': 'ntf_recipient_status', 'dict_name': '阅读状态', 'scope': 'global', 'items': [('unread', '未读'), ('read', '已读'), ('archived', '已归档')]},
    {'dict_code': 'ntf_delivery_status', 'dict_name': '投递状态', 'scope': 'global', 'items': [('pending', '待发送'), ('sent', '已发送'), ('failed', '失败'), ('skipped', '已跳过')]},
    {'dict_code': 'ntf_provider', 'dict_name': '通知服务商', 'scope': 'global', 'items': [('wechat', '微信'), ('aliyun_sms', '阿里云短信'), ('smtp', '邮件服务')]},
    {'dict_code': 'ntf_event_status', 'dict_name': '事件处理结果', 'scope': 'global', 'items': [('processed', '已处理'), ('skipped', '已跳过'), ('failed', '失败')]},
    {'dict_code': 'audit_action', 'dict_name': '操作类型', 'scope': 'global', 'items': [('create', '新增'), ('read', '查看'), ('update', '修改'), ('delete', '删除'), ('submit', '提交'), ('approve', '审批'), ('export', '导出'), ('import', '导入'), ('login', '登录')]},
    {'dict_code': 'audit_target_type', 'dict_name': '操作对象类型', 'scope': 'global', 'items': [('user', '用户'), ('role', '角色'), ('student', '学生'), ('class', '班级'), ('score', '成绩'), ('leave_request', '请假'), ('ar_bill', '账单'), ('stock_order', '库存单据'), ('score_sheet', '成绩单'), ('lesson_evaluation', '评课'), ('survey', '问卷')]},
    # 领域事件类型：事件名为 <业务域前缀>.<实体>.<动作>（写在 routing_key），类型编码把点换成下划线
    {'dict_code': 'int_event_type', 'dict_name': '事件类型', 'scope': 'global', 'items': [('inv_stock_order_confirmed', '库存单据已确认'), ('hr_employee_hired', '员工已入职'), ('hr_employee_transferred', '员工已调动'), ('hr_employee_left', '员工已离职'), ('ar_bill_issued', '账单已出账'), ('ar_bill_voided', '账单已作废'), ('ar_payment_received', '收款已到账'), ('ar_payment_allocated', '收款已分配'), ('ar_adjustment_approved', '账单调整已批准'), ('ar_refund_paid', '退款已完成')]},
    {'dict_code': 'int_outbox_status', 'dict_name': '出站状态', 'scope': 'global', 'items': [('pending', '待发送'), ('published', '已发送'), ('failed', '失败'), ('dead', '死信')]},
]


def _declared_dicts() -> list[dict]:
    # 按调用时的收集范围取声明；避免导入时缓存了其他租户/停用插件的字典。
    declarations = list(CORE_DICTS)
    for module in iter_module_attr("dictionary_specs"):
        declarations.extend(module.DICTIONARIES)
    return declarations


# 字典 CRUD 用此集合保护部署中声明的内置编码；同步则按调用上下文动态取范围。
BUILTIN_DICTS = _declared_dicts()


def builtin_dict_specs() -> list[dict]:
    declarations = _declared_dicts()
    specs = {}
    for spec in declarations:
        key = spec["dict_code"]
        if key in specs:
            raise ValueError(f"Duplicate dictionary: {key}")
        specs[key] = {**spec, "items": list(spec["items"])}
    for attribute in ("dictionary_specs", "catalog"):
        for module in iter_module_attr(attribute):
            for key, items in getattr(module, "DICT_ITEMS", {}).items():
                if key not in specs:
                    raise ValueError(f"{module.__name__}: unknown dictionary {key}")
                existing = {code for code, _ in specs[key]["items"]}
                for code, name in items:
                    if code in existing:
                        raise ValueError(f"Duplicate dictionary item: {key}.{code}")
                    specs[key]["items"].append((code, name))
                    existing.add(code)
    return list(specs.values())
