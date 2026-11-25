declare module "virtual:deployed-views" {
  const views: Record<string, () => Promise<unknown>>;
  export default views;
}

declare module "virtual:workbench-calendar" {
  export type CalendarEvent = { id: string; date: string; time: string; title: string; description: string; path: string };
  const loader: null | (() => Promise<{ loadEvents: (start: string, end: string) => Promise<CalendarEvent[]> }>);
  export default loader;
}
