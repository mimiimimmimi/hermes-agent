# Pulse Finalised Plan

> **Status:** Finalised and parked pending explicit Kanban build approval.
> **Build gate:** Do not dispatch coder/reviewer/ops build cards until Armi approves the Kanban build. Production/live remains untouched unless separately approved.
> **Overnight rule:** Include Need Armi / Need Lu Ee blocker handling in the first Kanban planner card.

## 1. Purpose

Pulse is the Wetfish labour-performance visibility programme.

It will connect:

- Manning Board / Roll Call actuals
- Nova Planner roster and process-flow forecasts
- FY Plan / Plan Book approved baseline
- planning/reference labour cost assumptions, allowances, productivity, and variance drivers

The goal is to make labour performance clear enough for daily management, season tracking, and future planning — without depending only on manual Excel reconciliation.

Short vision:

> Pulse shows the labour heartbeat. Nerve later becomes the local-first planning brain and watchdog.

## 2. Why we are building it

Current labour planning and performance visibility is spread across multiple tools and files:

- Manning Board shows planned/actual floor placement.
- Team leaders know attendance exceptions and movements.
- Nova Planner will model forecast staffing and roster cost.
- Plan Book / FY Plan holds the approved budget baseline.
- Excel currently carries much of the planning/reconciliation burden.

This creates risk:

- overspend is seen too late;
- hidden costs such as allowance creep are hard to call out early;
- actual labour movement is not always connected back to cost/productivity;
- future FY planning depends too much on manual spreadsheet maintenance;
- managers do not always have one clear view of actual vs forecast vs plan.

Pulse is intended to close that gap.

## 3. Product boundary

Pulse is one master programme, but it must be built in phases. Do not build it as one giant app/card.

System ownership:

- **Manning Board / Roll Call** owns Manning Actual:
  - actual attendance;
  - employee ID;
  - workstation ID;
  - workstation assignment/change events;
  - Roll Call completion and exceptions.

- **Nova Planner** owns Nova Forecast:
  - process-flow staffing;
  - roster model;
  - forecast paid hours;
  - forecast labour spend;
  - scenario versions.

- **FY Plan / Plan Book** owns the approved baseline:
  - approved target hours/spend;
  - approved output assumptions;
  - next-FY or season baseline.

- **Pulse** owns visibility:
  - actual vs forecast vs plan;
  - variance explanation;
  - source freshness;
  - Pulse Cards and manager views.

- **Nerve** is future scope:
  - watchdog;
  - cost-risk early warnings;
  - local-first AI summaries;
  - next-FY planning replacement pathway.

## 4. Naming standard

Use Pulse naming consistently.

Approved naming:

- Pulse Programme
- Pulse
- Pulse Board
- Pulse Cards
- Daily Pulse
- Season Pulse
- Manager Pulse
- Area Pulse
- Scenario Pulse
- Pulse Drivers
- Nerve

Avoid:

- Labour Pulse
- Scoreboard
- Race

## 5. Finalised V1 decisions

- V1 Roll Call exceptions are confirmed:
  - Sick
  - Absent
  - AWOL
  - Early finish
- Early finish must require **time left** and **reason**.
- Team leads can record workstation changes, but **no individual login is required** for V1.
- V1 Pulse views include all three:
  - Daily Pulse
  - Season Pulse
  - Manager Pulse
- Comparison target: **Manning Pulse vs any available plan in Nova Planning vs this FY**, with working days per month and rostering drill-down to hours.
- Cost fields are planning/reference only, not live payroll. No formal payroll-style approval gate is required.
- Lu Ee can approve non-critical Pulse blockers.

## 6. View wording

- **Daily Pulse:** today/shift view — what happened today, exceptions, labour hours/spend, source freshness.
- **Season Pulse:** month/season projection — whether we are tracking to save or overspend vs this FY.
- **Manager Pulse:** simplified manager/SET summary — key cards only, less operational detail.

The planner card may sequence delivery internally, but the approved V1 scope includes all three.

## 7. Cost-field wording

Cost fields are planning/reference components, not live payroll.

Planner should propose a practical V1 set such as:

- paid hours;
- rostered hours;
- variance hours;
- base labour cost estimate;
- allowance estimate / allowance creep flag;
- overtime or penalty estimate if available;
- cost per kg / KGPMH where source data is available.

## 8. Phase roadmap

### Phase 1 — Manning Actual / Roll Call foundation

Goal: capture reliable daily actual labour data without slowing team leads down.

Scope:

- Build Roll Call inside Manning Board Manager.
- Team leads mark exceptions only after factory start.
- Assigned staff not marked as exceptions default to **at work**.
- Annual leave is handled pre-shift in Manning Board setup.
- Capture confirmed V1 exception types.
- Early finish captures time-left and reason.
- Store employee ID and workstation ID.
- Team leads can record workstation changes without individual login.
- Store workstation movement/change history as event rows.

Important data model rule:

Do **not** create columns like `change_1`, `change_2`, `change_3`.

Use event rows instead:

```text
workstation_change_id
employee_id
date
time
workstation_pre_change
workstation_post_change
recorded_by
recorded_at
source
```

Acceptance criteria:

- Roll Call can be completed quickly by workstation/area.
- Unmarked assigned staff are treated as present.
- Early finish records time-left and reason.
- Exception records are auditable.
- Workstation changes create event rows.
- Data can later feed Pulse and Nerve.

### Phase 2 — Nova Forecast / roster-costing foundation

Goal: turn planned process staffing into forecast labour hours and spend.

Scope:

- Nova Planner models process-flow staffing.
- Add/confirm roster costing assumptions as planning/reference settings.
- Calculate forecast paid hours.
- Calculate forecast labour spend.
- Support named scenario versions.
- Keep Nova Forecast separate from actual Roll Call records.
- Support drill-down from monthly working days and rostering into hours.

Acceptance criteria:

- Nova can produce forecast hours/spend by scenario.
- Forecast can be compared against this FY and Manning Actual / Manning Pulse.
- Monthly working days and roster assumptions can drill down into hours.
- Scenarios are versioned and not overwritten silently.

### Phase 3 — FY Plan / Plan Book baseline link

Goal: define the approved target baseline that Pulse compares against.

Scope:

- Identify the baseline fields needed from FY Plan / Plan Book.
- Map output, labour, cost, working days/month, rostering, and productivity assumptions.
- Preserve the current Excel file as source/reference during V1.
- Do not replace Excel until Pulse/Nerve is proven and separately approved.

Acceptance criteria:

- Pulse can compare against an approved baseline.
- Baseline source and date are visible.
- Import/entry is auditable.
- Excel remains the fallback until replacement criteria are approved.

### Phase 4 — Pulse visibility layer

Goal: give managers one clear view of actual vs forecast vs plan.

Scope:

- Build Pulse Board as an interactive grid/canvas.
- Build draggable Pulse Cards.
- Show Daily Pulse, Season Pulse, and Manager Pulse in V1.
- Show Pulse Drivers explaining variances.
- Include source health/freshness indicators.

Initial Pulse Cards:

- Labour Hours
- Labour Spend
- Roll Call Completion
- Roll Call Exceptions
- Workstation/Area Variance
- KGPMH/Productivity
- Source Health/Freshness
- Season Pulse Projection
- Scenario Pulse Comparison
- Allowance / Hidden Cost Watch

Acceptance criteria:

- Manager can see actual vs forecast vs plan.
- Every major variance has a Pulse Driver.
- Source freshness is visible.
- Hidden cost drift is surfaced, not buried.
- Cards are clear enough for daily use.

### Phase 5 — Nerve-ready foundation

Goal: ensure Pulse data can later support Nerve without rebuilding the foundation.

Scope:

- Store clean events.
- Keep audit trails.
- Track source freshness.
- Preserve semantic IDs for employees, workstations, shifts, scenarios, and cost assumptions.
- Keep sensitive data local-first.
- Use deterministic rules first; AI summaries later.

Nerve watchdog future role:

- call out app/system/source-health risks;
- call out early signs of labour overspend;
- detect hidden cost drift such as allowance creep;
- monitor overtime/penalty drift;
- compare rostered hours vs paid hours;
- detect repeated exceptions;
- flag workstation changes that create paid-hour waste;
- explain unexplained variance between Manning Actual, Nova Forecast, and FY Plan.

Long-term Nerve planning vision:

- become the accurate, close-to-realistic next-FY planning tool;
- eventually replace the current Excel-based FY planning file;
- combine real Manning Actual history, Nova Forecast models, FY Plan baselines, cost assumptions, allowances, productivity, and scenario logic;
- replace Excel only when the tool is trusted, auditable, maintainable, and accurate enough for FY planning conversations.

Acceptance criteria:

- Pulse stores data in a way Nerve can monitor later.
- Sensitive employee/cost data remains local-first by default.
- Nerve vision is documented but not confused with V1 Pulse build scope.

## 9. Repository / project setup decision

Repo creation has not yet been approved or completed. Add this as an explicit pre-build gate before any coding work.

Recommended default: create a dedicated GitHub repository for the Pulse visibility layer, because Pulse is a separate product boundary from Manning Board and Nova Planner even though it consumes their data.

Proposed repo:

```text
mimiimimmimi/pulse
```

Alternative names if Armi prefers Wetfish prefixing:

```text
mimiimimmimi/wetfish-pulse
mimiimimmimi/Wetfish-Pulse
```

Repo ownership boundaries:

- **Manning Board repo:** Roll Call actual attendance and workstation event capture.
- **Nova Planner repo:** process-flow forecast, roster costing, scenario plan outputs.
- **Pulse repo:** Pulse Board, Daily Pulse, Season Pulse, Manager Pulse, comparison layer, source-health display, and Pulse Drivers.
- **Future Nerve repo/app:** only when Nerve becomes its own product; do not create it during Pulse V1 unless separately approved.

Initial Pulse repo scaffold should include:

- `README.md` explaining purpose, boundaries, and data sources.
- `CLAUDE.md` with Wetfish role boundaries and startup context.
- `docs/PARKED_STATUS.md` or `docs/plans/` containing this finalised plan and next start point.
- backend skeleton for comparison/data-contract APIs.
- frontend skeleton for Daily Pulse, Season Pulse, and Manager Pulse.
- tests for data-contract parsing and comparison calculations.
- CI workflow for backend tests and frontend build.
- `.gitignore` protecting local data, secrets, exports, and generated files.
- deployment notes for staging only.

Repo creation gate:

1. Armi approves repo name.
2. Create GitHub repo and local clone on the Hermes Mac/project workspace.
3. Add initial scaffold and plan docs.
4. Push first commit and verify CI.
5. Only then dispatch coding cards against the repo.

Do not bury Pulse inside Manning Board by default. Roll Call changes belong in Manning Board, but the Pulse visibility layer should have its own repo unless Armi explicitly chooses a different architecture.

## 10. Potential blockers and escalation rules

This section must be copied into the first Kanban planner card and used during any overnight build. The goal is to keep work moving without repeatedly asking Armi unless a real approval/input gate is hit.

### Needs Armi input

Only escalate to Armi for blockers that materially change risk, scope, live systems, security, or the business direction.

1. **Repo name / architecture approval** — if the team cannot proceed with the default `mimiimimmimi/pulse` repo or there is disagreement about a separate Pulse repo vs embedding Pulse inside Manning/Nova.
2. **Live or production deployment** — any move from staging/test to live, any production data write path, or any visible change to a live Wetfish Portal card.
3. **Gateway restart / Hermes routing** — any Hermes gateway restart, tool routing change, model/provider change, or anything affecting Hermes operation.
4. **Tunnel, DNS, Cloudflare, auth, or security changes** — new public hostname, Cloudflare route, Access policy, credential, auth model, or security-sensitive config.
5. **Host shutdown / hardware / network actions** — any shutdown, reboot, power-cycle, host migration, or risky runtime service action.
6. **Payroll-like interpretation risk** — if a cost calculation could be mistaken for live payroll, wage advice, or official payroll approval rather than planning/reference only.
7. **Excel replacement decision** — any attempt to retire, supersede, or replace the current FY Excel file. Pulse/Nerve replacement is future vision only until separately approved.
8. **Scope expansion into Nerve** — if builders start implementing Nerve AI/watchdog features instead of keeping Nerve as future-ready design.
9. **Sensitive data leaves Wetfish control** — any proposal to send employee-linked records, payroll/cost assumptions, raw logs, screenshots, or audit trails to external/cloud AI or third-party services.

### Needs Lu Ee input

Lu Ee can approve non-critical Pulse blockers and user/workflow details. Escalate these to Lu Ee first unless they also hit an Armi-only gate above.

1. **Roll Call workflow details** — screen wording, team-lead flow, phone/QR shortcut vs Manager view, and whether the flow is fast enough.
2. **Exception wording and options** — display wording for Sick, Absent, AWOL, Early finish, time-left, and reason fields.
3. **Manager Pulse wording** — whether variance wording is clear, fair, and suitable for manager/SET review.
4. **Pulse Card priority** — which cards are must-have for first staging if time is limited.
5. **UAT feedback** — usability, layout, labels, and whether staging is understandable enough for Armi review.
6. **Non-critical source mapping choices** — display names, grouping, and drill-down labels where the business meaning is clear and no live/security gate is involved.

### Do not block overnight for these if a safe default exists

- Exact visual polish of cards, provided the data and wording are not misleading.
- Final threshold tuning for amber/red warnings; use conservative placeholders and mark as configurable.
- Perfect cost model completeness; start with planning/reference fields and show source/assumption labels.
- Scenario naming conventions; planner can propose clear names and reviewer can refine.
- Area Pulse or Scenario Pulse implementation; these are follow-on structures unless explicitly pulled into V1.

### Technical blockers to record clearly

If any of these occur, record evidence in the Kanban card and continue with the next safe task if possible:

- Manning Board actuals do not yet expose required fields.
- Nova Planning does not yet expose a usable plan/scenario output.
- FY baseline requires manual mapping from Excel/Plan Book before comparison.
- Working-days-per-month or rostering assumptions are missing.
- Cross-app API/data contracts are not ready.
- Staging cannot be exposed without tunnel/DNS/auth changes.
- Public staging health is green but browser/data smoke fails.

### Overnight reporting rule

For overnight work, report only:

- ready staging links;
- real blockers needing Armi/Lu Ee input;
- completed build/review milestones;
- final parked summary.

Do not send repeated technical noise or multiple duplicate blocker alerts.

## 11. Suggested Kanban build sequence after approval

Only create Kanban build cards after Armi approves this finalised parked plan.

Recommended card order:

1. **Planner card:** confirm repo architecture, final Pulse V1 build scope, data contracts, blocker list, and acceptance criteria for Daily Pulse, Season Pulse, and Manager Pulse.
2. **Repo setup card:** create/verify the approved Pulse repo scaffold, push first commit, and verify CI before feature coding.
3. **Manning/Roll Call coder card:** implement Roll Call actuals and workstation event history in the Manning Board repo.
4. **Reviewer card:** verify Roll Call data model, UX speed, audit, and source safety.
5. **Nova planner/costing card:** define roster-costing assumptions and scenario output contract in/for Nova Planner.
6. **FY Plan baseline card:** map first baseline import/entry path.
7. **Pulse Board prototype card:** build Daily Pulse, Season Pulse, Manager Pulse, Pulse Cards, and source freshness display.
8. **Reviewer card:** check calculations, naming, wording, source boundaries, and non-payroll wording.
9. **Ops/staging card:** stage only after reviewer approval.
10. **Senior tester/UAT card:** Lu Ee/Armi review usability before live.

## 12. Build gates

Do not start coding until these are answered or explicitly deferred:

1. Repo name/architecture is approved and the initial Pulse repo is created/scaffolded.
2. Need Armi / Need Lu Ee blocker rules are copied into the Kanban planner card and accepted as the overnight escalation rule.
3. V1 Roll Call exception list is confirmed: Sick, Absent, AWOL, Early finish.
4. Early finish must capture time-left and reason.
5. Team leads can record workstation changes; no individual login required for V1.
6. V1 Pulse view scope is confirmed: include Daily Pulse, Season Pulse, and Manager Pulse.
7. First comparison target is confirmed: Manning Pulse vs available Nova Planning plan vs this FY, with working days per month and rostering drill-down to hours.
8. Planner should propose V1 cost fields; no approval gate is required because this is not a live payroll system.
9. Lu Ee can approve non-critical blockers for this project.

## 13. Parked status

Parked on 2026-05-22 after Armi finalised the review answers and requested blocker handling.

Next start point after approval: create the Kanban planner card first. The planner must convert this plan into executable build cards, copy in the Need Armi / Need Lu Ee blocker rules, confirm blocker handling, and keep production/live untouched until reviewer/UAT approval.

## 14. Approval wording

If approved to start Kanban build, Armi can reply:

```text
Approved: start Pulse Kanban build from the finalised parked plan. Start with planner card and keep production untouched until review/UAT approval.
```

If changes are needed, reply with:

```text
Change Pulse plan: [write changes here]
```
