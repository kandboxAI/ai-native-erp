import { reactive, watch } from "vue";
import { saveMyAvatar } from "@/api/userAvatar";
import { discardFile, fileUrl, uploadPhoto } from "@/api/systemFile";
import { appStore } from "./app";

const state = reactive({ saving: false });
let generation = 0;
watch([() => appStore.state.account, () => appStore.state.loggedIn], () => {
  generation++;
  state.saving = false;
}, { flush: "sync" });

async function save(path: string) {
  const account = appStore.state.account;
  if (!account || !appStore.state.loggedIn || state.saving) return false;
  const version = generation;
  const current = () => version === generation && appStore.state.account === account;
  state.saving = true;
  let fileId: string | undefined;
  let committed = false;
  try {
    fileId = await uploadPhoto(path, "user_avatar");
    if (!current()) return false;
    const result = await saveMyAvatar(fileId);
    committed = true;
    if (!current()) return false;
    appStore.updateAccountAvatar(fileUrl(result.avatar_url));
    return true;
  } catch (error) {
    if (!current()) return false;
    if (fileId && !committed) await discardFile(fileId).catch(() => undefined);
    throw error;
  } finally {
    if (current()) state.saving = false;
  }
}

export const avatarStore = { state, save };
