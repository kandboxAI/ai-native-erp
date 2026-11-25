import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { inspectWeixinRelease } from "./weixin-release.mjs";

// 构建产物目录（uni-app 默认输出 dist/build/mp-weixin，相对小程序工程根）。
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const directory = join(root, "dist", "build", "mp-weixin");
inspectWeixinRelease(directory);
