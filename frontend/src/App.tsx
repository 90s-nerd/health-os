import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Archive,
  ArrowRight,
  BarChart3,
  CalendarDays,
  Check,
  ChevronRight,
  Droplets,
  GlassWater,
  HeartPulse,
  Home,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  Menu,
  Pencil,
  Plus,
  RotateCcw,
  Scale,
  Settings as SettingsIcon,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, post } from "./api";
import type { Callout, Task, Today as TodayType } from "./types";
import { HabitIcon } from "./icons";
type View = "today" | "week" | "progress" | "plan" | "settings";
const nav = [
  ["today", "Today", Home],
  ["week", "Week", CalendarDays],
  ["progress", "Progress", BarChart3],
  ["plan", "Plan", Menu],
  ["settings", "Settings", SettingsIcon],
] as const;

const detectedTimezone =
  Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
const supportedTimezones = (
  Intl as typeof Intl & {
    supportedValuesOf?: (key: "timeZone") => string[];
  }
).supportedValuesOf?.("timeZone") ?? [
  "America/Chicago",
  "America/New_York",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Asia/Karachi",
];

function timezoneLabel(timezone: string) {
  if (timezone === "UTC") return "UTC — Coordinated Universal Time";
  const city = timezone.split("/").at(-1)?.replaceAll("_", " ") || timezone;
  const name = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    timeZoneName: "longGeneric",
  })
    .formatToParts()
    .find((part) => part.type === "timeZoneName")?.value;
  return `${city}${name ? ` — ${name}` : ""} (${timezone})`;
}

const timezoneOptions = [
  ...new Set(["UTC", detectedTimezone, ...supportedTimezones]),
]
  .map((value) => ({ value, label: timezoneLabel(value) }))
  .sort((left, right) => left.label.localeCompare(right.label));

function TimezoneSelect({
  value,
  onChange,
  autoFocus = false,
}: {
  value: string;
  onChange: (value: string) => void;
  autoFocus?: boolean;
}) {
  const options = timezoneOptions.some((option) => option.value === value)
    ? timezoneOptions
    : [{ value, label: timezoneLabel(value) }, ...timezoneOptions];
  return (
    <select
      autoFocus={autoFocus}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      required
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
function Loading() {
  return (
    <div className="center">
      <LoaderCircle className="spin" />
      <p>Loading your day…</p>
    </div>
  );
}
function ErrorBox({ error }: { error: Error }) {
  return (
    <div className="center error">
      <ShieldAlert />
      <h2>We couldn’t load this yet</h2>
      <p>{error.message}</p>
      <button onClick={() => location.reload()}>Try again</button>
    </div>
  );
}
function Ring({ value, label }: { value: number; label: string }) {
  return (
    <div
      className="ring"
      style={{ "--value": `${value * 3.6}deg` } as React.CSSProperties}
    >
      <div>
        <b>{value}%</b>
        <span>{label}</span>
      </div>
    </div>
  );
}
function TaskCard({
  task,
  onComplete,
  onUndo,
  onSkip,
  pending,
}: {
  task: Task;
  onComplete: (minimum: boolean) => void;
  onUndo: () => void;
  onSkip: () => void;
  pending: boolean;
}) {
  const [open, setOpen] = useState(false);
  const done = task.state === "completed";
  const skipped = task.state === "skipped";
  return (
    <article
      className={`task-card ${done ? "done" : ""} ${skipped ? "skipped" : ""}`}
    >
      <button
        className="task-main"
        aria-label={`${task.name}: ${task.state}`}
        onClick={() => (done || skipped ? onUndo() : onComplete(false))}
        disabled={pending}
      >
        <span className="task-icon">
          {skipped ? (
            <X size={19} />
          ) : (
            <HabitIcon name={done ? "check" : task.icon} />
          )}
        </span>
        <span className="task-copy">
          <strong>{task.name}</strong>
          <small>
            {skipped
              ? "Skipped intentionally · tap to restore"
              : done
                ? task.minimum_version
                  ? "Minimum version · habit protected"
                  : "Completed"
                : `${task.suggested_time || "Any time"} · ${task.required ? "Core" : "Optional"}`}
          </small>
        </span>
        <span
          className={`check ${done ? "checked" : ""} ${skipped ? "skipped" : ""}`}
        >
          {done && <Check size={18} />}
          {skipped && <RotateCcw size={16} />}
        </span>
      </button>
      {skipped && (
        <div className="skipped-actions">
          <span>Skipped intentionally</span>
          <button onClick={onUndo} disabled={pending}>
            <RotateCcw size={14} /> Undo skip
          </button>
        </div>
      )}
      {!done && !skipped && (
        <>
          <button
            className="more"
            onClick={() => setOpen(!open)}
            aria-expanded={open}
          >
            •••
          </button>
          {open && (
            <div className="task-actions">
              <p>{task.description}</p>
              {task.minimum_label && (
                <button onClick={() => onComplete(true)}>
                  <Sparkles size={16} /> Do minimum: {task.minimum_label}
                </button>
              )}
              <button onClick={onSkip}>
                <X size={16} /> Skip intentionally
              </button>
            </div>
          )}
        </>
      )}
    </article>
  );
}
function CalloutCard({
  item,
  onDismiss,
  onAction,
}: {
  item: Callout;
  onDismiss: () => void;
  onAction?: () => void;
}) {
  return (
    <aside className={`callout ${item.severity}`}>
      <div>
        <span className="eyebrow">{item.severity}</span>
        <h3>{item.title}</h3>
        <p>{item.message}</p>
        {item.suggested_action &&
          (onAction ? (
            <button className="callout-action" onClick={onAction}>
              {item.suggested_action} <ChevronRight size={15} />
            </button>
          ) : (
            <small>{item.suggested_action}</small>
          ))}
      </div>
      {item.dismissible && (
        <button onClick={onDismiss} aria-label={`Dismiss ${item.title}`}>
          <X size={17} />
        </button>
      )}
    </aside>
  );
}
function Today() {
  const qc = useQueryClient();
  const [weightOpen, setWeightOpen] = useState(false);
  const query = useQuery({
    queryKey: ["today"],
    queryFn: () => api<TodayType>("/today"),
  });
  const action = useMutation({
    mutationFn: ({
      id,
      kind,
      minimum = false,
    }: {
      id: number;
      kind: "complete" | "undo" | "skip";
      minimum?: boolean;
    }) =>
      kind === "undo"
        ? api(`/tasks/${id}/completion`, { method: "DELETE" })
        : post(
            `/tasks/${id}/${kind}`,
            minimum ? { minimum_version: true } : {},
          ),
    onMutate: async (vars) => {
      await qc.cancelQueries({ queryKey: ["today"] });
      const old = qc.getQueryData<TodayType>(["today"]);
      if (old)
        qc.setQueryData<TodayType>(["today"], {
          ...old,
          tasks: old.tasks.map((t) =>
            t.id === vars.id
              ? {
                  ...t,
                  state:
                    vars.kind === "undo"
                      ? "available"
                      : vars.kind === "skip"
                        ? "skipped"
                        : "completed",
                  minimum_version: vars.minimum || false,
                }
              : t,
          ),
        });
      return { old };
    },
    onError: (_e, _v, c) => c?.old && qc.setQueryData(["today"], c.old),
    onSettled: () => qc.invalidateQueries({ queryKey: ["today"] }),
  });
  const dismiss = useMutation({
    mutationFn: (id: string) => post(`/callouts/${id}/dismiss`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["today"] }),
  });
  const water = useMutation({
    mutationFn: ({ amount, undo }: { amount?: number; undo?: boolean }) =>
      undo
        ? api(`/hydration/${query.data?.water.latest_entry_id}`, {
            method: "DELETE",
          })
        : post("/hydration", { amount_ml: amount }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["today"] }),
  });
  if (query.isLoading) return <Loading />;
  if (query.error) return <ErrorBox error={query.error} />;
  const d = query.data!;
  const progress = Math.max(
    0,
    Math.min(
      100,
      ((d.weight.start - d.weight.current) /
        (d.weight.start - d.weight.next_milestone)) *
        100,
    ),
  );
  return (
    <div className="page today">
      <header className="today-header">
        <div>
          <p className="date">
            {new Date(d.date + "T12:00:00").toLocaleDateString(undefined, {
              weekday: "long",
              month: "long",
              day: "numeric",
            })}
          </p>
          <h1>
            {d.greeting}, {d.display_name}
          </h1>
          <span className={`mode ${d.mode.flexible ? "flexible" : ""}`}>
            {d.mode.name}
          </span>
        </div>
        <Ring value={d.completion} label="today" />
      </header>
      <p className="mode-note">{d.mode.subtitle}</p>
      <section className="status-row">
        <div>
          <span>Weekly rhythm</span>
          <strong>{d.weekly_consistency}%</strong>
          <div className="progress">
            <i style={{ width: `${d.weekly_consistency}%` }} />
          </div>
        </div>
        <div className="weight-status">
          <span>Weight trend</span>
          <div>
            <strong>{d.weight.current} kg</strong>
            <button onClick={() => setWeightOpen(true)}>Record</button>
          </div>
          <div className="progress weight">
            <i style={{ width: `${progress}%` }} />
          </div>
        </div>
        <div className="water-status">
          <div className="water-status-copy">
            <span>Water today</span>
            <strong>
              {d.water.current_ml.toLocaleString()} <small>ml</small>
            </strong>
            <small>{d.water.progress}% of your daily target</small>
          </div>
          <div
            className="water-gauge"
            style={{ "--water": `${d.water.progress}%` } as React.CSSProperties}
            aria-label={`${d.water.progress}% of water target`}
          >
            <Droplets size={21} />
          </div>
          <div className="water-actions" aria-label="Add water">
            {[250, 350, 500].map((amount) => (
              <button
                key={amount}
                onClick={() => water.mutate({ amount })}
                disabled={water.isPending}
                aria-label={`Add ${amount} milliliters of water`}
              >
                <GlassWater
                  size={amount === 250 ? 15 : amount === 350 ? 17 : 19}
                />
                +{amount}
              </button>
            ))}
            {d.water.latest_entry_id && (
              <button
                className="water-undo"
                onClick={() => water.mutate({ undo: true })}
                disabled={water.isPending}
              >
                Undo {d.water.latest_amount_ml} ml
              </button>
            )}
          </div>
        </div>
      </section>
      <section className="next">
        <span className="eyebrow">
          <Sparkles size={14} /> Next best action
        </span>
        <h2>{d.next_action.title}</h2>
        <p>{d.next_action.message}</p>
        {d.next_action.task_id && (
          <button
            onClick={() =>
              action.mutate({ id: d.next_action.task_id!, kind: "complete" })
            }
          >
            Mark complete <ChevronRight size={16} />
          </button>
        )}
      </section>
      {d.callouts.slice(0, 3).map((c) => (
        <CalloutCard
          key={c.id}
          item={c}
          onDismiss={() => dismiss.mutate(c.id)}
          onAction={
            c.id === "weight-due" ? () => setWeightOpen(true) : undefined
          }
        />
      ))}
      <div className="section-title">
        <div>
          <span className="eyebrow">Your rhythm</span>
          <h2>Today’s tasks</h2>
        </div>
        <span>
          {d.tasks.filter((x) => x.state === "completed").length}/
          {d.tasks.length}
        </span>
      </div>
      <div className="tasks">
        {d.tasks.map((t) => (
          <TaskCard
            key={t.id}
            task={t}
            pending={action.isPending}
            onComplete={(minimum) =>
              action.mutate({ id: t.id, kind: "complete", minimum })
            }
            onUndo={() => action.mutate({ id: t.id, kind: "undo" })}
            onSkip={() => action.mutate({ id: t.id, kind: "skip" })}
          />
        ))}
      </div>
      <QuickCheck tasks={d.tasks} mutate={action.mutate} />
      {weightOpen && (
        <WeightCheckIn
          currentWeight={d.weight.current}
          onClose={() => setWeightOpen(false)}
        />
      )}
    </div>
  );
}

type WeightEntry = {
  id: number;
  date: string;
  weight: number;
  average: number;
  waist_cm: number | null;
  notes: string | null;
};

function WeightCheckIn({
  currentWeight,
  entry,
  onClose,
}: {
  currentWeight?: number;
  entry?: WeightEntry | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const now = new Date();
  const localDate = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 10);
  const [entryDate, setEntryDate] = useState(entry?.date || localDate);
  const [weight, setWeight] = useState(
    entry ? String(entry.weight) : currentWeight ? String(currentWeight) : "",
  );
  const [waist, setWaist] = useState(
    entry?.waist_cm == null ? "" : String(entry.waist_cm),
  );
  const [notes, setNotes] = useState(entry?.notes || "");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    try {
      await api(entry ? `/weight/${entry.id}` : "/weight", {
        method: entry ? "PUT" : "POST",
        body: JSON.stringify({
          entry_date: entryDate,
          weight_kg: Number(weight),
          waist_cm: waist ? Number(waist) : null,
          notes: notes || null,
        }),
      });
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["today"] }),
        qc.invalidateQueries({ queryKey: ["progress"] }),
        qc.invalidateQueries({ queryKey: ["week"] }),
      ]);
      onClose();
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not save this reading",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation">
      <section
        className="weight-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="weight-title"
      >
        <div className="weight-modal-heading">
          <span className="weight-modal-icon">
            <Scale size={21} />
          </span>
          <div>
            <span className="eyebrow">
              {entry ? "Correct a reading" : "Quick check-in"}
            </span>
            <h2 id="weight-title">
              {entry ? "Edit weight entry" : "Record your weight"}
            </h2>
          </div>
          <button
            className="icon-button"
            onClick={onClose}
            aria-label="Close weight check-in"
          >
            <X size={18} />
          </button>
        </div>
        <p>
          {entry
            ? "Update any part of this reading and save your changes."
            : "One reading is enough. Daily fluctuations are normal; the trend matters more."}
        </p>
        <form onSubmit={save}>
          <div className="weight-primary-field">
            <label htmlFor="weight-value">Weight</label>
            <span>
              <input
                id="weight-value"
                type="number"
                inputMode="decimal"
                min="20"
                max="400"
                step="0.1"
                value={weight}
                onChange={(event) => setWeight(event.target.value)}
                autoFocus
                required
              />
              <b>kg</b>
            </span>
          </div>
          <div className="field-grid">
            <label>
              Date
              <input
                type="date"
                value={entryDate}
                onChange={(event) => setEntryDate(event.target.value)}
                required
              />
            </label>
            <label>
              Waist (optional)
              <input
                type="number"
                inputMode="decimal"
                min="30"
                max="300"
                step="0.1"
                value={waist}
                onChange={(event) => setWaist(event.target.value)}
                placeholder="cm"
              />
            </label>
            <label className="wide-field">
              Note (optional)
              <input
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="Anything useful to remember"
              />
            </label>
          </div>
          {message && (
            <p className="form-error" role="alert">
              {message}
            </p>
          )}
          <div className="weight-modal-actions">
            <button type="submit" disabled={saving || !weight}>
              {saving ? "Saving..." : entry ? "Save changes" : "Save reading"}
            </button>
            <button type="button" onClick={onClose}>
              Cancel
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
function QuickCheck({
  tasks,
  mutate,
}: {
  tasks: Task[];
  mutate: (v: { id: number; kind: "complete" | "undo" }) => void;
}) {
  return (
    <section className="quick">
      <span className="eyebrow">One-tap check-in</span>
      <h2>Quick check-in</h2>
      <div>
        {tasks.slice(0, 9).map((t) => (
          <button
            key={t.id}
            className={t.state === "completed" ? "active" : ""}
            onClick={() =>
              mutate({
                id: t.id,
                kind: t.state === "completed" ? "undo" : "complete",
              })
            }
          >
            <HabitIcon name={t.icon} />
            <span>{t.name.split(" ")[0]}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
function Week() {
  const q = useQuery({ queryKey: ["week"], queryFn: () => api<any>("/week") });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  return (
    <div className="page">
      <PageTitle
        eyebrow="Weekly rhythm"
        title="A wider view"
        copy="One missed day does not erase the pattern you are building."
      />
      <div className="week-grid">
        {q.data.days.map((d: any) => (
          <article key={d.date} className={d.mode.flexible ? "relaxed" : ""}>
            <div>
              <span>{d.label}</span>
              <strong>{d.day}</strong>
            </div>
            <b>{d.completion}%</b>
            <div className="mini-progress">
              <i style={{ height: `${d.completion}%` }} />
            </div>
            <ul>
              {[
                ["movement", "Move"],
                ["hydration", "Water"],
                ["nutrition", "Meals"],
                ["sleep", "Sleep"],
                ["weight", "Weight"],
              ].map(([k, label]) => (
                <li key={k} className={d[k] ? "yes" : ""}>
                  <span>{d[k] ? "✓" : "·"}</span>
                  {label}
                </li>
              ))}
            </ul>
            <small>{d.mode.name}</small>
          </article>
        ))}
      </div>
      <div className="summary-grid">
        <section className="panel">
          <span className="eyebrow">What went well</span>
          <h3>Progress survived real life</h3>
          <p>{q.data.summary}</p>
        </section>
        <section className="panel">
          <span className="eyebrow">Try next week</span>
          <h3>Plan the easier option</h3>
          <p>{q.data.suggestion}</p>
        </section>
      </div>
    </div>
  );
}
function Progress() {
  const [range, setRange] = useState("30");
  const [weightOpen, setWeightOpen] = useState(false);
  const [editingWeight, setEditingWeight] = useState<WeightEntry | null>(null);
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["progress", range],
    queryFn: () => api<ProgressData>(`/progress?range=${range}`),
  });
  const data = q.data;
  const openNewWeight = () => {
    setEditingWeight(null);
    setWeightOpen(true);
  };
  const openWeightEditor = (entry: WeightEntry) => {
    setEditingWeight(entry);
    setWeightOpen(true);
  };
  const deleteWeight = async (entry: WeightEntry) => {
    if (!confirm(`Delete the ${entry.date} weight reading?`)) return;
    await api(`/weight/${entry.id}`, { method: "DELETE" });
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["today"] }),
      qc.invalidateQueries({ queryKey: ["progress"] }),
      qc.invalidateQueries({ queryKey: ["week"] }),
    ]);
  };
  return (
    <div className="page">
      <PageTitle
        eyebrow="Trends, not judgment"
        title="Progress"
        copy="Individual readings are noisy. The longer view is what matters."
      />
      <div className="tabs">
        {["7", "30", "90", "all"].map((x) => (
          <button
            className={range === x ? "active" : ""}
            onClick={() => setRange(x)}
            key={x}
          >
            {x === "all" ? "All time" : `${x} days`}
          </button>
        ))}
      </div>
      {q.error ? (
        <ErrorBox error={q.error} />
      ) : q.isLoading || !data ? (
        <Loading />
      ) : (
        <>
          <section className="weight-goal-card">
            <div className="weight-goal-heading">
              <span className="weight-goal-icon">
                <Scale size={22} />
              </span>
              <div>
                <span className="eyebrow">Weight goal</span>
                <h2>
                  {data.weight_goal.current} <small>kg</small>
                  <i>→</i>
                  {data.weight_goal.goal} <small>kg</small>
                </h2>
              </div>
              <button onClick={openNewWeight}>
                <Plus size={16} /> Record weight
              </button>
            </div>
            <div className="goal-progress-copy">
              <strong>{data.weight_goal.progress}% complete</strong>
              <span>{data.weight_goal.remaining} kg remaining</span>
            </div>
            <div className="goal-progress-bar">
              <i style={{ width: `${data.weight_goal.progress}%` }} />
            </div>
            <div className="goal-details">
              <span>
                Started at <b>{data.weight_goal.start} kg</b>
              </span>
              <span>
                Change <b>{data.weight_goal.change} kg</b>
              </span>
              <span>
                Last recorded{" "}
                <b>{data.weight_goal.last_recorded || "Not yet"}</b>
              </span>
            </div>
            <div className="milestone-row" aria-label="Weight milestones">
              {data.weight_goal.milestones.map((milestone) => (
                <span
                  key={milestone}
                  className={
                    data.weight_goal.current <= milestone ? "reached" : ""
                  }
                >
                  {data.weight_goal.current <= milestone && <Check size={12} />}
                  {milestone} kg
                </span>
              ))}
            </div>
          </section>
          <div className="metric-cards">
            <div>
              <span>Movement</span>
              <strong>{data.summary.exercise_minutes}</strong>
              <small>minutes</small>
            </div>
            <div>
              <span>Average sleep</span>
              <strong>{data.summary.average_sleep}</strong>
              <small>hours</small>
            </div>
          </div>
          <Chart
            title="Weight trend"
            summary="Weight readings with a seven-entry moving average."
            empty={!data.weight.length}
          >
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={data.weight}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" hide />
                <YAxis domain={["dataMin - 1", "dataMax + 1"]} width={35} />
                <Tooltip />
                <Line dataKey="weight" stroke="#9aa6a0" dot />
                <Line
                  dataKey="average"
                  stroke="#3b7c67"
                  strokeWidth={3}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </Chart>
          {data.weight.length > 0 && (
            <section className="weight-history panel">
              <div className="weight-history-heading">
                <div>
                  <span className="eyebrow">Recorded weights</span>
                  <h3>Readings in this range</h3>
                </div>
                <small>Edit or remove any incorrect reading.</small>
              </div>
              <div className="weight-entry-list">
                {[...data.weight].reverse().map((entry) => (
                  <article key={entry.id}>
                    <div>
                      <strong>{entry.weight} kg</strong>
                      <span>{entry.date}</span>
                    </div>
                    <p>
                      {entry.waist_cm ? `Waist ${entry.waist_cm} cm` : ""}
                      {entry.waist_cm && entry.notes ? " · " : ""}
                      {entry.notes ||
                        (!entry.waist_cm ? "No additional details" : "")}
                    </p>
                    <div className="weight-entry-actions">
                      <button
                        onClick={() => openWeightEditor(entry)}
                        aria-label={`Edit weight from ${entry.date}`}
                        title="Edit"
                      >
                        <Pencil size={15} />
                      </button>
                      <button
                        onClick={() => deleteWeight(entry)}
                        aria-label={`Delete weight from ${entry.date}`}
                        title="Delete"
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          )}
          <Chart
            title="Sleep duration"
            summary="Daily sleep duration in hours."
            empty={!data.sleep.length}
          >
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={data.sleep}>
                <XAxis dataKey="date" hide />
                <YAxis domain={[0, 10]} width={28} />
                <Tooltip />
                <Area dataKey="hours" stroke="#5a719c" fill="#dce6f5" />
              </AreaChart>
            </ResponsiveContainer>
          </Chart>
          <Chart
            title="Exercise minutes"
            summary="Minutes of intentional movement by session."
            empty={!data.exercise.length}
          >
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={data.exercise}>
                <XAxis dataKey="date" hide />
                <YAxis width={28} />
                <Tooltip />
                <Bar dataKey="minutes" fill="#83ab94" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Chart>
          {weightOpen && (
            <WeightCheckIn
              currentWeight={data.weight_goal.current}
              entry={editingWeight}
              onClose={() => {
                setWeightOpen(false);
                setEditingWeight(null);
              }}
            />
          )}
        </>
      )}
    </div>
  );
}

type ProgressData = {
  weight: WeightEntry[];
  weight_goal: {
    start: number;
    current: number;
    goal: number;
    change: number;
    remaining: number;
    progress: number;
    last_recorded: string | null;
    milestones: number[];
  };
  sleep: { date: string; hours: number; quality: number }[];
  exercise: { date: string; minutes: number; activity: string }[];
  summary: { exercise_minutes: number; average_sleep: number };
};
function Chart({
  title,
  summary,
  empty,
  children,
}: {
  title: string;
  summary: string;
  empty: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className="chart">
      <h3>{title}</h3>
      <p className="sr-only">{summary}</p>
      {empty ? (
        <div className="empty">
          <Activity />
          <p>Your trend will appear after a few check-ins.</p>
        </div>
      ) : (
        children
      )}
    </section>
  );
}
function Plan() {
  const qc = useQueryClient();
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [draft, setDraft] = useState<PlanDraft>(() => emptyPlanDraft());
  const [message, setMessage] = useState("");
  const q = useQuery({
    queryKey: ["plan"],
    queryFn: () => api<PlanHabit[]>("/plan"),
  });
  const toggle = useMutation({
    mutationFn: ({ id, paused }: { id: number; paused: boolean }) =>
      api(`/plan/${id}`, { method: "PUT", body: JSON.stringify({ paused }) }),
    onSuccess: () => invalidatePlan(qc),
  });

  const openNew = () => {
    setEditingId(null);
    setDraft(emptyPlanDraft());
    setMessage("");
    setEditorOpen(true);
  };

  const openEdit = (habit: PlanHabit) => {
    setEditingId(habit.id);
    setDraft({
      name: habit.name,
      description: habit.description,
      category: habit.category,
      suggested_time: habit.suggested_time || "",
      required: habit.required,
      minimum_label: habit.minimum_label || "",
      days: habit.days,
    });
    setMessage("");
    setEditorOpen(true);
  };

  const savePlanEntry = async (event: React.FormEvent) => {
    event.preventDefault();
    setMessage("");
    if (!draft.days.length) {
      setMessage("Choose at least one day.");
      return;
    }
    const payload = {
      ...draft,
      suggested_time: draft.suggested_time || null,
      minimum_label: draft.minimum_label || null,
    };
    try {
      await api(editingId === null ? "/plan" : `/plan/${editingId}`, {
        method: editingId === null ? "POST" : "PUT",
        body: JSON.stringify(payload),
      });
      setEditorOpen(false);
      await invalidatePlan(qc);
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not save this entry",
      );
    }
  };

  const archiveEntry = async (habit: PlanHabit) => {
    if (
      !confirm(
        `Remove “${habit.name}” from your plan? Past check-ins will be preserved.`,
      )
    )
      return;
    await api(`/plan/${habit.id}`, { method: "DELETE" });
    if (editingId === habit.id) setEditorOpen(false);
    await invalidatePlan(qc);
  };

  return (
    <div className="page">
      <div className="plan-heading">
        <PageTitle
          eyebrow="Make it yours"
          title="Your plan"
          copy="The routine should fit your life. Edit, pause, or add anything that helps."
        />
        <button className="add-plan" onClick={openNew}>
          <Plus size={17} /> Add entry
        </button>
      </div>
      {(() => {
        const editor = (
          <form className="plan-editor form-section" onSubmit={savePlanEntry}>
            <div className="form-heading plan-editor-heading">
              <div>
                <span className="eyebrow">
                  {editingId === null ? "New entry" : "Edit entry"}
                </span>
                <h3>
                  {editingId === null
                    ? "Add to your plan"
                    : "Update this routine"}
                </h3>
              </div>
              <button
                type="button"
                className="icon-button"
                onClick={() => setEditorOpen(false)}
                aria-label="Close editor"
              >
                <X size={18} />
              </button>
            </div>
            <div className="field-grid">
              <label>
                Name
                <input
                  value={draft.name}
                  onChange={(event) =>
                    setDraft({ ...draft, name: event.target.value })
                  }
                  placeholder="Evening walk"
                  required
                />
              </label>
              <label>
                Category
                <select
                  value={draft.category}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      category: event.target.value as PlanCategory,
                    })
                  }
                >
                  {PLAN_CATEGORIES.map((category) => (
                    <option key={category} value={category}>
                      {category[0].toUpperCase() + category.slice(1)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="wide-field">
                Description
                <textarea
                  value={draft.description}
                  onChange={(event) =>
                    setDraft({ ...draft, description: event.target.value })
                  }
                  placeholder="A short description of what counts."
                  rows={3}
                />
              </label>
              <label>
                Suggested time
                <input
                  type="time"
                  value={draft.suggested_time}
                  onChange={(event) =>
                    setDraft({ ...draft, suggested_time: event.target.value })
                  }
                />
              </label>
              <label>
                Minimum version
                <input
                  value={draft.minimum_label}
                  onChange={(event) =>
                    setDraft({ ...draft, minimum_label: event.target.value })
                  }
                  placeholder="Walk for 5 minutes"
                />
              </label>
            </div>
            <fieldset className="weekday-field">
              <legend>Repeat on</legend>
              <div>
                {WEEKDAYS.map((day, index) => (
                  <button
                    key={day}
                    type="button"
                    className={draft.days.includes(index) ? "active" : ""}
                    aria-pressed={draft.days.includes(index)}
                    onClick={() =>
                      setDraft({
                        ...draft,
                        days: draft.days.includes(index)
                          ? draft.days.filter((value) => value !== index)
                          : [...draft.days, index].sort(),
                      })
                    }
                  >
                    {day.slice(0, 2)}
                  </button>
                ))}
              </div>
            </fieldset>
            <label className="core-toggle">
              <input
                type="checkbox"
                checked={draft.required}
                onChange={(event) =>
                  setDraft({ ...draft, required: event.target.checked })
                }
              />
              <span>
                <strong>Core habit</strong>
                <small>
                  Core entries count toward your daily completion score.
                </small>
              </span>
            </label>
            <div className="plan-editor-actions">
              <button type="submit">
                {editingId === null ? "Add to plan" : "Save changes"}
              </button>
              <button
                type="button"
                className="quiet-button"
                onClick={() => setEditorOpen(false)}
              >
                Cancel
              </button>
              {message && <p role="alert">{message}</p>}
            </div>
          </form>
        );

        return (
          <>
            {editorOpen && editingId === null && editor}
            {q.isLoading ? (
              <Loading />
            ) : q.error ? (
              <ErrorBox error={q.error} />
            ) : (
              <div className="plan-list">
                {q.data?.map((h) =>
                  editorOpen && editingId === h.id ? (
                    <div className="plan-editor-slot" key={h.id}>
                      {editor}
                    </div>
                  ) : (
                    <article key={h.id} className={h.paused ? "paused" : ""}>
                      <div className={`category ${h.category}`}>
                        <HabitIcon
                          name={
                            h.category === "movement"
                              ? "activity"
                              : h.category === "sleep"
                                ? "moon"
                                : h.category === "nutrition"
                                  ? "utensils"
                                  : h.category === "hydration"
                                    ? "droplets"
                                    : "clipboard-check"
                          }
                        />
                      </div>
                      <div>
                        <strong>{h.name}</strong>
                        <p>{h.description}</p>
                        <small>
                          {h.suggested_time} ·{" "}
                          {h.required ? "Core habit" : "Optional"} ·{" "}
                          {h.days
                            .map((day) => WEEKDAYS[day].slice(0, 3))
                            .join(", ")}
                        </small>
                      </div>
                      <div className="plan-card-actions">
                        <label
                          className="switch"
                          title={h.paused ? "Resume entry" : "Pause entry"}
                        >
                          <input
                            type="checkbox"
                            checked={!h.paused}
                            onChange={() =>
                              toggle.mutate({ id: h.id, paused: !h.paused })
                            }
                          />
                          <span />
                        </label>
                        <button
                          onClick={() => openEdit(h)}
                          aria-label={`Edit ${h.name}`}
                          title="Edit"
                        >
                          <Pencil size={16} />
                        </button>
                        <button
                          onClick={() => archiveEntry(h)}
                          aria-label={`Remove ${h.name}`}
                          title="Remove"
                        >
                          <Archive size={16} />
                        </button>
                      </div>
                    </article>
                  ),
                )}
              </div>
            )}
          </>
        );
      })()}
      <button
        className="danger-quiet"
        onClick={() =>
          confirm(
            "Reset the routine to Health OS defaults? Historical check-ins are preserved in exports.",
          ) &&
          post("/plan/reset").then(() =>
            qc.invalidateQueries({ queryKey: ["plan"] }),
          )
        }
      >
        <RotateCcw size={16} /> Reset to defaults
      </button>
    </div>
  );
}

const WEEKDAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];
const PLAN_CATEGORIES = [
  "movement",
  "hydration",
  "nutrition",
  "sleep",
  "weight",
  "planning",
] as const;
type PlanCategory = (typeof PLAN_CATEGORIES)[number];
type PlanHabit = {
  id: number;
  name: string;
  description: string;
  category: PlanCategory;
  suggested_time: string | null;
  required: boolean;
  minimum_label: string | null;
  paused: boolean;
  days: number[];
};
type PlanDraft = {
  name: string;
  description: string;
  category: PlanCategory;
  suggested_time: string;
  required: boolean;
  minimum_label: string;
  days: number[];
};
const emptyPlanDraft = (): PlanDraft => ({
  name: "",
  description: "",
  category: "planning",
  suggested_time: "",
  required: true,
  minimum_label: "",
  days: [0, 1, 2, 3, 4],
});
const invalidatePlan = (qc: ReturnType<typeof useQueryClient>) =>
  Promise.all([
    qc.invalidateQueries({ queryKey: ["plan"] }),
    qc.invalidateQueries({ queryKey: ["today"] }),
    qc.invalidateQueries({ queryKey: ["week"] }),
  ]);
function Settings() {
  const q = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<AppSettings>("/settings"),
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  return <SettingsEditor initial={q.data!} />;
}

function HouseholdPanel() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [removingId, setRemovingId] = useState<number | null>(null);
  const [form, setForm] = useState({
    display_name: "",
    pin: "",
  });
  const members = useQuery({
    queryKey: ["household"],
    queryFn: () =>
      api<
        {
          id: number;
          display_name: string;
          timezone: string;
          is_admin: boolean;
          must_change_pin: boolean;
        }[]
      >("/household"),
  });
  const add = async (event: React.FormEvent) => {
    event.preventDefault();
    setMessage("");
    try {
      await post("/household", form);
      setOpen(false);
      setForm({ display_name: "", pin: "" });
      await qc.invalidateQueries({ queryKey: ["household"] });
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not add this member",
      );
    }
  };
  const remove = async (member: { id: number; display_name: string }) => {
    if (
      !confirm(
        `Remove ${member.display_name} and all of their health data from this server? This cannot be undone.`,
      )
    )
      return;
    setMessage("");
    setRemovingId(member.id);
    try {
      await api(`/household/${member.id}`, { method: "DELETE" });
      await qc.invalidateQueries({ queryKey: ["household"] });
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not remove this member",
      );
    } finally {
      setRemovingId(null);
    }
  };
  return (
    <section className="form-section household-panel">
      <div className="household-heading">
        <div>
          <span className="eyebrow">Household</span>
          <h3>People on this server</h3>
          <p>Each PIN opens a separate dashboard, plan, and health history.</p>
        </div>
        <button type="button" onClick={() => setOpen(!open)}>
          <Plus size={16} /> Add member
        </button>
      </div>
      {open && (
        <form className="household-form" onSubmit={add}>
          <div className="field-grid">
            <label>
              Name
              <input
                value={form.display_name}
                onChange={(e) =>
                  setForm({ ...form, display_name: e.target.value })
                }
                required
              />
            </label>
            <label>
              Temporary PIN
              <input
                type="password"
                inputMode="numeric"
                minLength={4}
                value={form.pin}
                onChange={(e) => setForm({ ...form, pin: e.target.value })}
                required
              />
              <small>They’ll replace this after their first sign-in.</small>
            </label>
          </div>
          <div className="save-row">
            <button type="submit">Create member</button>
            <button
              type="button"
              className="quiet-button"
              onClick={() => setOpen(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      )}
      {message && (
        <p className="form-error" role="alert">
          {message}
        </p>
      )}
      <div className="member-list">
        {members.data?.map((member) => (
          <div key={member.id}>
            <span className="member-avatar">
              {member.display_name.slice(0, 1).toUpperCase()}
            </span>
            <span>
              <strong>{member.display_name}</strong>
              <small>
                {member.timezone}
                {member.must_change_pin ? " · Awaiting first sign-in" : ""}
              </small>
            </span>
            {member.is_admin ? (
              <i>Admin</i>
            ) : (
              <button
                type="button"
                className="icon-button member-remove"
                aria-label={`Remove ${member.display_name}`}
                title="Remove member"
                disabled={removingId === member.id}
                onClick={() => remove(member)}
              >
                {removingId === member.id ? (
                  <LoaderCircle className="spin" size={16} />
                ) : (
                  <Trash2 size={16} />
                )}
              </button>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

type AppSettings = {
  display_name: string;
  starting_weight_kg: number;
  timezone: string;
  caffeine_cutoff: string;
  water_target_ml: number;
  weight_milestones: number[];
  allow_embedding: boolean;
  embedding_origins: string[];
  pin_configured: boolean;
  is_admin: boolean;
  photo_uploads_enabled: boolean;
};

function SettingsEditor({ initial }: { initial: AppSettings }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    ...initial,
    weight_milestones: initial.weight_milestones.join(", "),
    embedding_origins: initial.embedding_origins.join("\n"),
  });
  const [currentPin, setCurrentPin] = useState("");
  const [newPin, setNewPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [pinConfigured, setPinConfigured] = useState(initial.pin_configured);
  const [message, setMessage] = useState("");
  const [pinMessage, setPinMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (key: string, value: string | number | boolean) =>
    setForm((current) => ({ ...current, [key]: value }));

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const payload = {
        ...form,
        starting_weight_kg: Number(form.starting_weight_kg),
        water_target_ml: Number(form.water_target_ml),
        weight_milestones: form.weight_milestones
          .split(",")
          .map((value) => Number(value.trim()))
          .filter((value) => Number.isFinite(value)),
        embedding_origins: form.embedding_origins
          .split(/[\n,]+/)
          .map((value) => value.trim())
          .filter(Boolean),
      };
      const result = await api<{ message: string }>("/settings", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      setMessage(result.message);
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["settings"] }),
        qc.invalidateQueries({ queryKey: ["today"] }),
        qc.invalidateQueries({ queryKey: ["week"] }),
      ]);
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not save settings",
      );
    } finally {
      setBusy(false);
    }
  };

  const changePin = async (event: React.FormEvent) => {
    event.preventDefault();
    setPinMessage("");
    if (newPin !== confirmPin) {
      setPinMessage("The new PIN entries do not match.");
      return;
    }
    setBusy(true);
    try {
      const result = await api<{ message: string }>("/auth/pin", {
        method: "PUT",
        body: JSON.stringify({
          current_pin: pinConfigured ? currentPin : null,
          new_pin: newPin,
        }),
      });
      setPinMessage(result.message);
      setCurrentPin("");
      setNewPin("");
      setConfirmPin("");
      setPinConfigured(true);
      await qc.invalidateQueries({ queryKey: ["settings"] });
    } catch (error) {
      setPinMessage(
        error instanceof Error ? error.message : "Could not update PIN",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <PageTitle
        eyebrow="Make Health OS yours"
        title="Settings"
        copy="Your preferences are stored privately on this server and take effect immediately."
      />
      <form className="settings-form" onSubmit={save}>
        <section className="form-section">
          <div className="form-heading">
            <span className="eyebrow">Daily preferences</span>
            <h3>Schedule and targets</h3>
            <p>
              Personal baselines for your progress, hydration, and future
              notifications. Task times are managed in your Plan.
            </p>
          </div>
          <div className="field-grid">
            <label>
              Display name
              <input
                value={form.display_name}
                onChange={(event) => set("display_name", event.target.value)}
                required
              />
            </label>
            <label>
              Starting weight (kg)
              <input
                type="number"
                min="20"
                max="400"
                step="0.1"
                value={form.starting_weight_kg}
                onChange={(event) =>
                  set("starting_weight_kg", event.target.value)
                }
                required
              />
              <small>Used as the baseline for goal progress.</small>
            </label>
            <label>
              Timezone
              <TimezoneSelect
                value={form.timezone}
                onChange={(value) => set("timezone", value)}
              />
            </label>
            <label>
              Caffeine cutoff
              <input
                type="time"
                value={form.caffeine_cutoff}
                onChange={(event) => set("caffeine_cutoff", event.target.value)}
                required
              />
            </label>
            <label>
              Daily water target (ml)
              <input
                type="number"
                min="250"
                max="10000"
                step="50"
                value={form.water_target_ml}
                onChange={(event) => set("water_target_ml", event.target.value)}
                required
              />
            </label>
            <label className="wide-field">
              Weight milestones (kg)
              <input
                value={form.weight_milestones}
                onChange={(event) =>
                  set("weight_milestones", event.target.value)
                }
                placeholder="94, 90, 88, 85"
                required
              />
              <small>Separate milestones with commas, highest to lowest.</small>
            </label>
          </div>
        </section>

        {form.is_admin && (
          <section className="form-section">
            <div className="form-heading">
              <span className="eyebrow">External display</span>
              <h3>Allow Embedding</h3>
              <p>
                Permit trusted dashboards, wall displays, or other local sites
                to show Health OS inside a frame.
              </p>
            </div>
            <label className="toggle-row">
              <span>
                <strong>Allow Health OS to be embedded</strong>
                <small>
                  Only the exact origins listed below will be permitted.
                </small>
              </span>
              <span className="switch">
                <input
                  type="checkbox"
                  checked={form.allow_embedding}
                  onChange={(event) =>
                    set("allow_embedding", event.target.checked)
                  }
                />
                <span />
              </span>
            </label>
            {form.allow_embedding && (
              <label className="origin-field">
                Permitted origins
                <textarea
                  rows={4}
                  value={form.embedding_origins}
                  onChange={(event) =>
                    set("embedding_origins", event.target.value)
                  }
                  placeholder={
                    "http://dashboard.local:8123\nhttps://display.example.internal"
                  }
                  required
                />
                <small>
                  One origin per line, including http:// or https:// and its
                  port.
                </small>
              </label>
            )}
          </section>
        )}

        <div className="save-row">
          <button type="submit" disabled={busy}>
            {busy ? "Saving…" : "Save settings"}
          </button>
          {message && <p role="status">{message}</p>}
        </div>
      </form>

      <form className="form-section pin-form" onSubmit={changePin}>
        <div className="form-heading">
          <span className="eyebrow">Access protection</span>
          <h3>{pinConfigured ? "Change PIN" : "Set a PIN"}</h3>
          <p>The PIN is stored only as a secure Argon2 hash.</p>
        </div>
        <div className="field-grid">
          {pinConfigured && (
            <label>
              Current PIN
              <input
                type="password"
                inputMode="numeric"
                value={currentPin}
                onChange={(event) => setCurrentPin(event.target.value)}
                required
              />
            </label>
          )}
          <label>
            New PIN
            <input
              type="password"
              inputMode="numeric"
              minLength={4}
              value={newPin}
              onChange={(event) => setNewPin(event.target.value)}
              required
            />
          </label>
          <label>
            Confirm new PIN
            <input
              type="password"
              inputMode="numeric"
              minLength={4}
              value={confirmPin}
              onChange={(event) => setConfirmPin(event.target.value)}
              required
            />
          </label>
        </div>
        <div className="save-row">
          <button type="submit" disabled={busy || newPin.length < 4}>
            Update PIN
          </button>
          {pinMessage && <p role="status">{pinMessage}</p>}
        </div>
      </form>

      {form.is_admin && <HouseholdPanel />}

      <section className="panel">
        <h3>Your data</h3>
        <p>Download portable copies whenever you like.</p>
        <div className="button-row">
          <a href="/api/export/json" download="health-os-data.json">
            JSON export
          </a>
          <a href="/api/export/weight.csv">Weight CSV</a>
          <a href="/api/export/sleep.csv">Sleep CSV</a>
        </div>
      </section>
    </div>
  );
}
function PageTitle({
  eyebrow,
  title,
  copy,
}: {
  eyebrow: string;
  title: string;
  copy: string;
}) {
  return (
    <header className="page-title">
      <span className="eyebrow">{eyebrow}</span>
      <h1>{title}</h1>
      <p>{copy}</p>
    </header>
  );
}
function Onboarding() {
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    display_name: "",
    timezone: detectedTimezone,
    starting_weight_kg: "",
    height_cm: "",
    water_target_ml: "2000",
    pin: "",
    confirm_pin: "",
  });
  const set = (key: string, value: string) =>
    setForm((current) => ({ ...current, [key]: value }));
  const next = (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    if (step < 3) {
      setStep(step + 1);
      return;
    }
    if (form.pin !== form.confirm_pin) {
      setError("The PIN entries do not match.");
      return;
    }
    setBusy(true);
    post("/onboarding", {
      display_name: form.display_name,
      timezone: form.timezone,
      starting_weight_kg: Number(form.starting_weight_kg),
      height_cm: form.height_cm ? Number(form.height_cm) : null,
      water_target_ml: Number(form.water_target_ml),
      pin: form.pin,
    })
      .then(() => location.reload())
      .catch((reason) => {
        setError(reason.message);
        setBusy(false);
      });
  };
  return (
    <main className="onboarding-shell">
      <section className="onboarding-card">
        <div className="onboarding-brand">
          <span>
            <HeartPulse />
          </span>
          <div>
            <strong>Health OS</strong>
            <small>steady, not strict</small>
          </div>
        </div>
        <div className="onboarding-progress" aria-label={`Step ${step} of 3`}>
          {[1, 2, 3].map((value) => (
            <i key={value} className={value <= step ? "active" : ""} />
          ))}
        </div>
        <form onSubmit={next}>
          {step === 1 && (
            <>
              <span className="eyebrow">Step 1 of 3 · About you</span>
              <h1>Let’s make this yours.</h1>
              <p>
                Your name and timezone keep each household member’s day
                personal.
              </p>
              <div className="field-grid onboarding-fields">
                <label className="wide-field">
                  Your name
                  <input
                    autoFocus
                    value={form.display_name}
                    onChange={(e) => set("display_name", e.target.value)}
                    required
                  />
                </label>
                <label className="wide-field">
                  Timezone
                  <TimezoneSelect
                    value={form.timezone}
                    onChange={(value) => set("timezone", value)}
                  />
                </label>
              </div>
            </>
          )}
          {step === 2 && (
            <>
              <span className="eyebrow">Step 2 of 3 · Starting point</span>
              <h1>Set gentle targets.</h1>
              <p>These are private baselines. You can change them anytime.</p>
              <div className="field-grid onboarding-fields">
                <label>
                  Starting weight (kg)
                  <input
                    autoFocus
                    type="number"
                    min="20"
                    max="400"
                    step="0.1"
                    value={form.starting_weight_kg}
                    onChange={(e) => set("starting_weight_kg", e.target.value)}
                    required
                  />
                </label>
                <label>
                  Height (cm, optional)
                  <input
                    type="number"
                    min="80"
                    max="250"
                    step="0.1"
                    value={form.height_cm}
                    onChange={(e) => set("height_cm", e.target.value)}
                  />
                </label>
                <label className="wide-field">
                  Daily water target (ml)
                  <input
                    type="number"
                    min="250"
                    max="10000"
                    step="50"
                    value={form.water_target_ml}
                    onChange={(e) => set("water_target_ml", e.target.value)}
                    required
                  />
                </label>
              </div>
            </>
          )}
          {step === 3 && (
            <>
              <span className="eyebrow">Step 3 of 3 · Private access</span>
              <h1>Choose your PIN.</h1>
              <p>This PIN identifies you and opens only your dashboard.</p>
              <div className="field-grid onboarding-fields">
                <label>
                  PIN
                  <input
                    autoFocus
                    type="password"
                    inputMode="numeric"
                    minLength={4}
                    value={form.pin}
                    onChange={(e) => set("pin", e.target.value)}
                    required
                  />
                </label>
                <label>
                  Confirm PIN
                  <input
                    type="password"
                    inputMode="numeric"
                    minLength={4}
                    value={form.confirm_pin}
                    onChange={(e) => set("confirm_pin", e.target.value)}
                    required
                  />
                </label>
              </div>
            </>
          )}
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <div className="onboarding-actions">
            {step > 1 && (
              <button
                type="button"
                className="quiet-button"
                onClick={() => setStep(step - 1)}
              >
                Back
              </button>
            )}
            <button type="submit" disabled={busy}>
              {step === 3
                ? busy
                  ? "Creating your space..."
                  : "Open my dashboard"
                : "Continue"}
              <ArrowRight size={17} />
            </button>
          </div>
        </form>
        <small className="onboarding-privacy">
          <ShieldCheck size={14} /> Every household member gets a separate
          private space.
        </small>
      </section>
    </main>
  );
}
function MemberSetupWizard({ name }: { name: string }) {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({
    timezone: detectedTimezone,
    starting_weight_kg: "",
    height_cm: "",
    water_target_ml: "2000",
  });
  const [pin, setPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const save = (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    if (pin !== confirmPin) {
      setError("The PIN entries do not match.");
      return;
    }
    setBusy(true);
    api("/household/complete-setup", {
      method: "PUT",
      body: JSON.stringify({
        timezone: form.timezone,
        starting_weight_kg: Number(form.starting_weight_kg),
        height_cm: form.height_cm ? Number(form.height_cm) : null,
        water_target_ml: Number(form.water_target_ml),
        new_pin: pin,
      }),
    })
      .then(() => location.reload())
      .catch((reason) => {
        setError(reason.message);
        setBusy(false);
      });
  };
  return (
    <main className="onboarding-shell">
      <section className="onboarding-card first-pin-card">
        <div className="onboarding-brand">
          <span>
            <LockKeyhole />
          </span>
          <div>
            <strong>Welcome, {name}</strong>
            <small>Your private Health OS space</small>
          </div>
        </div>
        <form onSubmit={save}>
          <div className="onboarding-progress" aria-label="Setup progress">
            {[0, 1, 2].map((index) => (
              <i key={index} className={index <= step ? "active" : ""} />
            ))}
          </div>
          {step === 0 && (
            <>
              <span className="eyebrow">Your local rhythm</span>
              <h1>Set your timezone.</h1>
              <p>
                We use this to show each day and task at the right time for you.
              </p>
              <div className="field-grid onboarding-fields">
                <label>
                  Timezone
                  <TimezoneSelect
                    autoFocus
                    value={form.timezone}
                    onChange={(value) => setForm({ ...form, timezone: value })}
                  />
                </label>
              </div>
            </>
          )}
          {step === 1 && (
            <>
              <span className="eyebrow">Your starting point</span>
              <h1>Add your health baseline.</h1>
              <p>
                These values make your progress and daily water goal personal.
              </p>
              <div className="field-grid onboarding-fields">
                <label>
                  Starting weight (kg)
                  <input
                    autoFocus
                    type="number"
                    min="20.1"
                    max="399.9"
                    step="0.1"
                    value={form.starting_weight_kg}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        starting_weight_kg: event.target.value,
                      })
                    }
                    required
                  />
                </label>
                <label>
                  Height (cm, optional)
                  <input
                    type="number"
                    min="80.1"
                    max="249.9"
                    step="0.1"
                    value={form.height_cm}
                    onChange={(event) =>
                      setForm({ ...form, height_cm: event.target.value })
                    }
                  />
                </label>
                <label>
                  Daily water target (ml)
                  <input
                    type="number"
                    min="250"
                    max="10000"
                    step="50"
                    value={form.water_target_ml}
                    onChange={(event) =>
                      setForm({ ...form, water_target_ml: event.target.value })
                    }
                    required
                  />
                </label>
              </div>
            </>
          )}
          {step === 2 && (
            <>
              <span className="eyebrow">Your private access</span>
              <h1>Choose your own PIN.</h1>
              <p>Replace the temporary household PIN with one only you know.</p>
              <div className="field-grid onboarding-fields">
                <label>
                  New PIN
                  <input
                    autoFocus
                    type="password"
                    inputMode="numeric"
                    minLength={4}
                    value={pin}
                    onChange={(event) => setPin(event.target.value)}
                    required
                  />
                </label>
                <label>
                  Confirm new PIN
                  <input
                    type="password"
                    inputMode="numeric"
                    minLength={4}
                    value={confirmPin}
                    onChange={(event) => setConfirmPin(event.target.value)}
                    required
                  />
                </label>
              </div>
            </>
          )}
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <div className="onboarding-actions">
            {step > 0 && (
              <button
                type="button"
                className="quiet-button"
                onClick={() => setStep(step - 1)}
              >
                Back
              </button>
            )}
            {step < 2 ? (
              <button
                type="button"
                disabled={
                  (step === 0 && !form.timezone.trim()) ||
                  (step === 1 && !form.starting_weight_kg)
                }
                onClick={() => setStep(step + 1)}
              >
                Continue <ArrowRight size={17} />
              </button>
            ) : (
              <button disabled={busy || pin.length < 4}>
                {busy ? "Saving..." : "Open my dashboard"}
                <ArrowRight size={17} />
              </button>
            )}
          </div>
        </form>
        <small className="onboarding-privacy">
          <ShieldCheck size={14} /> Your new PIN remains private and securely
          hashed.
        </small>
      </section>
    </main>
  );
}
function Login() {
  const [pin, setPin] = useState("");
  const [keep, setKeep] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <main className="login-shell">
      <section className="login-card">
        <div className="login-welcome">
          <div className="login-brand">
            <span className="login-logo">
              <HeartPulse />
            </span>
            <span>
              <strong>Health OS</strong>
              <small>steady, not strict</small>
            </span>
          </div>
          <div className="login-welcome-copy">
            <span className="eyebrow">Your private health space</span>
            <h1>Welcome back.</h1>
            <p>
              A quiet place to check in, notice patterns, and keep moving
              forward.
            </p>
          </div>
          <p className="login-privacy">
            <ShieldCheck size={17} /> Your health data stays on your server.
          </p>
        </div>
        <div className="login-access">
          <div className="login-access-heading">
            <span className="login-lock">
              <LockKeyhole size={19} />
            </span>
            <div>
              <span className="eyebrow">Protected access</span>
              <h2>Open your dashboard</h2>
            </div>
          </div>
          <p className="login-instruction">
            Your dashboard is locked to keep your health data private.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              post("/auth/login", { pin, keep_signed_in: keep })
                .then(() => location.reload())
                .catch((e) => {
                  setError(e.message);
                  setBusy(false);
                });
            }}
          >
            <label className="pin-field">
              <span className="sr-only">PIN</span>
              <span className="pin-input-wrap">
                <LockKeyhole size={18} aria-hidden="true" />
                <input
                  type="password"
                  inputMode="numeric"
                  autoComplete="current-password"
                  autoFocus
                  value={pin}
                  onChange={(e) => setPin(e.target.value)}
                  placeholder="PIN"
                />
              </span>
            </label>
            <div className="login-options">
              <label className="keep">
                <input
                  type="checkbox"
                  checked={keep}
                  onChange={(e) => setKeep(e.target.checked)}
                />
                <span>Keep me signed in</span>
              </label>
            </div>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <button disabled={busy || pin.length < 4}>
              <span>{busy ? "Opening…" : "Continue"}</span>
              {!busy && <ArrowRight size={18} />}
            </button>
          </form>
          <p className="login-footnote">
            <ShieldCheck size={14} /> Your PIN is verified locally and never
            leaves your server.
          </p>
        </div>
      </section>
    </main>
  );
}
export default function App() {
  const auth = useQuery({
    queryKey: ["auth"],
    queryFn: () => api<any>("/auth/status"),
  });
  const [view, setView] = useState<View>("today");
  const embedded =
    new URLSearchParams(location.search).get("embedded") === "true";
  const lockDashboard = () =>
    post("/auth/logout").then(() => location.reload());
  if (auth.isLoading) return <Loading />;
  if (auth.data?.onboarding_required) return <Onboarding />;
  if (auth.data?.pin_required && !auth.data.authenticated) return <Login />;
  if (auth.data?.profile?.must_change_pin)
    return <MemberSetupWizard name={auth.data.profile.display_name} />;
  const views = {
    today: <Today />,
    week: <Week />,
    progress: <Progress />,
    plan: <Plan />,
    settings: <Settings />,
  };
  return (
    <div className={`app ${embedded ? "embedded" : ""}`}>
      <aside className="sidebar">
        <div className="brand">
          <span>
            <HeartPulse />
          </span>
          <div>
            <strong>Health OS</strong>
            <small>
              {auth.data?.profile?.display_name || "steady, not strict"}
            </small>
          </div>
        </div>
        <nav>
          {nav.map(([key, label, Icon]) => (
            <button
              key={key}
              className={view === key ? "active" : ""}
              onClick={() => setView(key)}
            >
              <Icon />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <blockquote>“A short walk still counts.”</blockquote>
          <button className="sidebar-lock" onClick={lockDashboard}>
            <LogOut size={18} />
            <span>Lock dashboard</span>
          </button>
        </div>
      </aside>
      <main className="content">{views[view]}</main>
      <nav className="bottom-nav">
        {nav.map(([key, label, Icon]) => (
          <button
            key={key}
            className={view === key ? "active" : ""}
            onClick={() => {
              setView(key);
              scrollTo(0, 0);
            }}
          >
            <Icon />
            <span>{label}</span>
          </button>
        ))}
        <button className="mobile-lock" onClick={lockDashboard}>
          <LogOut />
          <span>Lock</span>
        </button>
      </nav>
    </div>
  );
}
