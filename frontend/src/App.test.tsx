import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, vi, test, expect } from "vitest";
import App from "./App";
const today = {
  date: "2026-07-13",
  display_name: "John",
  greeting: "Good morning",
  mode: { name: "Standard Day", subtitle: "Keep it simple.", flexible: false },
  completion: 0,
  weekly_consistency: 60,
  weight: { current: 99, start: 99, next_milestone: 94 },
  water: {
    current_ml: 750,
    target_ml: 2000,
    progress: 38,
    latest_entry_id: 4,
    latest_amount_ml: 250,
  },
  next_action: {
    title: "Morning water",
    message: "One glass is enough.",
    task_id: null,
  },
  tasks: [],
  callouts: [],
  embedded_default: false,
};
const testTask = {
  id: 1,
  key: "wake",
  name: "Wake in your target window",
  description: "Start without rushing.",
  category: "sleep",
  icon: "sunrise",
  suggested_time: "7:00 AM",
  required: true,
  minimum_label: null,
  state: "available",
  minimum_version: false,
};
const testPlanEntry = {
  id: 1,
  key: "evening-walk",
  name: "Evening walk",
  description: "A relaxed walk after dinner.",
  category: "movement",
  suggested_time: "19:00",
  required: false,
  minimum_label: "Walk for 5 minutes",
  days: [0, 1, 2, 3, 4, 5, 6],
  paused: false,
};
const progress = {
  weight: [
    {
      id: 7,
      date: "2026-07-12",
      weight: 98.2,
      average: 98.2,
      waist_cm: 101,
      notes: "Morning",
    },
  ],
  weight_goal: {
    start: 99,
    current: 98.2,
    goal: 85,
    change: 0.8,
    remaining: 13.2,
    progress: 6,
    last_recorded: "2026-07-12",
    milestones: [94, 90, 85],
  },
  sleep: [],
  exercise: [],
  summary: { exercise_minutes: 0, average_sleep: 0 },
};
let taskState = "available";
let onboardingRequired = false;
let haSetupRequired = false;
beforeEach(() => {
  cleanup();
  taskState = "available";
  onboardingRequired = false;
  haSetupRequired = false;
});
vi.stubGlobal(
  "fetch",
  vi.fn(async (url: string, options?: RequestInit) => {
    if (url.includes("/skip")) taskState = "skipped";
    if (url.includes("/completion") && options?.method === "DELETE")
      taskState = "available";
    return {
      ok: true,
      json: async () =>
        url.includes("auth/status")
          ? {
              onboarding_required: onboardingRequired || haSetupRequired,
              pin_required: false,
              authenticated: !onboardingRequired,
              auth_provider: haSetupRequired ? "home_assistant" : null,
              profile: haSetupRequired
                ? {
                    display_name: "Taylor",
                    setup_required: true,
                  }
                : null,
            }
          : url.includes("/today")
            ? { ...today, tasks: [{ ...testTask, state: taskState }] }
            : url.includes("/progress")
              ? progress
              : url.includes("/plan")
                ? [testPlanEntry]
                : {},
    };
  }),
);
test("renders application navigation", async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>,
  );
  expect((await screen.findAllByText("Today")).length).toBeGreaterThan(0);
});

test("shows first-time setup before the dashboard", async () => {
  onboardingRequired = true;
  render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>,
  );
  expect(
    await screen.findByRole("heading", { name: "Let’s make this yours." }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Your name")).toBeInTheDocument();
  expect(screen.queryByText("Allow Embedding")).not.toBeInTheDocument();
});

test("onboards a Home Assistant user without asking for a PIN", async () => {
  haSetupRequired = true;
  render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>,
  );
  expect(
    await screen.findByRole("heading", { name: "Let’s make this yours." }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Timezone")).toBeInTheDocument();
  expect(screen.getByText(/We detected/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Continue/ }));
  expect(
    screen.getByRole("heading", { name: "Set gentle targets." }),
  ).toBeInTheDocument();
  expect(screen.queryByLabelText("PIN")).not.toBeInTheDocument();
  expect(screen.queryByText("Today’s tasks")).not.toBeInTheDocument();
});
test("adds water from the one-tap dashboard controls", async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>,
  );
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Add 350 milliliters of water",
    }),
  );
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "/api/hydration",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ amount_ml: 350 }),
      }),
    ),
  );
});

test("opens the new plan entry editor", async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>,
  );
  const planButtons = await screen.findAllByRole("button", { name: "Plan" });
  fireEvent.click(planButtons[0]);
  fireEvent.click(await screen.findByRole("button", { name: "Add entry" }));
  expect(
    screen.getByRole("heading", { name: "Add to your plan" }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Name")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Add to plan" }),
  ).toBeInTheDocument();
});

test("opens an existing plan entry editor in the task's list position", async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>,
  );
  const planButtons = await screen.findAllByRole("button", { name: "Plan" });
  fireEvent.click(planButtons[0]);
  fireEvent.click(
    await screen.findByRole("button", { name: "Edit Evening walk" }),
  );

  const heading = screen.getByRole("heading", {
    name: "Update this routine",
  });
  expect(heading.closest(".plan-list")).not.toBeNull();
  expect(screen.getByLabelText("Name")).toHaveValue("Evening walk");
  expect(
    screen.queryByRole("button", { name: "Edit Evening walk" }),
  ).not.toBeInTheDocument();
});

test("offers edit and delete controls for recorded weights", async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>,
  );
  const progressButtons = await screen.findAllByRole("button", {
    name: "Progress",
  });
  fireEvent.click(progressButtons[0]);

  fireEvent.click(
    await screen.findByRole("button", {
      name: "Edit weight from 2026-07-12",
    }),
  );
  expect(
    screen.getByRole("dialog", { name: "Edit weight entry" }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Weight")).toHaveValue(98.2);
  expect(
    screen.getByRole("button", { name: "Save changes" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Delete weight from 2026-07-12" }),
  ).toBeInTheDocument();
});

test("opens the weight check-in from Today", async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Record" }));
  expect(
    screen.getByRole("dialog", { name: "Record your weight" }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Weight")).toHaveValue(99);
  expect(
    screen.getByRole("button", { name: "Save reading" }),
  ).toBeInTheDocument();
});

test("shows a skipped task and allows restoring it", async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "•••" }));
  fireEvent.click(screen.getByRole("button", { name: "Skip intentionally" }));

  const undo = await screen.findByRole("button", { name: "Undo skip" });
  expect(screen.getAllByText("Skipped intentionally").length).toBeGreaterThan(
    0,
  );
  await waitFor(() => expect(undo).toBeEnabled());
  fireEvent.click(undo);
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "/api/tasks/1/completion",
      expect.objectContaining({ method: "DELETE" }),
    ),
  );
});
