// Local menu icons are registered during layout startup, avoiding network icon
// requests while rendering backend-provided routes.
import { getSvgInfo } from "@pureadmin/utils";
import { addIcon } from "@iconify/vue/dist/offline";

import EpAvatar from "~icons/ep/avatar?raw";
import EpBell from "~icons/ep/bell?raw";
import EpCalendar from "~icons/ep/calendar?raw";
import EpChatDotSquare from "~icons/ep/chat-dot-square?raw";
import EpChatDotRound from "~icons/ep/chat-dot-round?raw";
import EpChatLineSquare from "~icons/ep/chat-line-square?raw";
import EpChatLineRound from "~icons/ep/chat-line-round?raw";
import EpChecked from "~icons/ep/checked?raw";
import EpCircleCheck from "~icons/ep/circle-check?raw";
import EpClock from "~icons/ep/clock?raw";
import EpCoin from "~icons/ep/coin?raw";
import EpCollection from "~icons/ep/collection?raw";
import EpCollectionTag from "~icons/ep/collection-tag?raw";
import EpDataAnalysis from "~icons/ep/data-analysis?raw";
import EpDataBoard from "~icons/ep/data-board?raw";
import EpDataLine from "~icons/ep/data-line?raw";
import EpDocument from "~icons/ep/document?raw";
import EpDocumentAdd from "~icons/ep/document-add?raw";
import EpDocumentChecked from "~icons/ep/document-checked?raw";
import EpDocumentCopy from "~icons/ep/document-copy?raw";
import EpEdit from "~icons/ep/edit?raw";
import EpEditPen from "~icons/ep/edit-pen?raw";
import EpFiles from "~icons/ep/files?raw";
import EpFinished from "~icons/ep/finished?raw";
import EpFlag from "~icons/ep/flag?raw";
import EpFolderAdd from "~icons/ep/folder-add?raw";
import EpGrid from "~icons/ep/grid?raw";
import EpGuide from "~icons/ep/guide?raw";
import EpHistogram from "~icons/ep/histogram?raw";
import EpHomeFilled from "~icons/ep/home-filled?raw";
import EpHouse from "~icons/ep/house?raw";
import EpKey from "~icons/ep/key?raw";
import EpList from "~icons/ep/list?raw";
import EpLollipop from "~icons/ep/lollipop?raw";
import EpManagement from "~icons/ep/management?raw";
import EpMedal from "~icons/ep/medal?raw";
import EpMenu from "~icons/ep/menu?raw";
import EpMessage from "~icons/ep/message?raw";
import EpMonitor from "~icons/ep/monitor?raw";
import EpMoney from "~icons/ep/money?raw";
import EpNotebook from "~icons/ep/notebook?raw";
import EpOdometer from "~icons/ep/odometer?raw";
import EpOfficeBuilding from "~icons/ep/office-building?raw";
import EpOperation from "~icons/ep/operation?raw";
import EpOpportunity from "~icons/ep/opportunity?raw";
import EpPhone from "~icons/ep/phone?raw";
import EpPieChart from "~icons/ep/pie-chart?raw";
import EpPlus from "~icons/ep/plus?raw";
import EpPriceTag from "~icons/ep/price-tag?raw";
import EpPrinter from "~icons/ep/printer?raw";
import EpQuestionFilled from "~icons/ep/question-filled?raw";
import EpReading from "~icons/ep/reading?raw";
import EpSchool from "~icons/ep/school?raw";
import EpSetUp from "~icons/ep/set-up?raw";
import EpSetting from "~icons/ep/setting?raw";
import EpShoppingCart from "~icons/ep/shopping-cart?raw";
import EpStamp from "~icons/ep/stamp?raw";
import EpStopwatch from "~icons/ep/stopwatch?raw";
import EpTicket from "~icons/ep/ticket?raw";
import EpTickets from "~icons/ep/tickets?raw";
import EpTimer from "~icons/ep/timer?raw";
import EpTools from "~icons/ep/tools?raw";
import EpUser from "~icons/ep/user?raw";
import EpUserFilled from "~icons/ep/user-filled?raw";
import EpWallet from "~icons/ep/wallet?raw";
import EpWarning from "~icons/ep/warning?raw";

import RiAdminFill from "~icons/ri/admin-fill?raw";
import RiAdminLine from "~icons/ri/admin-line?raw";
import RiAlarmWarningLine from "~icons/ri/alarm-warning-line?raw";
import RiArtboardLine from "~icons/ri/artboard-line?raw";
import RiBankCardLine from "~icons/ri/bank-card-line?raw";
import RiBarChartHorizontalLine from "~icons/ri/bar-chart-horizontal-line?raw";
import RiBookmark2Line from "~icons/ri/bookmark-2-line?raw";
import RiBriefcase4Line from "~icons/ri/briefcase-4-line?raw";
import RiCalendarScheduleLine from "~icons/ri/calendar-schedule-line?raw";
import RiCheckboxCircleLine from "~icons/ri/checkbox-circle-line?raw";
import RiChatSearchLine from "~icons/ri/chat-search-line?raw";
import RiCodeBoxLine from "~icons/ri/code-box-line?raw";
import RiDashboardLine from "~icons/ri/dashboard-line?raw";
import RiEditBoxLine from "~icons/ri/edit-box-line?raw";
import RiFileCheckLine from "~icons/ri/file-check-line?raw";
import RiFileInfoLine from "~icons/ri/file-info-line?raw";
import RiFilePaper2Line from "~icons/ri/file-paper-2-line?raw";
import RiFilePpt2Line from "~icons/ri/file-ppt-2-line?raw";
import RiFileSearchLine from "~icons/ri/file-search-line?raw";
import RiGitBranchLine from "~icons/ri/git-branch-line?raw";
import RiHistoryFill from "~icons/ri/history-fill?raw";
import RiInformationLine from "~icons/ri/information-line?raw";
import RiLinksFill from "~icons/ri/links-fill?raw";
import RiListCheck from "~icons/ri/list-check?raw";
import RiMarkdownLine from "~icons/ri/markdown-line?raw";
import RiMindMap from "~icons/ri/mind-map?raw";
import RiMessage3Line from "~icons/ri/message-3-line?raw";
import RiNotification3Line from "~icons/ri/notification-3-line?raw";
import RiSearchLine from "~icons/ri/search-line?raw";
import RiSettings3Line from "~icons/ri/settings-3-line?raw";
import RiSettings4Line from "~icons/ri/settings-4-line?raw";
import RiTableLine from "~icons/ri/table-line?raw";
import RiTaskLine from "~icons/ri/task-line?raw";
import RiTeamLine from "~icons/ri/team-line?raw";
import RiTerminalWindowLine from "~icons/ri/terminal-window-line?raw";
import RiUbuntuFill from "~icons/ri/ubuntu-fill?raw";
import RiUserVoiceLine from "~icons/ri/user-voice-line?raw";
import RiWindowLine from "~icons/ri/window-line?raw";

const icons = [
  ["ep/avatar", EpAvatar],
  ["ep/bell", EpBell],
  ["ep/calendar", EpCalendar],
  ["ep/chat-dot-square", EpChatDotSquare],
  ["ep/chat-dot-round", EpChatDotRound],
  ["ep/chat-line-square", EpChatLineSquare],
  ["ep/chat-line-round", EpChatLineRound],
  ["ep/checked", EpChecked],
  ["ep/circle-check", EpCircleCheck],
  ["ep/clock", EpClock],
  ["ep/coin", EpCoin],
  ["ep/collection", EpCollection],
  ["ep/collection-tag", EpCollectionTag],
  ["ep/data-analysis", EpDataAnalysis],
  ["ep/data-board", EpDataBoard],
  ["ep/data-line", EpDataLine],
  ["ep/document", EpDocument],
  ["ep/document-add", EpDocumentAdd],
  ["ep/document-checked", EpDocumentChecked],
  ["ep/document-copy", EpDocumentCopy],
  ["ep/edit", EpEdit],
  ["ep/edit-pen", EpEditPen],
  ["ep/files", EpFiles],
  ["ep/finished", EpFinished],
  ["ep/flag", EpFlag],
  ["ep/folder-add", EpFolderAdd],
  ["ep/grid", EpGrid],
  ["ep/guide", EpGuide],
  ["ep/histogram", EpHistogram],
  ["ep/home-filled", EpHomeFilled],
  ["ep/house", EpHouse],
  ["ep/key", EpKey],
  ["ep/list", EpList],
  ["ep/lollipop", EpLollipop],
  ["ep/management", EpManagement],
  ["ep/medal", EpMedal],
  ["ep/menu", EpMenu],
  ["ep/message", EpMessage],
  ["ep/monitor", EpMonitor],
  ["ep/money", EpMoney],
  ["ep/notebook", EpNotebook],
  ["ep/odometer", EpOdometer],
  ["ep/office-building", EpOfficeBuilding],
  ["ep/operation", EpOperation],
  ["ep/opportunity", EpOpportunity],
  ["ep/phone", EpPhone],
  ["ep/pie-chart", EpPieChart],
  ["ep/plus", EpPlus],
  ["ep/price-tag", EpPriceTag],
  ["ep/printer", EpPrinter],
  ["ep/question-filled", EpQuestionFilled],
  ["ep/reading", EpReading],
  ["ep/school", EpSchool],
  ["ep/set-up", EpSetUp],
  ["ep/setting", EpSetting],
  ["ep/shopping-cart", EpShoppingCart],
  ["ep/stamp", EpStamp],
  ["ep/stopwatch", EpStopwatch],
  ["ep/ticket", EpTicket],
  ["ep/tickets", EpTickets],
  ["ep/timer", EpTimer],
  ["ep/tools", EpTools],
  ["ep/user", EpUser],
  ["ep/user-filled", EpUserFilled],
  ["ep/wallet", EpWallet],
  ["ep/warning", EpWarning],
  ["ri/admin-fill", RiAdminFill],
  ["ri/admin-line", RiAdminLine],
  ["ri/alarm-warning-line", RiAlarmWarningLine],
  ["ri/artboard-line", RiArtboardLine],
  ["ri/bank-card-line", RiBankCardLine],
  ["ri/bar-chart-horizontal-line", RiBarChartHorizontalLine],
  ["ri/bookmark-2-line", RiBookmark2Line],
  ["ri/briefcase-4-line", RiBriefcase4Line],
  ["ri/calendar-schedule-line", RiCalendarScheduleLine],
  ["ri/checkbox-circle-line", RiCheckboxCircleLine],
  ["ri/chat-search-line", RiChatSearchLine],
  ["ri/code-box-line", RiCodeBoxLine],
  ["ri/dashboard-line", RiDashboardLine],
  ["ri/edit-box-line", RiEditBoxLine],
  ["ri/file-check-line", RiFileCheckLine],
  ["ri/file-info-line", RiFileInfoLine],
  ["ri/file-paper-2-line", RiFilePaper2Line],
  ["ri/file-ppt-2-line", RiFilePpt2Line],
  ["ri/file-search-line", RiFileSearchLine],
  ["ri/git-branch-line", RiGitBranchLine],
  ["ri/history-fill", RiHistoryFill],
  ["ri/information-line", RiInformationLine],
  ["ri/links-fill", RiLinksFill],
  ["ri/list-check", RiListCheck],
  ["ri/markdown-line", RiMarkdownLine],
  ["ri/mind-map", RiMindMap],
  ["ri/message-3-line", RiMessage3Line],
  ["ri/notification-3-line", RiNotification3Line],
  ["ri/search-line", RiSearchLine],
  ["ri/settings-3-line", RiSettings3Line],
  ["ri/settings-4-line", RiSettings4Line],
  ["ri/table-line", RiTableLine],
  ["ri/task-line", RiTaskLine],
  ["ri/team-line", RiTeamLine],
  ["ri/terminal-window-line", RiTerminalWindowLine],
  ["ri/ubuntu-fill", RiUbuntuFill],
  ["ri/user-voice-line", RiUserVoiceLine],
  ["ri/window-line", RiWindowLine]
];

icons.forEach(([name, icon]) => {
  addIcon(name as string, getSvgInfo(icon as string));
});
