export const referenceViews = [
  { id: "S00-startup", path: "/startup", reference: "S00-startup" },
  { id: "S01-projects", path: "/projects", reference: "S01-projects" },
  { id: "S02-preflight", path: "/projects/project_demo/preflight", reference: "S02-preflight" },
  { id: "S03-project-overview", path: "/projects/project_demo", reference: "S03-project-overview" },
  { id: "S04-planner", path: "/projects/project_demo/stages/planner", reference: "S04-planner" },
  { id: "S04-designer", path: "/projects/project_demo/stages/designer", reference: "S04-designer" },
  { id: "S04-builder", path: "/projects/project_demo/stages/builder", reference: "S04-builder" },
  { id: "S04-reviewer", path: "/projects/project_demo/stages/reviewer", reference: "S04-reviewer" },
  { id: "S04-deployer", path: "/projects/project_demo/stages/deployer", reference: "S04-deployer" },
  { id: "S05-artifacts-gate-handoff", path: "/projects/project_demo/artifacts", reference: "S05-artifacts-gate-handoff" },
  { id: "S06-approvals-capabilities-risk", path: "/projects/project_demo/approvals", reference: "S06-approvals-capabilities-risk" },
  { id: "S07-conflicts-checkpoints-recovery", path: "/projects/project_demo/recovery", reference: "S07-conflicts-checkpoints-recovery" },
  { id: "S08-settings", path: "/settings", reference: "S08-settings" },
  { id: "S09-events-audit-diagnostics", path: "/diagnostics", reference: "S09-events-audit-diagnostics", prepare: "audit" },
] as const;

export const referenceThemes = ["light", "dark"] as const;
