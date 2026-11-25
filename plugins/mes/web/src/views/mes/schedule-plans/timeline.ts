import type {
  PlanDetail,
  PlanSegment,
} from "@plugins/mes/web/src/api/mesSchedulePlans";

export type TimelineView = "order" | "equipment" | "person";
export type TimelineRange = "overview" | "work" | "detail";
export type TimeWindow = { start: number; end: number };

type Stage = TimeWindow & { segment: PlanSegment };
type Bar = TimeWindow & { stage: Stage; count: number; kind: string };
type Milestone = { at: number; label: string };

type Lane = {
  id: string;
  label: string;
  bars: Bar[];
  milestones: Milestone[];
};

export const stageLabels: Record<string, string> = {
  preparation: "准备",
  load: "装料",
  run: "加工",
  unload: "卸料",
  waiting_unload: "占机等待卸料",
  manual: "人工",
  inspection: "检验",
  external_wait: "委外加工 / 等待回厂",
};

export const hour = 3_600_000;
export const rangeHours = { work: 8, detail: 2 };

export function timelineWindow(
  bounds: TimeWindow,
  range: TimelineRange,
  firstStage: number,
  anchor?: number,
): TimeWindow {
  if (range === "overview") return bounds;
  const length = Math.min(bounds.end - bounds.start, rangeHours[range] * hour);
  const firstHour = new Date(firstStage).setMinutes(0, 0, 0);
  const start = Math.max(
    bounds.start,
    Math.min(anchor ?? firstHour, bounds.end - length),
  );
  return { start, end: start + length };
}

export function timelineStages(segments: PlanSegment[]): Stage[] {
  return segments
    .map((segment) => ({
      segment,
      start: Date.parse(segment.planned_start_at),
      end: Date.parse(segment.planned_end_at),
    }))
    .filter((stage) => stage.start < stage.end)
    .sort((a, b) => a.start - b.start);
}

function barKind(segment: PlanSegment, aggregate: boolean) {
  const kind = segment.segment_type_code;
  if (aggregate && ["preparation", "load", "run", "unload"].includes(kind))
    return "run";
  return kind;
}

export function personLabel(segment: PlanSegment) {
  return segment.production_person_name || (segment.production_person_id ? "姓名未维护" : "—");
}

export function equipmentLabel(segment: PlanSegment) {
  return segment.equipment_name ||
    segment.equipment_name_snapshot?.match(/ · (.+)$/)?.[1] ||
    (segment.equipment_id ? "设备名称未维护" : "—");
}

export function timelineLanes(
  stages: Stage[],
  operations: PlanDetail["operations"],
  completions: PlanDetail["result"]["completions"],
  window: TimeWindow,
  view: TimelineView,
  range: TimelineRange,
) {
  const aggregate = range !== "detail";
  const lanes = new Map<string, Lane>();
  const orderIds = new Map(
    operations.map((operation) => [operation.id, operation.work_order_id]),
  );
  const completionByOrder = new Map(
    completions.map((completion) => [completion.work_order_id, completion]),
  );

  for (const stage of stages) {
    const { segment } = stage;
    const inWindow = stage.end > window.start && stage.start < window.end;
    if (!inWindow && view !== "order") continue;
    const orderId = orderIds.get(segment.plan_operation_id);
    const resource = {
      order: [orderId ?? segment.work_order_no, segment.work_order_no],
      equipment: [segment.equipment_id, equipmentLabel(segment)],
      person: [
        segment.person_capacity_units_snapshot
          ? segment.production_person_id
          : null,
        personLabel(segment),
      ],
    }[view];
    const [id, label] = resource;
    if (!id) continue;
    let lane = lanes.get(id);
    if (!lane) {
      const completion =
        orderId && view === "order"
          ? completionByOrder.get(orderId)
          : undefined;
      const milestones = completion
        ? [
            {
              at: Date.parse(completion.first_article_release_at),
              label: "首件检验放行",
            },
            {
              at: Date.parse(completion.inspection_release_at),
              label: "整批检验放行",
            },
            { at: Date.parse(completion.due_at), label: "承诺出货交期" },
          ].filter(
            (event) =>
              Number.isFinite(event.at) &&
              (range === "overview" ||
                (event.at >= window.start && event.at <= window.end)),
          )
        : [];
      lane = { id, label: label || id, bars: [], milestones };
      lanes.set(id, lane);
    }
    if (!inWindow) continue;
    const kind = barKind(segment, aggregate);
    const previous = lane.bars.at(-1);
    const prior = previous?.stage.segment;
    if (
      aggregate &&
      previous &&
      prior &&
      previous.end === stage.start &&
      previous.kind === kind &&
      prior.plan_operation_id === segment.plan_operation_id &&
      prior.production_phase_code === segment.production_phase_code &&
      prior.is_independent_inspection === segment.is_independent_inspection &&
      prior.equipment_id === segment.equipment_id &&
      prior.production_person_id === segment.production_person_id &&
      prior.person_capacity_units_snapshot ===
        segment.person_capacity_units_snapshot
    ) {
      previous.end = stage.end;
      previous.count++;
    } else {
      lane.bars.push({
        start: stage.start,
        end: stage.end,
        stage,
        count: 1,
        kind,
      });
    }
  }

  return [...lanes.values()]
    .filter((lane) => lane.bars.length || lane.milestones.length)
    .map(({ bars, ...lane }) => {
      const tracks: Bar[][] = [];
      for (const bar of bars) {
        let track = tracks.find((track) => track.at(-1)!.end <= bar.start);
        if (!track) {
          track = [];
          tracks.push(track);
        }
        track.push(bar);
      }
      return { ...lane, tracks };
    });
}
