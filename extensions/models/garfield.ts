/**
 * Purpose-built Garfield review and repair loop.
 *
 * The Swamp workflow deliberately exposes this model as one long-running
 * method. Deterministic TypeScript owns validation, loop control, snapshots,
 * recovery records, and accounting; fresh Codex processes are used only for
 * semantic review and code editing.
 *
 * @module
 */

import { z } from "npm:zod@4";

const GlobalArgsSchema = z.object({});

export const ReviewLensSchema = z.enum([
  "behavior",
  "repoInstructions",
  "validation",
  "tests",
  "docs",
  "deadCode",
  "delayering",
  "types",
  "generatedDependencies",
  "comments",
  "minimalism",
  "interfaces",
  "state",
  "policies",
]);

const FindingEvidenceSchema = z.enum([
  "direct",
  "spec",
  "policy",
  "test",
  "validation",
  "missing",
  "inferred",
]);

/** A current-diff-caused concern that can be fixed without expanding intent. */
export const FindingSchema = z.object({
  severity: z.enum(["blocker", "high", "medium"]),
  lens: ReviewLensSchema,
  cause: z.enum(["introduced", "worsened", "stale", "missing-required"]),
  evidence: z.array(FindingEvidenceSchema).min(1),
  path: z.string().min(1),
  line: z.number().int().positive().nullable(),
  concern: z.string().min(1),
  impact: z.string().min(1),
  fix: z.string().min(1),
});

const ReviewAssignmentNameSchema = z.enum([
  "comprehensive",
  "contract",
  "implementation",
  "evidence",
  "interfaces",
  "state",
  "generatedDependencies",
  "policies",
  "verification",
]);

const ReviewCheckSchema = z.object({
  status: z.enum(["pass", "finding", "not-applicable"]),
  evidence: z.string().min(1),
});

const ReviewCoverageSchema = z.object({
  requestedBehavior: ReviewCheckSchema,
  compatibility: ReviewCheckSchema,
  boundaryBehavior: ReviewCheckSchema,
  failureBehavior: ReviewCheckSchema,
  stateAndSideEffects: ReviewCheckSchema,
  outputContract: ReviewCheckSchema,
  validationEvidence: ReviewCheckSchema,
  implementationMinimalism: ReviewCheckSchema,
  repositoryInstructions: ReviewCheckSchema,
  testsAndEvidence: ReviewCheckSchema,
  interfacesAndTypes: ReviewCheckSchema,
  generatedDependencies: ReviewCheckSchema,
  documentation: ReviewCheckSchema,
  deadCodeAndLayering: ReviewCheckSchema,
  policyCompliance: ReviewCheckSchema,
});

const ReviewAssignmentSchema = z.object({
  name: ReviewAssignmentNameSchema,
  lenses: z.array(ReviewLensSchema).min(1),
  reason: z.string().min(1),
});

const LensDecisionSchema = z.object({
  lens: ReviewLensSchema,
  status: z.enum(["applicable", "skipped"]),
  reason: z.string().min(1),
});

const ReviewPlanSchema = z.object({
  snapshotHash: z.string().min(1),
  risk: z.enum(["simple", "medium", "complex"]),
  reasons: z.array(z.string().min(1)).min(1),
  lenses: z.array(LensDecisionSchema),
  assignments: z.array(ReviewAssignmentSchema).min(1).max(8),
  instructionPaths: z.array(z.string()),
  policyPaths: z.array(z.string()),
  requiresVerification: z.boolean(),
});

/** Structured output required from every independent review process. */
export const ReviewSchema = z.object({
  assignment: ReviewAssignmentNameSchema,
  summary: z.string().min(1),
  coverage: ReviewCoverageSchema,
  findings: z.array(FindingSchema).max(20),
  deferred: z.array(z.string().min(1)).max(20).default([]),
}).superRefine((review, context) => {
  const findingChecks = Object.entries(review.coverage).filter(
    ([, check]) => check.status === "finding",
  );
  if (review.findings.length === 0 && findingChecks.length > 0) {
    context.addIssue({
      code: "custom",
      path: ["findings"],
      message: "coverage marked a finding but findings is empty",
    });
  }
  if (review.findings.length > 0 && findingChecks.length === 0) {
    context.addIssue({
      code: "custom",
      path: ["coverage"],
      message: "findings were returned without a finding coverage status",
    });
  }
});

const ReviewRecordSchema = z.object({
  cycle: z.number().int().positive(),
  assignment: ReviewAssignmentSchema,
  review: ReviewSchema,
});

const FindingDecisionSchema = z.object({
  finding: FindingSchema,
  disposition: z.enum(["accepted", "rejected", "deferred"]),
  rationale: z.string().min(1),
});

const SnapshotSchema = z.object({
  hash: z.string().min(1),
  status: z.string(),
  diff: z.string(),
  diffTruncated: z.boolean(),
  changedPaths: z.array(z.string()),
  capturedAt: z.iso.datetime(),
});

const ValidationSchema = z.object({
  command: z.array(z.string()).min(1),
  passed: z.boolean(),
  exitCode: z.number().int(),
  timedOut: z.boolean(),
  durationMs: z.number().int().nonnegative(),
  stdout: z.string(),
  stderr: z.string(),
  outputTruncated: z.boolean(),
});

const InvocationSchema = z.object({
  invocationId: z.string().min(1),
  agentId: z.string().min(1),
  role: z.enum(["review", "fix"]),
  assignment: ReviewAssignmentNameSchema.optional(),
  cycle: z.number().int().positive(),
  model: z.string().min(1),
  reasoningEffort: z.enum(["minimal", "low", "medium", "high", "xhigh"]),
  sandbox: z.enum(["read-only", "workspace-write"]),
  success: z.boolean(),
  exitCode: z.number().int(),
  timedOut: z.boolean(),
  durationMs: z.number().int().nonnegative(),
  toolDurationMs: z.number().int().nonnegative(),
  toolOutputBytes: z.number().int().nonnegative(),
  inputTokens: z.number().int().nonnegative(),
  cachedInputTokens: z.number().int().nonnegative(),
  outputTokens: z.number().int().nonnegative(),
  reasoningOutputTokens: z.number().int().nonnegative(),
  totalTokens: z.number().int().nonnegative(),
  promptHash: z.string().min(1),
  finalMessage: z.string(),
  finalMessageTruncated: z.boolean(),
  stderr: z.string(),
  stderrTruncated: z.boolean(),
  sessionCounting: z.literal("codex-exec-turn-deltas"),
  startedAt: z.iso.datetime(),
});

const CheckpointSchema = z.object({
  workItem: z.string().min(1),
  phase: z.enum([
    "snapshotted",
    "planned",
    "validated",
    "reviewed",
    "adjudicated",
    "actor_pending",
    "actor_completed",
    "verified",
    "passed",
    "blocked",
  ]),
  actorCalls: z.number().int().nonnegative(),
  snapshot: SnapshotSchema,
  plan: ReviewPlanSchema.optional(),
  validation: ValidationSchema.optional(),
  findings: z.array(FindingSchema),
  reviews: z.array(ReviewRecordSchema),
  decisions: z.array(FindingDecisionSchema),
  invocations: z.array(InvocationSchema),
  note: z.string().optional(),
  updatedAt: z.iso.datetime(),
});

const UsageSchema = z.object({
  inputTokens: z.number().int().nonnegative(),
  cachedInputTokens: z.number().int().nonnegative(),
  outputTokens: z.number().int().nonnegative(),
  reasoningOutputTokens: z.number().int().nonnegative(),
  totalTokens: z.number().int().nonnegative(),
});

const ResultSchema = z.object({
  workItem: z.string().min(1),
  runId: z.string().min(1),
  status: z.enum(["passed", "blocked"]),
  reason: z.string().min(1),
  actorCalls: z.number().int().nonnegative(),
  agentCalls: z.number().int().nonnegative(),
  snapshot: SnapshotSchema,
  plan: ReviewPlanSchema,
  validation: ValidationSchema,
  review: ReviewSchema.optional(),
  reviews: z.array(ReviewRecordSchema),
  decisions: z.array(FindingDecisionSchema),
  invocations: z.array(InvocationSchema),
  usage: UsageSchema,
  completedAt: z.iso.datetime(),
});

/** Arguments accepted by the single workflow-facing operation. */
export const RunArgsSchema = z.object({
  runId: z.string().min(1),
  workItem: z.string().min(1),
  workspaceDir: z.string().min(1),
  intent: z.string().min(1),
  validationProgram: z.string().min(1).default("./tools/validate.sh"),
  validationArgs: z.array(z.string()).default([]),
  codexPath: z.string().min(1).default("codex"),
  model: z.string().min(1).default("configured-default"),
  reasoningEffort: z.enum(["minimal", "low", "medium", "high", "xhigh"])
    .default("high"),
  agentTimeoutMs: z.number().int().min(1_000).max(7_200_000).default(1_800_000),
  maxActorCalls: z.number().int().min(0).max(2).default(2),
  maxReviewCalls: z.number().int().min(1).max(20).default(16),
  maxConcurrentReviewers: z.number().int().min(1).max(3).default(3),
});

type RunArgs = z.infer<typeof RunArgsSchema>;
type Finding = z.infer<typeof FindingSchema>;
type Review = z.infer<typeof ReviewSchema>;
type ReviewLens = z.infer<typeof ReviewLensSchema>;
type ReviewAssignment = z.infer<typeof ReviewAssignmentSchema>;
type ReviewPlan = z.infer<typeof ReviewPlanSchema>;
type ReviewRecord = z.infer<typeof ReviewRecordSchema>;
type FindingDecision = z.infer<typeof FindingDecisionSchema>;
type Snapshot = z.infer<typeof SnapshotSchema>;
type Validation = z.infer<typeof ValidationSchema>;
type Invocation = z.infer<typeof InvocationSchema>;

type Logger = {
  info: (message: string, properties?: Record<string, unknown>) => void;
  warning: (message: string, properties?: Record<string, unknown>) => void;
  error: (message: string, properties?: Record<string, unknown>) => void;
};

type ProcessResult = {
  stdout: string;
  stderr: string;
  exitCode: number;
  timedOut: boolean;
  durationMs: number;
};

type AgentResult = {
  invocation: Invocation;
  finalMessage: string;
};

const REVIEW_LENSES = ReviewLensSchema.options;
const REVIEW_COVERAGE_KEYS = [
  "requestedBehavior",
  "compatibility",
  "boundaryBehavior",
  "failureBehavior",
  "stateAndSideEffects",
  "outputContract",
  "validationEvidence",
  "implementationMinimalism",
  "repositoryInstructions",
  "testsAndEvidence",
  "interfacesAndTypes",
  "generatedDependencies",
  "documentation",
  "deadCodeAndLayering",
  "policyCompliance",
] as const;

const MAX_DIFF_BYTES = 80_000;
const MAX_VALIDATION_OUTPUT_BYTES = 20_000;
const MAX_AGENT_OUTPUT_BYTES = 8_000_000;
const MAX_AGENT_PREVIEW_BYTES = 8_000;
const PROTECTED_PATH_PREFIXES = [".git/", ".swamp/", ".agents/"];
const SENSITIVE_PATH_PATTERNS = [
  /(^|\/)\.env(?:\.|$)/i,
  /(^|\/)(?:credentials|secrets)\.(?:json|ya?ml|toml)$/i,
  /(^|\/)id_(?:rsa|dsa|ecdsa|ed25519)$/i,
  /\.(?:pem|key|p12|pfx)$/i,
];

const REVIEW_OUTPUT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["assignment", "summary", "coverage", "findings", "deferred"],
  properties: {
    assignment: {
      type: "string",
      enum: ReviewAssignmentNameSchema.options,
    },
    summary: { type: "string", minLength: 1 },
    coverage: {
      type: "object",
      additionalProperties: false,
      required: REVIEW_COVERAGE_KEYS,
      properties: Object.fromEntries(
        REVIEW_COVERAGE_KEYS.map((name) => [name, {
          type: "object",
          additionalProperties: false,
          required: ["status", "evidence"],
          properties: {
            status: {
              type: "string",
              enum: ["pass", "finding", "not-applicable"],
            },
            evidence: { type: "string", minLength: 1 },
          },
        }]),
      ),
    },
    findings: {
      type: "array",
      maxItems: 20,
      items: {
        type: "object",
        additionalProperties: false,
        required: [
          "severity",
          "lens",
          "cause",
          "evidence",
          "path",
          "line",
          "concern",
          "impact",
          "fix",
        ],
        properties: {
          severity: { type: "string", enum: ["blocker", "high", "medium"] },
          lens: { type: "string", enum: ReviewLensSchema.options },
          cause: {
            type: "string",
            enum: ["introduced", "worsened", "stale", "missing-required"],
          },
          evidence: {
            type: "array",
            minItems: 1,
            items: { type: "string", enum: FindingEvidenceSchema.options },
          },
          path: { type: "string", minLength: 1 },
          line: { type: ["integer", "null"], minimum: 1 },
          concern: { type: "string", minLength: 1 },
          impact: { type: "string", minLength: 1 },
          fix: { type: "string", minLength: 1 },
        },
      },
    },
    deferred: {
      type: "array",
      maxItems: 20,
      items: { type: "string", minLength: 1 },
    },
  },
};

const DEFAULT_REVIEW_ASSIGNMENT: ReviewAssignment = {
  name: "comprehensive",
  lenses: ["behavior", "repoInstructions", "validation", "minimalism"],
  reason: "default consolidated review",
};

const LENS_COVERAGE: Record<
  ReviewLens,
  Array<keyof z.infer<typeof ReviewCoverageSchema>>
> = {
  behavior: [
    "requestedBehavior",
    "compatibility",
    "boundaryBehavior",
    "failureBehavior",
    "outputContract",
  ],
  repoInstructions: ["repositoryInstructions"],
  validation: ["validationEvidence"],
  tests: ["testsAndEvidence"],
  docs: ["documentation"],
  deadCode: ["deadCodeAndLayering"],
  delayering: ["deadCodeAndLayering", "implementationMinimalism"],
  types: ["interfacesAndTypes"],
  generatedDependencies: ["generatedDependencies"],
  comments: ["implementationMinimalism"],
  minimalism: ["implementationMinimalism"],
  interfaces: ["interfacesAndTypes", "compatibility"],
  state: ["stateAndSideEffects", "failureBehavior"],
  policies: ["policyCompliance"],
};

/** Build an explicit applicability plan from stable diff and repository signals. */
export function buildReviewPlan(
  snapshot: Snapshot,
  repositoryFiles: string[] = [],
): ReviewPlan {
  const paths = snapshot.changedPaths;
  const lowerPaths = paths.map((path) => path.toLowerCase());
  const diff = snapshot.diff;
  const codeChanged = lowerPaths.some((path) =>
    /\.(?:c|cc|cpp|cs|go|java|js|jsx|kt|php|py|rb|rs|swift|ts|tsx)$/.test(path)
  );
  const testChanged = lowerPaths.some((path) =>
    /(?:^|\/)(?:test|tests|spec|specs)(?:\/|$)|(?:_test|\.test|\.spec)\./.test(
      path,
    )
  );
  const docsChanged = lowerPaths.some((path) =>
    /\.(?:md|mdx|rst)$/.test(path) || /(?:^|\/)docs?\//.test(path)
  );
  const generatedChanged = lowerPaths.some((path) =>
    /(?:^|\/)(?:generated|migrations?|schemas?|proto)(?:\/|$)/.test(path) ||
    /(?:lock|\.lock|go\.sum|package\.json|go\.mod|pyproject\.toml|requirements.*\.txt)$/
      .test(path)
  );
  const policyChanged = lowerPaths.some((path) =>
    /(?:^|\/)policies?\//.test(path)
  );
  const interfaceSignal =
    lowerPaths.some((path) =>
      /(?:^|\/)(?:api|cmd|routes?|controllers?|public)(?:\/|$)|openapi|\.proto$/
        .test(path)
    ) ||
    /\b(?:export|public|interface|type\s+\w+|struct|flag\.|route|endpoint|status code)\b/i
      .test(diff);
  const stateSignal =
    lowerPaths.some((path) =>
      /(?:^|\/)(?:store|storage|repository|repositories|db|database|migrations?|models?)(?:\/|$)/
        .test(path)
    ) ||
    /\b(?:save|write|delete|persist|audit|transaction|mutat|side effect)\w*\b/i
      .test(diff);
  const typeSignal = codeChanged &&
    /\b(?:interface|type\s+\w+|struct|schema|unknown|nullable|null|serialize|deserialize)\b/i
      .test(diff);
  const removalSignal =
    diff.split("\n").filter((line) =>
      line.startsWith("-") && !line.startsWith("---")
    ).length >= 5;
  const layeringSignal =
    /\b(?:adapter|wrapper|factory|coordinator|delegate|layer|fallback|guard|flag)\w*\b/i
      .test(diff);
  const commentSignal = diff.split("\n").some((line) =>
    /^\+\s*(?:\/\/|\/\*|\*|#)/.test(line)
  );
  const instructionPaths = repositoryFiles.filter((path) =>
    /(^|\/)AGENTS\.md$/i.test(path)
  ).sort();
  const policyPaths = repositoryFiles.filter((path) =>
    /(^|\/)policies\/.*\.md$/i.test(path) &&
    !/(^|\/)(?:README|policy-template)\.md$/i.test(path)
  ).sort();

  const applicability = new Map<
    ReviewLens,
    { applicable: boolean; reason: string }
  >();
  const decide = (
    lens: ReviewLens,
    applicable: boolean,
    reason: string,
  ): void => {
    applicability.set(lens, { applicable, reason });
  };
  decide("behavior", true, "behavior/spec review is mandatory");
  decide(
    "repoInstructions",
    true,
    "repository-instruction review is mandatory",
  );
  decide("validation", true, "validation review is mandatory");
  decide(
    "tests",
    codeChanged || testChanged,
    codeChanged
      ? "changed code creates a concrete test obligation"
      : "no code or test evidence changed",
  );
  decide(
    "docs",
    docsChanged || interfaceSignal,
    docsChanged
      ? "documentation changed"
      : interfaceSignal
      ? "interface changes may require documentation evidence"
      : "no documentation or user-facing interface signal",
  );
  decide(
    "deadCode",
    removalSignal,
    removalSignal
      ? "the diff removes or replaces enough code to risk leftovers"
      : "no material replacement or deletion signal",
  );
  decide(
    "delayering",
    layeringSignal,
    layeringSignal
      ? "the diff changes wrappers, flags, adapters, guards, or layering"
      : "no new indirection signal",
  );
  decide(
    "types",
    typeSignal,
    typeSignal
      ? "typed interfaces or serialization boundaries changed"
      : "no typed-boundary signal",
  );
  decide(
    "generatedDependencies",
    generatedChanged,
    generatedChanged
      ? "generated, schema, migration, manifest, or dependency files changed"
      : "no generated or dependency signal",
  );
  decide(
    "comments",
    commentSignal,
    commentSignal
      ? "comments or docstrings changed"
      : "no changed comment signal",
  );
  decide(
    "minimalism",
    codeChanged,
    codeChanged
      ? "changed code requires a minimalism review"
      : "no implementation code changed",
  );
  decide(
    "interfaces",
    interfaceSignal,
    interfaceSignal
      ? "public, module, CLI, API, or lifecycle boundaries changed"
      : "no interface-design signal",
  );
  decide(
    "state",
    stateSignal,
    stateSignal
      ? "storage, mutation, audit, or side-effect behavior changed"
      : "no state or side-effect signal",
  );
  decide(
    "policies",
    policyPaths.length > 0,
    policyPaths.length > 0
      ? "repository policies exist and must be checked for applicability"
      : "no source repository policy files were discovered",
  );

  const criticalSignals = [
    generatedChanged,
    policyChanged,
    lowerPaths.some((path) => /openapi|\.proto$|migrations?\//.test(path)),
  ]
    .filter(Boolean).length;
  const diffBytes = new TextEncoder().encode(diff).byteLength;
  let risk: ReviewPlan["risk"] = "simple";
  const reasons: string[] = [];
  if (paths.length >= 9 || diffBytes > 60_000 || criticalSignals >= 2) {
    risk = "complex";
    reasons.push("large or multi-domain diff requires specialist review");
  } else if (
    paths.length >= 5 || diffBytes > 30_000 || criticalSignals === 1
  ) {
    risk = "medium";
    reasons.push(
      "cross-cutting or contract-sensitive diff requires clustered review",
    );
  } else {
    reasons.push("contained diff qualifies for the consolidated fast path");
  }
  if (snapshot.diffTruncated) {
    risk = "complex";
    reasons.push(
      "truncated diff requires repository inspection by specialists",
    );
  }

  const lenses = REVIEW_LENSES.map((lens) => {
    const decision = applicability.get(lens)!;
    return {
      lens,
      status: decision.applicable ? "applicable" as const : "skipped" as const,
      reason: decision.reason,
    };
  });
  const applicable = (candidates: ReviewLens[]): ReviewLens[] =>
    candidates.filter((lens) => applicability.get(lens)?.applicable);
  const assignments: ReviewAssignment[] = [];
  const addAssignment = (
    name: ReviewAssignment["name"],
    candidates: ReviewLens[],
    reason: string,
  ): void => {
    const selected = applicable(candidates);
    if (selected.length > 0) {
      assignments.push({ name, lenses: selected, reason });
    }
  };

  if (risk === "simple") {
    addAssignment(
      "comprehensive",
      REVIEW_LENSES,
      "one evidence-backed reviewer covers all applicable lenses",
    );
  } else if (risk === "medium") {
    addAssignment(
      "contract",
      ["behavior", "interfaces", "state"],
      "review requested and compatibility contracts",
    );
    addAssignment("implementation", [
      "deadCode",
      "delayering",
      "types",
      "comments",
      "minimalism",
    ], "review implementation quality and boundaries");
    addAssignment("evidence", [
      "repoInstructions",
      "validation",
      "tests",
      "docs",
      "generatedDependencies",
      "policies",
    ], "review repository obligations and readiness evidence");
  } else {
    addAssignment("contract", ["behavior"], "independent behavior/spec review");
    addAssignment("implementation", [
      "deadCode",
      "delayering",
      "types",
      "comments",
      "minimalism",
    ], "focused implementation review");
    addAssignment("evidence", [
      "repoInstructions",
      "validation",
      "tests",
      "docs",
    ], "focused readiness-evidence review");
    addAssignment(
      "interfaces",
      ["interfaces"],
      "dedicated interface-contract review",
    );
    addAssignment("state", ["state"], "dedicated state and side-effect review");
    addAssignment(
      "generatedDependencies",
      ["generatedDependencies"],
      "dedicated generated and dependency review",
    );
    addAssignment("policies", ["policies"], "dedicated source-policy review");
  }

  return ReviewPlanSchema.parse({
    snapshotHash: snapshot.hash,
    risk,
    reasons,
    lenses,
    assignments,
    instructionPaths,
    policyPaths,
    requiresVerification: risk === "complex" || criticalSignals > 0,
  });
}

/** Select all initial assignments and only affected mandatory assignments later. */
export function selectReviewAssignments(
  plan: ReviewPlan,
  cycle: number,
  affectedLenses: ReviewLens[] = [],
): ReviewAssignment[] {
  if (cycle <= 1 || plan.risk === "simple") return plan.assignments;
  const affected = new Set(affectedLenses);
  const selected = plan.assignments.filter((assignment) =>
    assignment.lenses.includes("behavior") ||
    assignment.lenses.includes("validation") ||
    assignment.lenses.some((lens) => affected.has(lens))
  );
  return selected.length > 0 ? selected : plan.assignments;
}

/** Deterministically accept supported in-scope findings and record every decision. */
export function adjudicateFindings(
  records: ReviewRecord[],
  snapshot: Snapshot,
): FindingDecision[] {
  const decisions: FindingDecision[] = [];
  const seen = new Set<string>();
  for (const record of records) {
    for (const finding of record.review.findings) {
      const fingerprint = findingFingerprint(finding);
      if (seen.has(fingerprint)) {
        decisions.push({
          finding,
          disposition: "rejected",
          rationale: "duplicate of an already adjudicated finding",
        });
        continue;
      }
      seen.add(fingerprint);
      const hasGroundedEvidence = finding.evidence.some((evidence) =>
        evidence !== "inferred"
      );
      if (!hasGroundedEvidence) {
        decisions.push({
          finding,
          disposition: "deferred",
          rationale:
            "inferred-only concern lacks direct, spec, policy, test, validation, or missing-artifact evidence",
        });
        continue;
      }
      const changedPath = snapshot.changedPaths.includes(finding.path);
      const missingOrStale = finding.cause === "missing-required" ||
        finding.cause === "stale";
      if (finding.severity === "medium" && !changedPath && !missingOrStale) {
        decisions.push({
          finding,
          disposition: "deferred",
          rationale:
            "medium concern is outside changed paths and is not a stale or missing required artifact",
        });
        continue;
      }
      decisions.push({
        finding,
        disposition: "accepted",
        rationale:
          "grounded current-slice finding whose structured smallest fix preserves intent",
      });
    }
  }
  return FindingDecisionSchema.array().parse(decisions);
}

/** Convert a work-item identifier into a deterministic resource instance name. */
export function resourceKey(workItem: string): string {
  const slug = workItem.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")
    .replaceAll(/^-+|-+$/g, "").slice(0, 48) || "work-item";
  let hash = 2166136261;
  for (const character of workItem) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return `${slug}-${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

/** Parse changed paths from `git status --porcelain=v1`. */
export function changedPathsFromStatus(status: string): string[] {
  const paths = new Set<string>();
  for (const line of status.split("\n")) {
    if (line.length < 4) continue;
    let path = line.slice(3).trim();
    if (path.includes(" -> ")) path = path.split(" -> ", 2)[1];
    if (path.startsWith('"') && path.endsWith('"')) {
      path = path.slice(1, -1);
    }
    if (path) paths.add(path);
  }
  return [...paths].sort();
}

/** Parse the terminal response and exclusive usage from `codex exec --json`. */
export function parseCodexEvents(
  rawOutput: string,
  options: {
    invocationId: string;
    role: "review" | "fix";
    assignment?: ReviewAssignment["name"];
    cycle: number;
    model: string;
    reasoningEffort: RunArgs["reasoningEffort"];
    sandbox: "read-only" | "workspace-write";
    promptHash: string;
    exitCode: number;
    timedOut: boolean;
    durationMs: number;
    stderr: string;
    startedAt: string;
  },
): AgentResult {
  let agentId = options.invocationId;
  let finalMessage = "";
  let inputTokens = 0;
  let cachedInputTokens = 0;
  let outputTokens = 0;
  let reasoningOutputTokens = 0;
  let toolDurationMs = 0;
  let toolOutputBytes = 0;
  let completedTurns = 0;

  for (const line of rawOutput.split("\n")) {
    if (!line.trim().startsWith("{")) continue;
    let event: Record<string, unknown>;
    try {
      event = JSON.parse(line) as Record<string, unknown>;
    } catch {
      continue;
    }
    const eventType = String(event.type ?? "");
    if (eventType === "thread.started") {
      agentId = String(event.thread_id ?? event.threadId ?? agentId);
      continue;
    }
    if (eventType === "turn.completed") {
      const usage = isRecord(event.usage) ? event.usage : {};
      inputTokens += numeric(usage.input_tokens ?? usage.inputTokens);
      cachedInputTokens += numeric(
        usage.cached_input_tokens ?? usage.cachedInputTokens,
      );
      outputTokens += numeric(usage.output_tokens ?? usage.outputTokens);
      reasoningOutputTokens += numeric(
        usage.reasoning_output_tokens ?? usage.reasoningOutputTokens,
      );
      completedTurns += 1;
      continue;
    }
    const item = isRecord(event.item) ? event.item : undefined;
    if (!item || eventType !== "item.completed") continue;
    const itemType = String(item.type ?? "");
    if (itemType === "agent_message") {
      finalMessage = String(item.text ?? "");
      continue;
    }
    if (itemType === "command_execution" || itemType === "mcp_tool_call") {
      toolDurationMs += numeric(item.duration_ms ?? item.durationMs);
      const output = String(
        item.aggregated_output ?? item.aggregatedOutput ?? item.output ?? "",
      );
      toolOutputBytes += new TextEncoder().encode(output).byteLength;
    }
  }

  const success = options.exitCode === 0 && !options.timedOut &&
    completedTurns > 0 && finalMessage.length > 0;
  const finalMessagePreview = truncate(
    redactSensitiveText(finalMessage),
    MAX_AGENT_PREVIEW_BYTES,
  );
  const stderrPreview = truncate(
    redactSensitiveText(options.stderr),
    MAX_AGENT_PREVIEW_BYTES,
  );
  const invocation = InvocationSchema.parse({
    invocationId: options.invocationId,
    agentId,
    role: options.role,
    assignment: options.assignment,
    cycle: options.cycle,
    model: options.model,
    reasoningEffort: options.reasoningEffort,
    sandbox: options.sandbox,
    success,
    exitCode: options.exitCode,
    timedOut: options.timedOut,
    durationMs: options.durationMs,
    toolDurationMs,
    toolOutputBytes,
    inputTokens,
    cachedInputTokens,
    outputTokens,
    reasoningOutputTokens,
    // Codex input_tokens already includes cached_input_tokens.
    totalTokens: inputTokens + outputTokens,
    promptHash: options.promptHash,
    finalMessage: finalMessagePreview.text,
    finalMessageTruncated: finalMessagePreview.truncated,
    stderr: stderrPreview.text,
    stderrTruncated: stderrPreview.truncated,
    sessionCounting: "codex-exec-turn-deltas",
    startedAt: options.startedAt,
  });
  return { invocation, finalMessage };
}

/** Parse and validate a review response, tolerating only an outer JSON fence. */
export function parseReviewResponse(
  message: string,
  expectedAssignment: ReviewAssignment = DEFAULT_REVIEW_ASSIGNMENT,
): Review {
  let text = message.trim();
  if (text.startsWith("```")) {
    text = text.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  }
  const review = ReviewSchema.parse(JSON.parse(text));
  if (review.assignment !== expectedAssignment.name) {
    throw new Error(
      `review assignment mismatch: expected ${expectedAssignment.name}, got ${review.assignment}`,
    );
  }
  const requiredCoverage = new Set(
    expectedAssignment.lenses.flatMap((lens) => LENS_COVERAGE[lens]),
  );
  for (const key of requiredCoverage) {
    if (review.coverage[key].status === "not-applicable") {
      throw new Error(`${key} is required for ${expectedAssignment.name}`);
    }
  }
  for (const finding of review.findings) {
    if (!expectedAssignment.lenses.includes(finding.lens)) {
      throw new Error(
        `finding lens ${finding.lens} is outside assignment ${expectedAssignment.name}`,
      );
    }
    const mappedChecks = LENS_COVERAGE[finding.lens];
    if (
      !mappedChecks.some((key) => review.coverage[key].status === "finding")
    ) {
      throw new Error(
        `finding lens ${finding.lens} has no matching finding coverage status`,
      );
    }
  }
  return review;
}

/** Build the single consolidated no-edit review prompt. */
export function buildReviewPrompt(
  args: Pick<RunArgs, "intent" | "validationProgram" | "validationArgs">,
  snapshot: Snapshot,
  validation: Validation,
  assignment: ReviewAssignment = DEFAULT_REVIEW_ASSIGNMENT,
  plan?: ReviewPlan,
): string {
  const requiredCoverage = [
    ...new Set(
      assignment.lenses.flatMap((lens) => LENS_COVERAGE[lens]),
    ),
  ];
  const verification = assignment.name === "verification";
  return `You are the independent Garfield ${assignment.name} reviewer. Review only; do not edit files and do not spawn subagents.

User intent:
${args.intent}

Assigned review lenses:
${assignment.lenses.join("\n")}

Assignment reason:
${assignment.reason}

Review contract:
- Review only the current diff relative to HEAD and directly related files.
- Focus on the assigned lenses. Mark coverage outside those lenses not-applicable with a concrete reason.
- Read the applicable repository AGENTS.md instructions and only relevant repository skills and policies.
- Always check behavior/spec, repository instructions, and validation evidence.
- As applicable, check tests, storage invariants, API compatibility, generated artifacts, types, dead code, needless layering, comments, and implementation minimalism.
- A finding is actionable only when the current diff introduced or worsened it, made evidence stale, or omitted a required artifact.
- Include only blocker/high/medium findings whose smallest fix preserves the stated intent. Put adjacent or out-of-intent observations in deferred.
- Verify both requested behavior and compatibility when the flag or new path is absent.
- Convert every sentence of the user intent into testable invariants before judging the diff. Do not infer requirements from visible tests alone.
- Complete every structured coverage check with concrete code, test, validation, or not-applicable evidence. requestedBehavior, compatibility, validationEvidence, and implementationMinimalism are always applicable.
- For boundaryBehavior, inspect zero/empty, one, many, missing, and repeated cases whenever the changed domain admits them.
- For outputContract, compare exact text/shape, count grammar, ordering, errors, and exit behavior across zero, one, many, and compatibility paths. If the diff adds or changes user-visible output, this check is applicable.
- Treat bespoke output wording or control-flow special cases as findings when a uniform existing path expresses the requested contract and neither the intent nor repository conventions require the special case.
- For stateAndSideEffects, trace every write, mutation, event, and external effect in both the requested and compatibility paths.
- A coverage status of finding requires at least one actionable finding; a clear review cannot contain a finding status.
- Every finding must name its assigned lens, current-diff cause, and evidence labels. Inferred evidence cannot stand alone.
- Required non-not-applicable coverage keys for this assignment: ${
    requiredCoverage.join(", ")
  }.
${
    verification
      ? "- This is a final verification pass: verify intent preservation, validation sufficiency, and decision/defer evidence without re-reviewing unrelated details."
      : "- This is a review pass: return every material finding within the assigned lenses."
  }
- Return only the structured response required by the output schema.

Discovered repository instructions:
${plan?.instructionPaths.join("\n") || "(discover applicable AGENTS.md files)"}

Discovered repository policies:
${
    plan?.policyPaths.join("\n") ||
    "(none discovered by planner; inspect if needed)"
  }

Aggregate validation already passed:
${JSON.stringify(validation.command)} => ${validation.exitCode}

Changed paths:
${snapshot.changedPaths.join("\n") || "(none)"}

Current status:
${snapshot.status || "(clean)"}

Current diff${
    snapshot.diffTruncated
      ? " (truncated; inspect the workspace for the rest)"
      : ""
  }:
${snapshot.diff || "(empty)"}`;
}

/** Build the workspace-writing prompt for accepted review findings. */
export function buildFindingFixPrompt(
  intent: string,
  findings: Finding[],
  snapshot: Snapshot,
): string {
  return `You are the Garfield repair actor. Edit the current workspace directly. Do not spawn subagents.

User intent:
${intent}

Fix every accepted finding below with the smallest coherent change that preserves the user intent and existing behavior outside it:
${JSON.stringify(findings, null, 2)}

Rules:
- Read and follow repository AGENTS.md and the relevant repository skills/policies before editing.
- Preserve unrelated working-copy changes. Do not reset, revert, or commit.
- Do not broaden the feature, add speculative hardening, or change public behavior beyond the intent.
- Add or update focused tests when a finding identifies missing behavioral evidence.
- You may run targeted checks. The outer Garfield method will run the aggregate validation independently.
- Finish with a concise factual summary; control flow ignores your claims and re-observes the workspace.

Changed paths before repair:
${snapshot.changedPaths.join("\n") || "(none)"}`;
}

/** Build the actor prompt for a deterministic aggregate validation failure. */
export function buildValidationFixPrompt(
  intent: string,
  validation: Validation,
): string {
  return `You are the Garfield repair actor. Edit the current workspace directly. Do not spawn subagents.

User intent:
${intent}

The repository-owned aggregate validation failed. Diagnose and fix only failures caused by the current implementation slice while preserving unrelated work and behavior outside the intent.

Command: ${JSON.stringify(validation.command)}
Exit: ${validation.exitCode}${validation.timedOut ? " (timed out)" : ""}
stdout:
${validation.stdout || "(empty)"}
stderr:
${validation.stderr || "(empty)"}

Read and follow repository AGENTS.md and relevant skills/policies. Do not reset, revert, commit, broaden the feature, or spawn subagents. The outer Garfield method will rerun aggregate validation independently.`;
}

async function captureSnapshot(
  workspace: string,
  signal: AbortSignal,
): Promise<Snapshot> {
  const [status, diff] = await Promise.all([
    runChecked(
      ["git", "status", "--porcelain=v1", "--untracked-files=all"],
      workspace,
      signal,
    ),
    runChecked(
      ["git", "diff", "--binary", "HEAD", "--", "."],
      workspace,
      signal,
    ),
  ]);
  // Hash the raw content so snapshot identity tracks the true worktree state,
  // but never persist or prompt with unredacted text.
  const digest = await sha256(`${status.stdout}\n${diff.stdout}`);
  const bounded = truncate(redactSensitiveText(diff.stdout), MAX_DIFF_BYTES);
  return SnapshotSchema.parse({
    hash: digest,
    status: redactSensitiveText(status.stdout),
    diff: bounded.text,
    diffTruncated: bounded.truncated,
    changedPaths: changedPathsFromStatus(status.stdout),
    capturedAt: new Date().toISOString(),
  });
}

async function listRepositoryFiles(
  workspace: string,
  signal: AbortSignal,
): Promise<string[]> {
  const result = await runChecked(
    ["git", "ls-files", "-co", "--exclude-standard"],
    workspace,
    signal,
  );
  return result.stdout.split("\n").map((path) => path.trim()).filter(Boolean)
    .sort();
}

async function runValidation(
  args: RunArgs,
  workspace: string,
  signal: AbortSignal,
): Promise<Validation> {
  const workspaceReal = await Deno.realPath(workspace);
  if (
    args.validationProgram.startsWith("/") ||
    !args.validationProgram.includes("/")
  ) {
    throw new Error(
      "validationProgram must be a repository-relative executable path",
    );
  }
  const program = await Deno.realPath(
    `${workspaceReal}/${args.validationProgram}`,
  );
  if (program !== workspaceReal && !program.startsWith(`${workspaceReal}/`)) {
    throw new Error("validationProgram resolves outside workspaceDir");
  }
  const result = await runProcess([program, ...args.validationArgs], {
    cwd: workspaceReal,
    timeoutMs: Math.min(args.agentTimeoutMs, 600_000),
    signal,
  });
  const stdout = truncate(
    redactSensitiveText(result.stdout),
    MAX_VALIDATION_OUTPUT_BYTES,
  );
  const stderr = truncate(
    redactSensitiveText(result.stderr),
    MAX_VALIDATION_OUTPUT_BYTES,
  );
  return ValidationSchema.parse({
    command: [args.validationProgram, ...args.validationArgs],
    passed: result.exitCode === 0 && !result.timedOut,
    exitCode: result.exitCode,
    timedOut: result.timedOut,
    durationMs: result.durationMs,
    stdout: stdout.text,
    stderr: stderr.text,
    outputTruncated: stdout.truncated || stderr.truncated,
  });
}

async function runAgent(
  args: RunArgs,
  workspace: string,
  role: "review" | "fix",
  cycle: number,
  prompt: string,
  signal: AbortSignal,
  assignment?: ReviewAssignment["name"],
): Promise<AgentResult> {
  const invocationId = crypto.randomUUID();
  const startedAt = new Date().toISOString();
  const promptHash = await sha256(prompt);
  const sandbox = role === "review" ? "read-only" : "workspace-write";
  const modelName = args.model;
  let schemaPath: string | undefined;
  try {
    if (role === "review") {
      schemaPath = await Deno.makeTempFile({
        prefix: "garfield-review-",
        suffix: ".json",
      });
      await Deno.writeTextFile(
        schemaPath,
        JSON.stringify(REVIEW_OUTPUT_SCHEMA),
      );
    }
    const command = [
      args.codexPath,
      "exec",
      "--json",
      "--color",
      "never",
      "--skip-git-repo-check",
      "--ephemeral",
      "--disable",
      "multi_agent",
      "--sandbox",
      sandbox,
      "-c",
      'approval_policy="never"',
      "-c",
      `model_reasoning_effort="${args.reasoningEffort}"`,
    ];
    if (args.model !== "configured-default") {
      command.push("--model", args.model);
    }
    if (schemaPath) command.push("--output-schema", schemaPath);
    command.push("-");
    const process = await runProcess(command, {
      cwd: workspace,
      stdin: prompt,
      timeoutMs: args.agentTimeoutMs,
      signal,
    });
    if (
      new TextEncoder().encode(process.stdout).byteLength >
        MAX_AGENT_OUTPUT_BYTES
    ) {
      throw new Error(
        `Codex event stream exceeded ${MAX_AGENT_OUTPUT_BYTES} bytes`,
      );
    }
    return parseCodexEvents(process.stdout, {
      invocationId,
      role,
      assignment,
      cycle,
      model: modelName,
      reasoningEffort: args.reasoningEffort,
      sandbox,
      promptHash,
      exitCode: process.exitCode,
      timedOut: process.timedOut,
      durationMs: process.durationMs,
      stderr: process.stderr,
      startedAt,
    });
  } finally {
    if (schemaPath) await Deno.remove(schemaPath).catch(() => {});
  }
}

async function runChecked(
  command: string[],
  cwd: string,
  signal: AbortSignal,
): Promise<ProcessResult> {
  const result = await runProcess(command, { cwd, timeoutMs: 30_000, signal });
  if (result.exitCode !== 0 || result.timedOut) {
    // git stderr can echo remote URLs carrying embedded credentials.
    throw new Error(
      `${command.join(" ")} failed (${result.exitCode}): ${
        redactSensitiveText(result.stderr.trim())
      }`,
    );
  }
  return result;
}

async function runProcess(
  command: string[],
  options: {
    cwd: string;
    stdin?: string;
    timeoutMs: number;
    signal: AbortSignal;
  },
): Promise<ProcessResult> {
  if (options.signal.aborted) throw new Error("Garfield execution cancelled");
  const started = performance.now();
  const child = new Deno.Command(command[0], {
    args: command.slice(1),
    cwd: options.cwd,
    stdin: options.stdin === undefined ? "null" : "piped",
    stdout: "piped",
    stderr: "piped",
  }).spawn();
  let timedOut = false;
  let stopping = false;
  let killTimer: ReturnType<typeof setTimeout> | undefined;

  const stop = (timeout: boolean): void => {
    if (stopping) return;
    stopping = true;
    timedOut = timeout;
    try {
      child.kill("SIGTERM");
    } catch {
      return;
    }
    killTimer = setTimeout(() => {
      try {
        child.kill("SIGKILL");
      } catch {
        // Process already exited.
      }
    }, 5_000);
  };
  const abort = (): void => stop(false);
  options.signal.addEventListener("abort", abort, { once: true });
  const timeout = setTimeout(() => stop(true), options.timeoutMs);

  const stdoutPromise = new Response(child.stdout).text();
  const stderrPromise = new Response(child.stderr).text();
  if (options.stdin !== undefined) {
    const writer = child.stdin.getWriter();
    try {
      await writer.write(new TextEncoder().encode(options.stdin));
    } catch {
      // Early process failure is reflected in status/stderr below.
    } finally {
      await writer.close().catch(() => {});
    }
  }

  try {
    const [status, stdout, stderr] = await Promise.all([
      child.status,
      stdoutPromise,
      stderrPromise,
    ]);
    if (options.signal.aborted) throw new Error("Garfield execution cancelled");
    return {
      stdout,
      stderr,
      exitCode: status.code,
      timedOut,
      durationMs: Math.round(performance.now() - started),
    };
  } finally {
    clearTimeout(timeout);
    if (killTimer !== undefined) clearTimeout(killTimer);
    options.signal.removeEventListener("abort", abort);
  }
}

function assertActorScope(before: Snapshot, after: Snapshot): void {
  if (before.hash === after.hash) {
    throw new Error("actor_made_no_workspace_change");
  }
  const newProtected = after.changedPaths.filter((path) =>
    PROTECTED_PATH_PREFIXES.some((prefix) =>
      path === prefix.slice(0, -1) || path.startsWith(prefix)
    ) &&
    !before.changedPaths.includes(path)
  );
  if (newProtected.length > 0) {
    throw new Error(`actor_changed_protected_paths:${newProtected.join(",")}`);
  }
}

function assertNoSensitiveChanges(snapshot: Snapshot): void {
  const sensitive = snapshot.changedPaths.filter((path) =>
    SENSITIVE_PATH_PATTERNS.some((pattern) => pattern.test(path))
  );
  if (sensitive.length > 0) {
    throw new Error(
      `changed_sensitive_paths_not_safe_for_agent_prompt:${
        sensitive.join(",")
      }`,
    );
  }
  // The diff is redacted before it reaches this point, so key material shows up
  // as the redaction marker rather than the PEM header. Match both: the raw
  // header alone would silently stop firing once redaction is applied.
  if (
    /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/i.test(snapshot.diff) ||
    snapshot.diff.includes("<redacted-private-key>")
  ) {
    throw new Error("changed_private_key_material_not_safe_for_agent_prompt");
  }
}

function aggregateUsage(
  invocations: Invocation[],
): z.infer<typeof UsageSchema> {
  const result = {
    inputTokens: 0,
    cachedInputTokens: 0,
    outputTokens: 0,
    reasoningOutputTokens: 0,
    totalTokens: 0,
  };
  for (const invocation of invocations) {
    result.inputTokens += invocation.inputTokens;
    result.cachedInputTokens += invocation.cachedInputTokens;
    result.outputTokens += invocation.outputTokens;
    result.reasoningOutputTokens += invocation.reasoningOutputTokens;
    result.totalTokens += invocation.totalTokens;
  }
  return UsageSchema.parse(result);
}

function findingFingerprint(finding: Finding): string {
  const concern = finding.concern.toLowerCase().replaceAll(/\s+/g, " ").trim();
  return [finding.lens, finding.path, finding.line ?? "", concern].join("|");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function numeric(value: unknown): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) && parsed >= 0 ? Math.trunc(parsed) : 0;
}

function redactSensitiveText(value: string): string {
  return value
    .replace(/(authorization\s*:\s*bearer\s+)[^\s]+/gi, "$1<redacted>")
    .replace(
      /((?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*)[^\s,;]+/gi,
      "$1<redacted>",
    )
    .replace(
      /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/gi,
      "<redacted-private-key>",
    );
}

async function sha256(value: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(value),
  );
  return [...new Uint8Array(digest)].map((byte) =>
    byte.toString(16).padStart(2, "0")
  ).join("");
}

function truncate(
  value: string,
  maxBytes: number,
): { text: string; truncated: boolean } {
  const bytes = new TextEncoder().encode(value);
  if (bytes.byteLength <= maxBytes) return { text: value, truncated: false };
  return {
    text: new TextDecoder().decode(bytes.slice(0, maxBytes)) +
      "\n<garfield-truncated>",
    truncated: true,
  };
}

/** Swamp model exposing the complete bounded Garfield operation. */
export const model = {
  type: "@adam/garfield",
  version: "2026.07.14.1",
  globalArguments: GlobalArgsSchema,
  resources: {
    checkpoint: {
      description:
        "Latest durable phase and accounting checkpoint for a Garfield work item",
      schema: CheckpointSchema,
      lifetime: "infinite",
      garbageCollection: 20,
    },
    result: {
      description:
        "Terminal Garfield verdict, evidence, and complete flat agent accounting",
      schema: ResultSchema,
      lifetime: "infinite",
      garbageCollection: 10,
    },
  },
  methods: {
    run: {
      description:
        "Run the bounded validate, review, repair, and independent re-review loop",
      arguments: RunArgsSchema,
      execute: async (
        rawArgs: RunArgs,
        context: {
          signal: AbortSignal;
          logger: Logger;
          readResource: (
            name: string,
            version?: number,
          ) => Promise<Record<string, unknown> | null>;
          writeResource: (
            specName: string,
            name: string,
            data: Record<string, unknown>,
          ) => Promise<{ name: string }>;
        },
      ): Promise<{ dataHandles: Array<{ name: string }> }> => {
        const args = RunArgsSchema.parse(rawArgs);
        const workspace = await Deno.realPath(args.workspaceDir);
        const key = resourceKey(args.workItem);
        const checkpointName = `checkpoint-${key}`;
        const resultName = `result-${key}`;
        const existing = await context.readResource(checkpointName);
        let actorCalls = 0;
        let invocations: Invocation[] = [];
        let reviews: ReviewRecord[] = [];
        let decisions: FindingDecision[] = [];
        let plan: ReviewPlan | undefined;
        let affectedLenses: ReviewLens[] = [];
        let reviewCalls = 0;
        let snapshot = await captureSnapshot(workspace, context.signal);
        assertNoSensitiveChanges(snapshot);
        context.logger.info("Starting Garfield run {workItem}", {
          workItem: args.workItem,
          snapshot: snapshot.hash,
        });

        const existingResult = await context.readResource(resultName);
        if (existingResult) {
          const parsedResult = ResultSchema.safeParse(existingResult);
          if (
            parsedResult.success && parsedResult.data.status === "passed" &&
            parsedResult.data.workItem === args.workItem &&
            parsedResult.data.snapshot.hash === snapshot.hash
          ) {
            context.logger.info("Garfield run {workItem} is already complete", {
              workItem: args.workItem,
            });
            const handle = await context.writeResource(
              "result",
              resultName,
              parsedResult.data,
            );
            return { dataHandles: [handle] };
          }
        }

        if (existing) {
          const checkpoint = CheckpointSchema.safeParse(existing);
          if (
            checkpoint.success && checkpoint.data.workItem === args.workItem &&
            checkpoint.data.snapshot.hash === snapshot.hash
          ) {
            actorCalls = checkpoint.data.actorCalls;
            invocations = checkpoint.data.invocations;
            reviews = checkpoint.data.reviews;
            decisions = checkpoint.data.decisions;
            plan = checkpoint.data.plan;
            affectedLenses = [
              ...new Set<ReviewLens>([
                "behavior",
                "validation",
                ...decisions.filter((decision) =>
                  decision.disposition === "accepted"
                ).map((decision) => decision.finding.lens),
              ]),
            ];
            reviewCalls = invocations.filter((invocation) =>
              invocation.role === "review"
            ).length;
            context.logger.info("Resuming Garfield checkpoint {phase}", {
              phase: checkpoint.data.phase,
              actorCalls,
            });
          } else if (
            checkpoint.success && checkpoint.data.phase === "actor_pending" &&
            checkpoint.data.snapshot.hash !== snapshot.hash
          ) {
            throw new Error(
              "Workspace changed after a pending actor checkpoint; refusing incomplete accounting",
            );
          }
        }

        let lastCheckpoint: { name: string } | undefined;
        const checkpoint = async (
          phase: z.infer<typeof CheckpointSchema>["phase"],
          validation?: Validation,
          findings: Finding[] = [],
          note?: string,
        ): Promise<void> => {
          const payload = CheckpointSchema.parse({
            workItem: args.workItem,
            phase,
            actorCalls,
            snapshot,
            plan,
            validation,
            findings,
            reviews,
            decisions,
            invocations,
            note,
            updatedAt: new Date().toISOString(),
          });
          lastCheckpoint = await context.writeResource(
            "checkpoint",
            checkpointName,
            payload,
          );
        };

        let lastValidation: Validation | undefined;
        let lastReview: Review | undefined;
        let terminalFindings: Finding[] = [];
        const finish = async (
          status: "passed" | "blocked",
          reason: string,
        ): Promise<{ dataHandles: Array<{ name: string }> }> => {
          if (!lastValidation) {
            throw new Error(
              "Cannot finalize Garfield without validation evidence",
            );
          }
          if (!plan) {
            const repositoryFiles = await listRepositoryFiles(
              workspace,
              context.signal,
            );
            plan = buildReviewPlan(snapshot, repositoryFiles);
          }
          await checkpoint(
            status,
            lastValidation,
            terminalFindings,
            reason,
          );
          const result = ResultSchema.parse({
            workItem: args.workItem,
            runId: args.runId,
            status,
            reason,
            actorCalls,
            agentCalls: invocations.length,
            snapshot,
            plan,
            validation: lastValidation,
            review: lastReview,
            reviews,
            decisions,
            invocations,
            usage: aggregateUsage(invocations),
            completedAt: new Date().toISOString(),
          });
          const resultHandle = await context.writeResource(
            "result",
            resultName,
            result,
          );
          const handles = lastCheckpoint
            ? [lastCheckpoint, resultHandle]
            : [resultHandle];
          if (status === "blocked") {
            context.logger.warning(
              "Blocked Garfield run {workItem}: {reason}",
              {
                workItem: args.workItem,
                reason,
              },
            );
            throw new Error(`Garfield blocked: ${reason}`);
          }
          context.logger.info(
            "Completed Garfield run {workItem} with {agentCalls} agent calls",
            {
              workItem: args.workItem,
              agentCalls: invocations.length,
            },
          );
          return { dataHandles: handles };
        };
        const invoke = async (
          role: "review" | "fix",
          cycle: number,
          prompt: string,
          assignment?: ReviewAssignment["name"],
        ): Promise<AgentResult | null> => {
          try {
            return await runAgent(
              args,
              workspace,
              role,
              cycle,
              prompt,
              context.signal,
              assignment,
            );
          } catch (error) {
            // Cancellation is not a semantic review failure. Swallowing it here
            // would persist an infinite-lifetime "blocked" verdict for a run the
            // caller aborted, so let it propagate.
            if (context.signal.aborted) throw error;
            context.logger.error(
              "Garfield {role} process could not be completed: {error}",
              {
                role,
                error: error instanceof Error ? error.message : String(error),
              },
            );
            return null;
          }
        };

        const runReviewAssignments = async (
          assignments: ReviewAssignment[],
          cycle: number,
        ): Promise<{ records: ReviewRecord[]; failure?: string }> => {
          if (reviewCalls + assignments.length > args.maxReviewCalls) {
            return { records: [], failure: "review_call_limit_reached" };
          }
          const records: ReviewRecord[] = [];
          let failure: string | undefined;
          for (
            let offset = 0;
            offset < assignments.length && !failure;
            offset += args.maxConcurrentReviewers
          ) {
            const batch = assignments.slice(
              offset,
              offset + args.maxConcurrentReviewers,
            );
            const results = await Promise.all(batch.map(async (assignment) => ({
              assignment,
              reviewer: await invoke(
                "review",
                cycle,
                buildReviewPrompt(
                  args,
                  snapshot,
                  lastValidation!,
                  assignment,
                  plan,
                ),
                assignment.name,
              ),
            })));
            for (const { assignment, reviewer } of results) {
              reviewCalls += 1;
              if (!reviewer) {
                failure ??= `review_execution_error:${assignment.name}`;
                continue;
              }
              invocations.push(reviewer.invocation);
              if (!reviewer.invocation.success) {
                failure ??= `review_process_failed:${assignment.name}`;
                continue;
              }
              try {
                const review = parseReviewResponse(
                  reviewer.finalMessage,
                  assignment,
                );
                lastReview = review;
                records.push({ cycle, assignment, review });
              } catch (error) {
                context.logger.error(
                  "Review response for {assignment} failed schema validation",
                  {
                    assignment: assignment.name,
                    error: error instanceof Error
                      ? error.message
                      : String(error),
                  },
                );
                failure ??= `malformed_review_response:${assignment.name}`;
              }
            }
          }
          reviews.push(...records);
          return { records, failure };
        };

        while (true) {
          await checkpoint("snapshotted");
          const repositoryFiles = await listRepositoryFiles(
            workspace,
            context.signal,
          );
          plan = buildReviewPlan(snapshot, repositoryFiles);
          await checkpoint("planned");
          context.logger.info("Validating snapshot {hash}", {
            hash: snapshot.hash,
          });
          lastValidation = await runValidation(args, workspace, context.signal);
          await checkpoint("validated", lastValidation);

          if (!lastValidation.passed) {
            if (actorCalls >= args.maxActorCalls) {
              terminalFindings = [];
              return await finish(
                "blocked",
                "validation_failed_after_actor_limit",
              );
            }
            await checkpoint(
              "actor_pending",
              lastValidation,
              [],
              "repair aggregate validation failure",
            );
            const actor = await invoke(
              "fix",
              actorCalls + 1,
              buildValidationFixPrompt(args.intent, lastValidation),
            );
            if (!actor) return await finish("blocked", "actor_execution_error");
            invocations.push(actor.invocation);
            actorCalls += 1;
            if (!actor.invocation.success) {
              return await finish("blocked", "actor_process_failed");
            }
            const before = snapshot;
            snapshot = await captureSnapshot(workspace, context.signal);
            try {
              assertNoSensitiveChanges(snapshot);
              assertActorScope(before, snapshot);
            } catch (error) {
              return await finish(
                "blocked",
                error instanceof Error ? error.message : String(error),
              );
            }
            affectedLenses = ["behavior", "validation"];
            plan = undefined;
            await checkpoint("actor_completed", lastValidation);
            continue;
          }

          const reviewCycle = actorCalls + 1;
          const assignments = selectReviewAssignments(
            plan,
            reviewCycle,
            affectedLenses,
          );
          context.logger.info(
            "Reviewing validated snapshot {hash} with {reviewers} assignments",
            {
              hash: snapshot.hash,
              reviewers: assignments.length,
              risk: plan.risk,
            },
          );
          const reviewBatch = await runReviewAssignments(
            assignments,
            reviewCycle,
          );
          if (reviewBatch.failure) {
            terminalFindings = reviewBatch.records.flatMap((record) =>
              record.review.findings
            );
            return await finish("blocked", reviewBatch.failure);
          }
          const rawFindings = reviewBatch.records.flatMap((record) =>
            record.review.findings
          );
          await checkpoint("reviewed", lastValidation, rawFindings);

          let cycleDecisions = adjudicateFindings(
            reviewBatch.records,
            snapshot,
          );
          decisions.push(...cycleDecisions);
          let accepted = cycleDecisions.filter((decision) =>
            decision.disposition === "accepted"
          ).map((decision) => decision.finding);
          terminalFindings = accepted;
          await checkpoint("adjudicated", lastValidation, accepted);

          if (accepted.length === 0 && plan.requiresVerification) {
            const applicableLenses = new Set(
              plan.lenses.filter((decision) => decision.status === "applicable")
                .map((decision) => decision.lens),
            );
            const verificationCandidates: ReviewLens[] = [
              "behavior",
              "repoInstructions",
              "validation",
              "tests",
              "interfaces",
              "state",
              "generatedDependencies",
              "policies",
            ];
            const verification: ReviewAssignment = {
              name: "verification",
              lenses: verificationCandidates.filter((lens) =>
                applicableLenses.has(lens)
              ),
              reason:
                "risk-based final advisor verifies intent preservation and readiness evidence",
            };
            const verificationBatch = await runReviewAssignments(
              [verification],
              reviewCycle,
            );
            if (verificationBatch.failure) {
              terminalFindings = verificationBatch.records.flatMap((record) =>
                record.review.findings
              );
              return await finish("blocked", verificationBatch.failure);
            }
            cycleDecisions = adjudicateFindings(
              verificationBatch.records,
              snapshot,
            );
            decisions.push(...cycleDecisions);
            accepted = cycleDecisions.filter((decision) =>
              decision.disposition === "accepted"
            ).map((decision) => decision.finding);
            terminalFindings = accepted;
            await checkpoint("verified", lastValidation, accepted);
          }

          if (accepted.length === 0) {
            terminalFindings = [];
            return await finish(
              "passed",
              "validation_and_adaptive_review_clear",
            );
          }

          const repeated = accepted.find((finding) =>
            decisions.filter((decision) =>
              decision.disposition === "accepted" &&
              findingFingerprint(decision.finding) ===
                findingFingerprint(finding)
            ).length >= 2
          );
          if (repeated) {
            terminalFindings = [repeated];
            return await finish("blocked", "repeated_finding_without_progress");
          }
          if (actorCalls >= args.maxActorCalls) {
            return await finish("blocked", "findings_remain_after_actor_limit");
          }

          await checkpoint(
            "actor_pending",
            lastValidation,
            accepted,
            "repair accepted review findings",
          );
          const actor = await invoke(
            "fix",
            actorCalls + 1,
            buildFindingFixPrompt(args.intent, accepted, snapshot),
          );
          if (!actor) return await finish("blocked", "actor_execution_error");
          invocations.push(actor.invocation);
          actorCalls += 1;
          if (!actor.invocation.success) {
            return await finish("blocked", "actor_process_failed");
          }
          const before = snapshot;
          snapshot = await captureSnapshot(workspace, context.signal);
          try {
            assertNoSensitiveChanges(snapshot);
            assertActorScope(before, snapshot);
          } catch (error) {
            return await finish(
              "blocked",
              error instanceof Error ? error.message : String(error),
            );
          }
          affectedLenses = [
            ...new Set<ReviewLens>([
              "behavior",
              "validation",
              ...accepted.map((finding) => finding.lens),
            ]),
          ];
          plan = undefined;
          await checkpoint(
            "actor_completed",
            lastValidation,
            accepted,
          );
        }
      },
    },
  },
};
