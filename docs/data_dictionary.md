# Data Dictionary

This document defines the first schema draft for the synthetic A/B-testing platform. It is the contract for generation, validation, and exports. All timestamps are UTC ISO-8601 values. Effective intervals use `[effective_from, effective_to)`: the start is included and the end is excluded; a blank end means "still effective." Boolean values are true/false. Database primary and foreign keys must be preserved in every export.

## Global rules

- Generate 50,000 distinct eligible synthetic users across 10 experiments: 5,000 disjoint users per experiment in the baseline. `ExperimentAudience` remains a many-to-many bridge so the schema can support overlapping audiences later.
- Use seed `20261022` by default. Starter/full scale changes the number of generated rows, not the generation rules.
- IDs are strings, immutable, deterministic, and zero-padded where a counter is used. Experiment IDs use `EXP-2026-000001`; variants use `VAR-<experiment-id>-A` and `VAR-<experiment-id>-B`; normal assignments use `ASG-<experiment-id>-<user-id>`; exposure IDs use `EXPOS-2026-000001`; conversion IDs use `CONV-2026-000001`.
- Synthetic user identifiers use `USR-000001` and contain no real personal information. Timestamps are UTC. Rates and probabilities are fractions from 0 to 1, not percentages.
- A valid baseline has one assignment per eligible experiment-user pair. To represent the deliberate multi-variant-assignment anomaly without duplicate primary keys, the additional assignment uses a deterministic `-DUP01` suffix; this exception is labeled in the separate ground-truth file.
- The final experiment deliberately has a sample-ratio mismatch. Validation reports `assignment_valid=false`; results are still calculated for diagnosis because the underlying links remain intact, but each result is marked `result_valid=false` and `decision=invalid`. Ground truth expects the analysis to be blocked for decision-making and investigated.
- `ground_truth` is evaluation metadata, not an input feature. Never join it into the tables used to calculate experiment results.

## Core entities

### Experiment

One planned or running A/B test. It owns variants, eligibility links, assignments, and results.

| Field | Type | Req. | Allowed values / units | Unique / key | Validation |
|---|---|---:|---|---|---|
| `experiment_id` | string | Yes | `EXP-2026-` plus six digits | PK | Immutable; unique; valid format. |
| `name` | string | Yes | Human-readable synthetic name | No | Non-empty. |
| `hypothesis` | string | Yes | Falsifiable statement | No | Non-empty; states the expected direction and population. |
| `primary_metric_definition_id` | string | Yes | Existing metric definition ID | FK to `MetricDefinition` | Definition must be effective during the experiment. |
| `analysis_plan` | enum | Yes | `ITT` | No | Only predeclared analysis plan for this challenge; results must follow it. |
| `outcome_window_days` | integer | Yes | Positive days | No | Greater than zero; used to derive each assignment's outcome window. |
| `random_seed` | integer | Yes | Default `20261022` | No | Recorded for traceability; generation uses a deterministic seeded generator. |
| `planned_start_at` | timestamp | Yes | UTC | No | Earlier than `planned_end_at`. |
| `planned_end_at` | timestamp | Yes | UTC | No | Later than `planned_start_at`. |
| `status` | enum | Yes | `draft`, `designed`, `running`, `completed`, `analyzed`, `archived` | No | Only documented forward lifecycle transitions are accepted. |
| `created_at` | timestamp | Yes | UTC | No | No later than any status event. |

### Variant

A treatment option within one experiment. The experiment has one control and one treatment variant in this challenge.

| Field | Type | Req. | Allowed values / units | Unique / key | Validation |
|---|---|---:|---|---|---|
| `variant_id` | string | Yes | `VAR-<experiment-id>-A/B` | PK | Immutable; unique; embedded experiment ID must match `experiment_id`. |
| `experiment_id` | string | Yes | Existing experiment ID | FK to `Experiment` | Parent must exist. |
| `variant_key` | string | Yes | `A`, `B` | Unique with experiment | `A` is control; `B` is treatment; one of each per experiment. |
| `name` | string | Yes | `control`, `treatment` | No | Must agree with `variant_key`. |
| `allocation_probability` | number | Yes | Fraction `(0, 1)` | No | Per-experiment variant probabilities sum to 1 within tolerance. |
| `treatment_parameters_json` | JSON text | Yes | `{}` for control; documented synthetic changes for treatment | No | Parses as JSON; control has no treatment change. |
| `effective_from` | timestamp | Yes | UTC | No | Before effective end, if any. |
| `effective_to` | timestamp | No | UTC or blank | No | Later than effective start. |
| `status` | enum | Yes | `planned`, `active`, `paused`, `retired` | No | State changes are appended to variant lifecycle history. |

### AudienceMember

A synthetic person record. This table is deliberately separate from experiment eligibility.

| Field | Type | Req. | Allowed values / units | Unique / key | Validation |
|---|---|---:|---|---|---|
| `user_id` | string | Yes | `USR-` plus six digits | PK | Immutable; unique; valid format. |
| `region` | enum | Yes | `north`, `south`, `east`, `west` | No | Must be an allowed synthetic category. |
| `device_type` | enum | Yes | `web`, `ios`, `android` | No | Must be an allowed synthetic category. |
| `tenure_days` | integer | Yes | Days, zero or greater | No | Non-negative. |
| `created_at` | timestamp | Yes | UTC | No | Must be no later than experiment assignment. |

### ExperimentAudience (eligibility bridge)

Resolves the many-to-many relationship between experiments and people and records eligibility at experiment scope. The 50,000 baseline volume counts these eligible pairs.

| Field | Type | Req. | Allowed values / units | Unique / key | Validation |
|---|---|---:|---|---|---|
| `experiment_id` | string | Yes | Existing experiment ID | Composite PK; FK to `Experiment` | Parent must exist. |
| `user_id` | string | Yes | Existing user ID | Composite PK; FK to `AudienceMember` | Parent must exist; one eligibility row per experiment-user pair. |
| `eligible` | boolean | Yes | `true` for generated eligible baseline pairs | No | Only eligible pairs receive assignments. |
| `eligibility_reason` | string | Yes | Documented synthetic rule | No | Non-empty and consistent with eligibility. |
| `evaluated_at` | timestamp | Yes | UTC | No | Within the experiment's planned period. |

### Assignment

The immutable randomized allocation of one eligible experiment-user pair to a variant. This is the unit of intent-to-treat (ITT) analysis.

| Field | Type | Req. | Allowed values / units | Unique / key | Validation |
|---|---|---:|---|---|---|
| `assignment_id` | string | Yes | Normal: `ASG-<experiment-id>-<user-id>`; labeled duplicate adds `-DUP01` | PK | Unique and deterministic; duplicate suffix only for the ground-truth anomaly. |
| `experiment_id` | string | Yes | Existing experiment ID | FK to `ExperimentAudience`; part of composite FK to `Variant` | Must match eligibility and variant parent. |
| `user_id` | string | Yes | Existing user ID | FK to `ExperimentAudience`; composite eligibility FK | Must be eligible in this experiment. |
| `variant_id` | string | Yes | Existing variant ID | Composite FK (`experiment_id`, `variant_id`) to `Variant` | Variant must belong to this experiment. |
| `assigned_at` | timestamp | Yes | UTC | No | In planned experiment window and after eligibility evaluation. |
| `allocation_probability` | number | Yes | Fraction `(0, 1)` | No | Must equal the assigned variant's declared allocation probability. |
| `assignment_method` | enum | Yes | `seeded_random` | No | Generator uses the shared seeded random-number generator. |

Baseline uniqueness of `(experiment_id, user_id)` is validated in code rather than enforced as a database unique constraint, so the deliberate duplicate-assignment anomaly can be represented and reported instead of being silently dropped.

### ExposureEvent

An immutable telemetry record associated with an assignment. A row with `telemetry_status=missing` explicitly represents missing telemetry; its observed exposure time is blank.

| Field | Type | Req. | Allowed values / units | Unique / key | Validation |
|---|---|---:|---|---|---|
| `exposure_id` | string | Yes | `EXPOS-2026-` plus six digits | PK | Immutable; unique; valid format. |
| `assignment_id` | string | Yes | Existing assignment ID | FK to `Assignment` | Parent must exist. |
| `received_variant_id` | string | No | Existing variant ID or blank if telemetry is missing | FK to `Variant` | When present, variant must belong to the assignment's experiment; difference from assignment variant measures noncompliance. |
| `telemetry_status` | enum | Yes | `observed`, `missing` | No | Missing telemetry is retained, not converted into an observed exposure. |
| `exposed_at` | timestamp | Conditional | UTC when observed; blank when missing | No | Observed time normally follows assignment; an intentional earlier-time anomaly is labeled in ground truth. |
| `surface` | enum | Yes | `web`, `ios`, `android` | No | Allowed synthetic exposure surface. |
| `created_at` | timestamp | Yes | UTC | No | Records when the telemetry row was ingested, including missing-telemetry records. |

### ConversionEvent

An immutable conversion outcome linked to the assignment that received the allocation. A conversion can be delayed; whether it falls inside the outcome window is derived from assignment time and experiment settings, not independently generated.

| Field | Type | Req. | Allowed values / units | Unique / key | Validation |
|---|---|---:|---|---|---|
| `conversion_id` | string | Yes | `CONV-2026-` plus six digits | PK | Immutable; unique; valid format. |
| `assignment_id` | string | Yes | Existing assignment ID | FK to `Assignment` | Parent must exist. |
| `converted_at` | timestamp | Yes | UTC | No | Compared with `[assigned_at, assigned_at + outcome_window_days)`; an intentional inconsistent-window anomaly is labeled. |
| `outcome_window_days` | integer | Yes | Positive days | No | Normally copied from the experiment; mismatch is an explicit labeled anomaly. Analysis always uses the experiment's predeclared window. |
| `conversion_value` | number | Yes | Synthetic currency units, zero or greater | No | Finite and non-negative. |
| `currency` | enum | Yes | `USD` | No | All generated values use the same currency. |
| `source` | enum | Yes | `web`, `ios`, `android` | No | Allowed synthetic conversion source. |
| `is_refunded` | boolean | Yes | `true`, `false` | No | Used by the refund guardrail; generated from the documented synthetic rule. |

### MetricDefinition

A versioned catalog definition for a primary or guardrail metric. Definitions are append-only: a changed definition gets a new ID/version and effective dates; prior results keep their original definition.

The generated conversion-rate definitions intentionally differ: V001 counts any user with an in-window conversion, including refunded conversions; V002 counts only users with at least one non-refunded in-window conversion. The V002 change event occurs after the V001 experiment results, so those results continue to reference V001.

| Field | Type | Req. | Allowed values / units | Unique / key | Validation |
|---|---|---:|---|---|---|
| `metric_definition_id` | string | Yes | Deterministic `MET-<metric-slug>-V<version>` | PK | Immutable; unique. |
| `metric_name` | string | Yes | Stable snake_case name | Unique with version | Non-empty. |
| `version` | integer | Yes | Positive integer | Unique with metric name | Increments when definition changes. |
| `description` | string | Yes | Human-readable definition | No | States what is measured. |
| `numerator` | string | Yes | Source fields and calculation | No | Formula can be evaluated from exported source records. |
| `denominator` | string | No | Source fields and calculation | No | Required for rate metrics; denominator cannot be zero for a defined rate. The refund-rate denominator is assigned users. |
| `unit` | enum | Yes | `count`, `fraction`, `USD`, `days` | No | Result value uses this unit. |
| `analysis_unit` | enum | Yes | `assigned_user` | No | Primary and guardrail analyses use assignment-level ITT. |
| `effective_from` | timestamp | Yes | UTC | No | Definition is effective for results that reference it. |
| `effective_to` | timestamp | No | UTC or blank | No | Later than effective start; versions for the same metric must not overlap. |

### MetricDefinitionChangeEvent

An append-only audit event for a metric-definition change. This challenge scenario records a change to `conversion_rate` after results have already been analyzed using V001.

| Field | Type | Req. | Allowed values / units | Unique / key | Validation |
|---|---|---:|---|---|---|
| `metric_definition_change_event_id` | string | Yes | Deterministic event ID | PK | Unique and immutable. |
| `old_metric_definition_id` | string | Yes | Existing metric definition ID | FK to `MetricDefinition` | Must identify the prior version. |
| `new_metric_definition_id` | string | Yes | Existing metric definition ID | FK to `MetricDefinition` | Must be the next version of the same metric. |
| `changed_at` | timestamp | Yes | UTC | No | Must match the prior definition's `effective_to` and new definition's `effective_from`, and follow results using the prior definition. |
| `reason` | string | Yes | Human-readable explanation | No | Non-empty; describes the formula change. |

### GuardrailMetric

A bridge/configuration row linking an experiment to a guardrail metric and its predeclared failure threshold. It makes the experiment-to-metric relationship many-to-many and auditable.

| Field | Type | Req. | Allowed values / units | Unique / key | Validation |
|---|---|---:|---|---|---|
| `experiment_id` | string | Yes | Existing experiment ID | Composite PK; FK to `Experiment` | Parent must exist. |
| `metric_definition_id` | string | Yes | Existing metric definition ID | Composite PK; FK to `MetricDefinition` | Must not be the experiment's primary metric. |
| `comparison` | enum | Yes | `max_increase`, `max_decrease`, `min_value`, `max_value` | No | Defines direction of failure; `max_decrease` compares treatment minus control with the negative threshold. |
| `threshold` | number | Yes | Same unit as metric | No | Finite; applied exactly as predeclared. |
| `alpha` | number | Yes | Fraction `(0, 1)` | No | Predeclared significance level used for uncertainty/failure decisions. |
| `effective_from` | timestamp | Yes | UTC | No | Must precede analysis. |
| `effective_to` | timestamp | No | UTC or blank | No | Later than effective start. |

### ExperimentResult

A derived, versioned analysis result. It references the metric definition used so a later metric change cannot rewrite the meaning of an earlier result.

| Field | Type | Req. | Allowed values / units | Unique / key | Validation |
|---|---|---:|---|---|---|
| `result_id` | string | Yes | Deterministic result ID including experiment, metric, and run counter | PK | Immutable; unique. |
| `experiment_id` | string | Yes | Existing experiment ID | FK to `Experiment` | Parent must exist. |
| `metric_definition_id` | string | Yes | Existing metric definition ID | FK to `MetricDefinition` | Definition must be effective at analysis time. |
| `analysis_run` | integer | Yes | One or greater | Unique with experiment and metric | Incremented for reruns; earlier results are retained. |
| `analysis_plan` | enum | Yes | `ITT` | No | Must match the experiment's predeclared plan. |
| `control_n` | integer | Yes | Assigned-user count | No | Reconciles to assignments in control, not only exposed users. |
| `treatment_n` | integer | Yes | Assigned-user count | No | Reconciles to assignments in treatment. |
| `estimate` | number | Yes | Metric unit; treatment minus control | No | Recomputed from source events and metric definition. |
| `standard_error` | number | Yes | Metric unit | No | Finite and non-negative. |
| `confidence_level` | number | Yes | Fraction `(0, 1)` | No | Predeclared, for example 0.95. |
| `ci_lower` | number | Yes | Metric unit | No | Less than or equal to `ci_upper`; calculated from estimate and uncertainty. |
| `ci_upper` | number | Yes | Metric unit | No | Greater than or equal to `ci_lower`; calculated from estimate and uncertainty. |
| `p_value` | number | No | Fraction `[0, 1]` | No | Blank only when the metric/test does not define one. |
| `result_valid` | boolean | Yes | `true`, `false` | No | False when assignment integrity or the sample-ratio check fails, or when either analysis arm has no assignments. Estimates remain available for diagnosis. |
| `decision` | enum | Yes | `positive`, `negative`, `inconclusive`, `guardrail_failed`, `invalid` | No | Derived from estimate, uncertainty, predeclared thresholds, and validation status. |
| `analyzed_at` | timestamp | Yes | UTC | No | After the experiment's analysis window closes. |

## Supporting history and evaluation records

These supporting records supplement the nine requested core entities so lifecycle changes and deliberate anomalies remain auditable.

### Validation summary output

The per-experiment validation summary is an exported analysis artifact, not a source entity. It contains `experiment_id` (FK to `Experiment`), `eligible_n`, `assigned_n`, `control_n`, `treatment_n`, `sample_ratio_p_value` (unit interval), `duplicate_assignment_count`, `assignment_integrity_valid` (boolean for core assignment links), `assignment_valid` (boolean including the SRM check), and `outcome_window_days`. The separate check table records each check name, pass/fail boolean, and rows checked. An SRM-only case can therefore be distinguished from duplicate or broken-parent assignment failures.

### ExperimentStateEvent

| Field | Type | Req. | Allowed values / units | Unique / key | Validation |
|---|---|---:|---|---|---|
| `state_event_id` | string | Yes | Deterministic event ID | PK | Unique; immutable. |
| `experiment_id` | string | Yes | Existing experiment ID | FK to `Experiment` | Parent must exist. |
| `from_status` | enum | No | Same experiment lifecycle states; blank for initial state | No | Must equal prior event's `to_status`. |
| `to_status` | enum | Yes | `draft`, `designed`, `running`, `completed`, `analyzed`, `archived` | No | Must be an allowed forward transition. |
| `changed_at` | timestamp | Yes | UTC | No | Later than the previous state event. |
| `reason` | string | Yes | Short explanation | No | Non-empty. |

### VariantStateEvent

| Field | Type | Req. | Allowed values / units | Unique / key | Validation |
|---|---|---:|---|---|---|
| `state_event_id` | string | Yes | Deterministic event ID | PK | Unique; immutable. |
| `variant_id` | string | Yes | Existing variant ID | FK to `Variant` | Parent must exist. |
| `from_status` | enum | No | Same variant lifecycle states; blank for initial state | No | Must equal prior event's `to_status`. |
| `to_status` | enum | Yes | `planned`, `active`, `paused`, `retired` | No | Must be an allowed forward transition. |
| `changed_at` | timestamp | Yes | UTC | No | Later than the previous state event. |
| `reason` | string | Yes | Short explanation | No | Non-empty. |

### Separate `ground_truth.csv` / `ground_truth.json`

Ground truth is maintained outside the analysis input tables. Each row has a deterministic `ground_truth_id` (PK), `issue_type` (enum), `entity_type`, `entity_id`, `expected_label`, `expected_decision`, optional `metric_name` and `metric_definition_id`, optional numeric `expected_control`, `expected_treatment`, and `expected_effect`, and a short `reason`. Metric-change rows additionally carry `related_event_id`, `old_metric_definition_id`, `new_metric_definition_id`, `event_timestamp`, and `event_reason`, and expect prior results to retain their original definition reference. Numeric expectations are population means derived from the same declared lift, assignment compliance/crossover, conversion, refund, and revenue rules; result records use the metric version effective at their analysis time. Allowed issue types cover the required negative scenarios, `guardrail_regression`, `metric_definition_changed_after_result`, and `expected_metric_effect`. Expected labels/decisions are derived from the documented rules and calculated outcomes. Ground truth may reference affected source IDs but is never used as an analysis input.

## Relationships and cardinality

| Relationship | Cardinality | Foreign-key rule |
|---|---|---|
| Experiment to Variant | 1:N | Every variant references one experiment; each experiment has exactly variants A and B in the baseline. |
| Experiment to AudienceMember | N:M | Resolved by `ExperimentAudience`; eligibility is unique per experiment-user pair. |
| ExperimentAudience to Assignment | 1:0..1 in baseline | Assignment references an eligible pair; a labeled anomaly can have more than one assignment for the pair. |
| Experiment to Assignment | 1:N | Assignment also references its experiment's variant. |
| Variant to Assignment | 1:N | Assignment variant must belong to the same experiment. |
| Assignment to ExposureEvent | 1:0..N | Exposure/telemetry records reference an assignment; missing telemetry is explicit. |
| Assignment to ConversionEvent | 1:0..N | Conversion events reference an assignment; conversions need not occur. |
| Experiment to primary MetricDefinition | N:1 | The primary metric definition must exist and be effective for the experiment. |
| Experiment to MetricDefinition guardrails | N:M | Resolved by `GuardrailMetric`, with thresholds and alpha on the bridge row. |
| Experiment to ExperimentResult | 1:N | Each result references one experiment and one versioned metric definition. |
| Experiment to ExperimentStateEvent | 1:N | State changes are appended, not overwritten. |
| Variant to VariantStateEvent | 1:N | Variant state changes are appended, not overwritten. |

## Lifecycle and derived-value rules

- Experiment transitions are `draft -> designed -> running -> completed -> analyzed -> archived`; the generated baseline records `draft -> designed -> running -> completed -> analyzed`, and transition history is append-only. A failed validation is recorded as a result/decision and does not erase source records.
- Variant transitions are `planned -> active -> paused -> active -> retired`; the generated baseline records `planned -> active -> retired`, and a retired variant cannot receive new assignments.
- Assignments are immutable. Reassignment or duplicate assignment is represented by another row and must be flagged; it is never implemented by changing the original variant.
- Exposure events must normally follow assignment. Conversion-window membership is derived from assignment time plus `outcome_window_days`. Delayed conversions remain in the source events and are included only when within the predeclared window.
- Counts, conversion rates, sample-ratio checks, effects, confidence intervals, p-values, guardrail outcomes, and result decisions are calculated from source records and metric definitions. They are never independently randomized.
- The designated SRM-only negative case intentionally calculates a result despite `assignment_valid=false` so its metrics remain inspectable. The result is explicitly marked invalid, and the anomaly, dashboard warning, and ground truth flag that it must not guide a decision.
- Metric changes create a new `MetricDefinition` version with new effective dates. Existing results keep their original metric ID; a ground-truth case labels a definition whose effective date changes after a result.
- Foreign-key, uniqueness, enum, temporal, lifecycle, reconciliation, and duplicate checks run before export. A deliberate anomaly is retained only with a corresponding separate ground-truth label and reported validation issue.
