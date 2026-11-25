import type { Emitter } from "mitt";
import mitt from "mitt";

/** 全局公共事件需要在此处添加类型 */
type Events = {
  openPanel: string;
  tagOnClick: string;
  logoChange: boolean;
  tagViewsChange: string;
  tagViewsTagsStyle: string;
  changLayoutRoute: string;
  tagViewsShowModel: string;
  /** 工作流审批/驳回后，业务列表应刷新 */
  workflowBusinessChanged: {
    business_type: string;
    business_id?: string;
    instance_status?: string;
  };
};

export const emitter: Emitter<Events> = mitt<Events>();
