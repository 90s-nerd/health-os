export type Task = {
  id: number;
  key: string;
  name: string;
  description: string;
  category: string;
  icon: string;
  suggested_time: string | null;
  required: boolean;
  minimum_label: string | null;
  state: "available" | "upcoming" | "completed" | "skipped";
  minimum_version: boolean;
  notes?: string;
};
export type Today = {
  date: string;
  display_name: string;
  greeting: string;
  mode: { name: string; subtitle: string; flexible: boolean };
  completion: number;
  weekly_consistency: number;
  weight: { current: number; start: number; next_milestone: number };
  water: {
    current_ml: number;
    target_ml: number;
    progress: number;
    latest_entry_id: number | null;
    latest_amount_ml: number | null;
  };
  next_action: { title: string; message: string; task_id: number | null };
  tasks: Task[];
  callouts: Callout[];
  embedded_default: boolean;
};
export type Callout = {
  id: string;
  severity: string;
  priority: number;
  title: string;
  message: string;
  suggested_action?: string;
  reason: string;
  dismissible: boolean;
};
