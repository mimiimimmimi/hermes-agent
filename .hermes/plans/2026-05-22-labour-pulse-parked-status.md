# Pulse Parked Status

Parked: 2026-05-22

Status: Finalised plan parked pending explicit Kanban build approval.

Plan file: `.hermes/plans/2026-05-22-labour-pulse-review-plan.md`

Git status: not applicable — `.hermes/plans` is outside a project git repository in this session; no repo commit/push was performed.

Final decisions:

- Product name is **Pulse**, not Labour Pulse.
- V1 Roll Call exceptions: Sick, Absent, AWOL, Early finish.
- Early finish requires time-left and reason.
- Team leads can record workstation changes; no individual login required for V1.
- V1 Pulse views include Daily Pulse, Season Pulse, and Manager Pulse.
- Comparison target: Manning Pulse vs any available Nova Planning plan vs this FY, with working days per month and rostering drill-down to hours.
- Cost fields are planning/reference only, not live payroll. No formal payroll-style approval gate is required.
- Lu Ee can approve non-critical Pulse blockers.

Repo creation note:

- Repo creation has not yet been approved/completed.
- Recommended default is a dedicated Pulse repo for the visibility layer, separate from Manning Board and Nova Planner.
- Proposed name: `mimiimimmimi/pulse` or `mimiimimmimi/wetfish-pulse`.
- Repo setup should be the first build card after planner approval, before feature coding.

Need Armi / Need Lu Ee blocker handling:

Need Armi input for repo architecture/name disagreement, live/production deployment, gateway/Hermes routing, tunnel/DNS/Cloudflare/auth/security, host shutdown/hardware, payroll-interpretation risk, Excel replacement, Nerve scope expansion, or sensitive data leaving Wetfish control.

Need Lu Ee input for non-critical Pulse workflow, wording, card priority, UAT, and source-mapping choices.

Do not block overnight for visual polish, final threshold tuning, incomplete cost-model detail, scenario naming, or follow-on Area/Scenario Pulse structure if a safe labelled default exists.

Next start point after approval:

1. Create Kanban planner card.
2. Planner converts finalised plan into executable build cards and blocker handling.
3. Repo setup card creates/verifies the approved Pulse repo scaffold and CI.
4. No production/live changes until reviewer/UAT approval.
