import type { Router } from "vue-router";
import { getToken } from "@/utils/auth";
import type { AiQuestionContext } from "./aiPageContext";

type AssistantRequest =
  | {
      kind: "question";
      prompt: string;
      context?: AiQuestionContext;
      userId?: string;
    }
  | { kind: "recent" };

let pendingRequest: AssistantRequest | undefined;
let openRequest: ((request: AssistantRequest) => void) | undefined;
let closeRequest: (() => Promise<void>) | undefined;
let managementPage: { userId: string; fullPath: string } | undefined;

/** Dedicated desktop conversation page, separate from the application home. */
export const desktopAssistantPath = "/assistant";

function deliverPendingRequest() {
  if (!openRequest || !pendingRequest) return;
  const request = pendingRequest;
  pendingRequest = undefined;
  if (request.kind === "question" && request.userId !== getToken()?.userId)
    return;
  openRequest(request);
}

async function routeAssistantRequest(
  router: Router,
  request: AssistantRequest
) {
  if (!window.erpDesktop) return;
  const source = router.currentRoute.value;
  const userId = getToken()?.userId;
  if (
    userId &&
    source.path !== desktopAssistantPath &&
    source.path !== "/login" &&
    !source.path.startsWith("/error/")
  ) {
    managementPage = { userId, fullPath: source.fullPath || source.path };
  }
  pendingRequest = request;
  if (
    router.currentRoute.value.path !== desktopAssistantPath ||
    router.currentRoute.value.query.tab !== undefined
  ) {
    // The previous page may still be mounted during a route transition or cached.
    // Keep the request queued until the destination page registers its opener.
    openRequest = undefined;
    closeRequest = undefined;
    await router.push(desktopAssistantPath);
  }
  if (router.currentRoute.value.path !== desktopAssistantPath) {
    pendingRequest = undefined;
    throw new Error("Desktop assistant navigation was blocked");
  }
  deliverPendingRequest();
}

/** Route a new desktop question to the workbench's embedded DSH view. */
export async function askDesktopAssistant(
  router: Router,
  prompt: string,
  context?: AiQuestionContext
) {
  const question = prompt.trim();
  if (!question) return;
  await routeAssistantRequest(router, {
    kind: "question",
    prompt: question,
    ...(context ? { context: JSON.parse(JSON.stringify(context)) } : {}),
    userId: getToken()?.userId
  });
}

/** Open the latest existing conversation in the embedded DSH view. */
export async function continueDesktopAssistant(router: Router) {
  await routeAssistantRequest(router, { kind: "recent" });
}

/** Close the workbench's embedded DSH panel before changing desktop views. */
export async function closeDesktopAssistantPanel() {
  await closeRequest?.();
}

/** Return to the current user's source page, preserving its query and hash. */
export async function returnToDesktopManagement(router: Router) {
  if (!window.erpDesktop) return;
  pendingRequest = undefined;
  await closeDesktopAssistantPanel();
  if (router.currentRoute.value.path !== desktopAssistantPath) return;
  const destination =
    managementPage && managementPage.userId === getToken()?.userId
      ? managementPage.fullPath
      : "/welcome";
  const failure = await router.replace(destination);
  if (failure) throw new Error("Desktop management navigation was blocked");
}

/** Register the workbench's DSH opener and closer for desktop navigation. */
export function registerDesktopAssistant(
  open: (request: AssistantRequest) => void,
  close: () => Promise<void>
) {
  openRequest = open;
  closeRequest = close;
  deliverPendingRequest();
  return () => {
    if (openRequest === open) openRequest = undefined;
    if (closeRequest === close) closeRequest = undefined;
  };
}
