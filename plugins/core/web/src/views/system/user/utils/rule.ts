import { reactive } from "vue";
import type { FormRules } from "element-plus";
import { isPhone, isEmail } from "@pureadmin/utils";

/** 用户表单校验 */
export const formRules = reactive(<FormRules>{
  full_name: [{ required: true, message: "姓名为必填项", trigger: "blur" }],
  password: [
    { required: true, message: "初始密码为必填项", trigger: "blur" },
    { min: 6, message: "密码至少 6 位", trigger: "blur" }
  ],
  org_id: [{ required: true, message: "请选择所属组织", trigger: "change" }],
  mobile: [
    {
      validator: (_rule, value, callback) => {
        if (!value) callback();
        else if (!isPhone(value))
          callback(new Error("请输入正确的手机号码格式"));
        else callback();
      },
      trigger: "blur"
    }
  ],
  email: [
    {
      validator: (_rule, value, callback) => {
        if (!value) callback();
        else if (!isEmail(value)) callback(new Error("请输入正确的邮箱格式"));
        else callback();
      },
      trigger: "blur"
    }
  ]
});
