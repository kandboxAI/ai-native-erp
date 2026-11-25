import { reactive } from "vue";
import type { FormRules } from "element-plus";

const ROLE_NO_RE = /^[a-z][a-z0-9_]*$/;

/** 角色表单校验 */
export const formRules = reactive(<FormRules>{
  role_name: [{ required: true, message: "角色名称为必填项", trigger: "blur" }],
  role_no: [
    { required: true, message: "角色编号为必填项", trigger: "blur" },
    {
      validator: (_rule, value, callback) => {
        if (!ROLE_NO_RE.test(String(value || ""))) {
          callback(
            new Error("只能使用小写字母、数字、下划线，且以小写字母开头")
          );
        } else {
          callback();
        }
      },
      trigger: "blur"
    }
  ],
  data_scope_code: [
    { required: true, message: "请选择数据范围", trigger: "change" }
  ]
});
