import {
  assertEquals,
  assertRejects,
  assertStringIncludes,
  assertThrows,
} from "jsr:@std/assert@1.0.19";

import {
  adjudicateFindings,
  buildReviewPlan,
  buildReviewPrompt,
  changedPathsFromStatus,
  model,
  parseCodexEvents,
  parseReviewResponse,
  resourceKey,
  selectReviewAssignments,
} from "./garfield.ts";

const CLEAR_REVIEW = {
  assignment: "comprehensive",
  summary: "clear",
  coverage: {
    requestedBehavior: { status: "pass", evidence: "diff implements intent" },
    compatibility: { status: "pass", evidence: "existing path is unchanged" },
    boundaryBehavior: {
      status: "pass",
      evidence: "zero, one, many, missing, and repeated cases do not vary",
    },
    failureBehavior: {
      status: "pass",
      evidence: "the fixture introduces and changes no failure path",
    },
    stateAndSideEffects: {
      status: "not-applicable",
      evidence: "the fixture performs no stateful operation",
    },
    outputContract: {
      status: "pass",
      evidence: "the fixture changes no user-visible output contract",
    },
    validationEvidence: {
      status: "pass",
      evidence: "aggregate validation passed",
    },
    implementationMinimalism: {
      status: "pass",
      evidence: "the diff adds no unnecessary branch or layer",
    },
    repositoryInstructions: {
      status: "pass",
      evidence: "no additional repository instructions apply",
    },
    testsAndEvidence: {
      status: "not-applicable",
      evidence: "the fixture changes no implementation code",
    },
    interfacesAndTypes: {
      status: "not-applicable",
      evidence: "the fixture changes no interface or type boundary",
    },
    generatedDependencies: {
      status: "not-applicable",
      evidence: "the fixture changes no generated or dependency artifact",
    },
    documentation: {
      status: "not-applicable",
      evidence: "the fixture changes no behavior requiring documentation",
    },
    deadCodeAndLayering: {
      status: "not-applicable",
      evidence: "the fixture neither removes code nor adds a layer",
    },
    policyCompliance: {
      status: "not-applicable",
      evidence: "the fixture repository has no source policies",
    },
  },
  findings: [],
  deferred: [],
};

Deno.test("model exposes one operational method and two resources", () => {
  assertEquals(model.type, "@adam/garfield");
  assertEquals(Object.keys(model.methods), ["run"]);
  assertEquals(Object.keys(model.resources), ["checkpoint", "result"]);
});

Deno.test("resourceKey is stable and storage safe", () => {
  const first = resourceKey("garfield-bench:contained:r1:abc");
  assertEquals(first, resourceKey("garfield-bench:contained:r1:abc"));
  assertEquals(/^[a-z0-9-]+$/.test(first), true);
});

Deno.test("changedPathsFromStatus handles ordinary and renamed paths", () => {
  assertEquals(
    changedPathsFromStatus(
      " M internal/a.go\nR  old.go -> new.go\n?? added.go\n",
    ),
    ["added.go", "internal/a.go", "new.go"],
  );
});

Deno.test("review planner keeps contained work on one comprehensive review", () => {
  const plan = buildReviewPlan({
    hash: "simple",
    status: " M service.ts\n",
    diff: "+export function enabled() { return true; }",
    diffTruncated: false,
    changedPaths: ["service.ts"],
    capturedAt: "2026-07-14T00:00:00.000Z",
  }, ["AGENTS.md", "service.ts", "service_test.ts"]);
  assertEquals(plan.risk, "simple");
  assertEquals(plan.assignments.map((assignment) => assignment.name), [
    "comprehensive",
  ]);
  assertEquals(plan.instructionPaths, ["AGENTS.md"]);
});

Deno.test("review planner expands complex contract-sensitive work", () => {
  const changedPaths = [
    "api/openapi.json",
    "cmd/root.ts",
    "generated/client.ts",
    "migrations/001.sql",
    "package-lock.json",
    "src/repository.ts",
    "src/service.ts",
    "tests/service_test.ts",
    "docs/api.md",
  ];
  const plan = buildReviewPlan({
    hash: "complex",
    status: changedPaths.map((path) => ` M ${path}`).join("\n"),
    diff: "+export interface Request { state: string }\n+save(request);",
    diffTruncated: false,
    changedPaths,
    capturedAt: "2026-07-14T00:00:00.000Z",
  }, [...changedPaths, "policies/release.md"]);
  assertEquals(plan.risk, "complex");
  assertEquals(plan.requiresVerification, true);
  assertEquals(plan.assignments.map((assignment) => assignment.name), [
    "contract",
    "implementation",
    "evidence",
    "interfaces",
    "state",
    "generatedDependencies",
    "policies",
  ]);
});

Deno.test("post-fix review selection retains mandatory assignments", () => {
  const plan = buildReviewPlan({
    hash: "medium",
    status: " M api/openapi.json\n",
    diff: "+route endpoint",
    diffTruncated: false,
    changedPaths: [
      "api/openapi.json",
      "src/a.ts",
      "src/b.ts",
      "test/a_test.ts",
      "docs/a.md",
    ],
    capturedAt: "2026-07-14T00:00:00.000Z",
  });
  assertEquals(plan.risk, "medium");
  assertEquals(
    selectReviewAssignments(plan, 2).map((assignment) => assignment.name),
    ["contract", "evidence"],
  );
});

Deno.test("finding adjudication accepts evidence, rejects duplicates, and defers inference", () => {
  const grounded = {
    severity: "high",
    lens: "behavior",
    cause: "introduced",
    evidence: ["direct"],
    path: "service.ts",
    line: 8,
    concern: "The compatibility path now returns the new value.",
    impact: "Existing callers change behavior.",
    fix: "Restore the previous compatibility branch.",
  };
  const inferred = {
    ...grounded,
    severity: "medium",
    evidence: ["inferred"],
    line: 12,
    concern: "A future caller may need another branch.",
  };
  const findingReview = (findings: unknown[]) => ({
    assignment: "contract",
    summary: "findings",
    coverage: {
      ...structuredClone(CLEAR_REVIEW.coverage),
      requestedBehavior: {
        status: "finding",
        evidence: "the changed compatibility branch is visible in the diff",
      },
    },
    findings,
    deferred: [],
  });
  const assignment = {
    name: "contract",
    lenses: ["behavior"],
    reason: "contract review",
  };
  const records = [
    { cycle: 1, assignment, review: findingReview([grounded]) },
    { cycle: 1, assignment, review: findingReview([grounded, inferred]) },
  ] as unknown as Parameters<typeof adjudicateFindings>[0];
  const decisions = adjudicateFindings(records, {
    hash: "snapshot",
    status: " M service.ts\n",
    diff: "+ changed",
    diffTruncated: false,
    changedPaths: ["service.ts"],
    capturedAt: "2026-07-14T00:00:00.000Z",
  });
  assertEquals(decisions.map((decision) => decision.disposition), [
    "accepted",
    "rejected",
    "deferred",
  ]);
});

Deno.test("Codex accounting treats cached input as a subset", () => {
  const stream = [
    JSON.stringify({ type: "thread.started", thread_id: "thread-1" }),
    JSON.stringify({
      type: "item.completed",
      item: {
        type: "agent_message",
        text: JSON.stringify(CLEAR_REVIEW),
      },
    }),
    JSON.stringify({
      type: "turn.completed",
      usage: {
        input_tokens: 100,
        cached_input_tokens: 80,
        output_tokens: 20,
        reasoning_output_tokens: 7,
      },
    }),
  ].join("\n");
  const result = parseCodexEvents(stream, {
    invocationId: "invocation-1",
    role: "review",
    cycle: 1,
    model: "test-model",
    reasoningEffort: "high",
    sandbox: "read-only",
    promptHash: "abc",
    exitCode: 0,
    timedOut: false,
    durationMs: 42,
    stderr: "",
    startedAt: "2026-07-14T00:00:00.000Z",
  });
  assertEquals(result.invocation.inputTokens, 100);
  assertEquals(result.invocation.cachedInputTokens, 80);
  assertEquals(result.invocation.outputTokens, 20);
  assertEquals(result.invocation.totalTokens, 120);
  assertEquals(result.invocation.agentId, "thread-1");
  assertEquals(result.invocation.finalMessageTruncated, false);
  assertEquals(result.invocation.stderrTruncated, false);
});

Deno.test("review parser requires complete evidence-backed coverage", () => {
  assertEquals(
    parseReviewResponse(JSON.stringify(CLEAR_REVIEW)).findings,
    [],
  );
  assertThrows(() =>
    parseReviewResponse('{"summary":"clear","findings":[],"deferred":[]}')
  );
});

Deno.test("review parser rejects internally inconsistent clearance", () => {
  const inconsistent = structuredClone(CLEAR_REVIEW);
  inconsistent.coverage.outputContract = {
    status: "finding",
    evidence: "a zero-result branch changes the output grammar",
  };
  assertThrows(() => parseReviewResponse(JSON.stringify(inconsistent)));
});

Deno.test("review parser allows one root finding to affect several coverage lenses", () => {
  const crossLens = structuredClone(CLEAR_REVIEW) as
    & Omit<
      typeof CLEAR_REVIEW,
      "findings"
    >
    & { findings: Array<Record<string, unknown>> };
  crossLens.coverage.requestedBehavior = {
    status: "finding",
    evidence: "the compatibility branch changed",
  };
  crossLens.coverage.stateAndSideEffects = {
    status: "finding",
    evidence: "the same behavior defect also performs a write",
  };
  crossLens.findings = [{
    severity: "high",
    lens: "behavior",
    cause: "introduced",
    evidence: ["direct"],
    path: "service.ts",
    line: 8,
    concern: "The compatibility path changed.",
    impact: "Existing callers observe new behavior.",
    fix: "Restore the compatibility path.",
  }];
  assertEquals(
    parseReviewResponse(JSON.stringify(crossLens)).findings.length,
    1,
  );
});

Deno.test("review parser rejects low findings", () => {
  const invalid = structuredClone(CLEAR_REVIEW) as Record<string, unknown>;
  invalid.findings = [{
    severity: "low",
    lens: "behavior",
    cause: "introduced",
    evidence: ["direct"],
    path: "a",
    line: null,
    concern: "c",
    impact: "i",
    fix: "f",
  }];
  assertThrows(() => parseReviewResponse(JSON.stringify(invalid)));
});

Deno.test("review prompt includes intent, validation, and diff", () => {
  const prompt = buildReviewPrompt(
    {
      intent: "Preserve behavior without --dry-run.",
      validationProgram: "./tools/validate.sh",
      validationArgs: [],
    },
    {
      hash: "hash",
      status: " M service.go\n",
      diff: "+ changed",
      diffTruncated: false,
      changedPaths: ["service.go"],
      capturedAt: "2026-07-14T00:00:00.000Z",
    },
    {
      command: ["./tools/validate.sh"],
      passed: true,
      exitCode: 0,
      timedOut: false,
      durationMs: 1,
      stdout: "",
      stderr: "",
      outputTruncated: false,
    },
  );
  assertStringIncludes(prompt, "Preserve behavior without --dry-run.");
  assertStringIncludes(prompt, "./tools/validate.sh");
  assertStringIncludes(prompt, "+ changed");
  assertStringIncludes(prompt, "do not spawn subagents");
  assertStringIncludes(prompt, "zero, one, many");
  assertStringIncludes(prompt, "bespoke output wording");
  assertStringIncludes(prompt, "structured coverage check");
});

Deno.test("run completes an already-clear workspace with one review call", async () => {
  const root = await makeWorkspace(0);
  try {
    const codex = await makeFakeCodex(root);
    const stored = new Map<string, Record<string, unknown>>();
    const handles = await model.methods.run.execute(
      runArgs(root, codex, "clear-work-item", 2),
      testContext(stored),
    );
    assertEquals(handles.dataHandles.length, 2);
    const result = [...stored.entries()].find(([name]) =>
      name.startsWith("result-")
    )?.[1];
    assertEquals(result?.status, "passed");
    assertEquals(result?.agentCalls, 1);
    assertEquals(result?.actorCalls, 0);
    assertEquals((result?.usage as Record<string, unknown>).totalTokens, 120);
  } finally {
    await Deno.remove(root, { recursive: true });
  }
});

Deno.test("run expands complex work and verifies a clear verdict", async () => {
  const root = await makeWorkspace(0);
  try {
    const codex = await makeAdaptiveFakeCodex(root);
    await makeComplexWorkspaceDirty(root);
    const stored = new Map<string, Record<string, unknown>>();
    await model.methods.run.execute(
      runArgs(root, codex, "complex-work-item", 2),
      testContext(stored),
    );
    const result = [...stored.entries()].find(([name]) =>
      name.startsWith("result-")
    )?.[1];
    assertEquals(result?.status, "passed");
    assertEquals(result?.agentCalls, 8);
    assertEquals((result?.plan as Record<string, unknown>).risk, "complex");
    assertEquals(
      (result?.reviews as Array<Record<string, unknown>>).map((record) =>
        (record.assignment as Record<string, unknown>).name
      ),
      [
        "contract",
        "implementation",
        "evidence",
        "interfaces",
        "state",
        "generatedDependencies",
        "policies",
        "verification",
      ],
    );
    assertEquals((result?.usage as Record<string, unknown>).totalTokens, 960);
  } finally {
    await Deno.remove(root, { recursive: true });
  }
});

Deno.test("run persists a blocked result when validation cannot be repaired", async () => {
  const root = await makeWorkspace(1);
  try {
    const codex = await makeFakeCodex(root);
    const stored = new Map<string, Record<string, unknown>>();
    await assertRejects(
      () =>
        model.methods.run.execute(
          runArgs(root, codex, "blocked-work-item", 0),
          testContext(stored),
        ),
      Error,
      "validation_failed_after_actor_limit",
    );
    const result = [...stored.entries()].find(([name]) =>
      name.startsWith("result-")
    )?.[1];
    assertEquals(result?.status, "blocked");
    assertEquals(result?.agentCalls, 0);
    assertEquals((result?.validation as Record<string, unknown>).passed, false);
  } finally {
    await Deno.remove(root, { recursive: true });
  }
});

async function makeWorkspace(validationExit: number): Promise<string> {
  const root = await Deno.makeTempDir({ prefix: "garfield-model-test-" });
  await Deno.mkdir(`${root}/tools`, { recursive: true });
  await Deno.writeTextFile(`${root}/README.md`, "test workspace\n");
  await Deno.writeTextFile(
    `${root}/tools/validate.sh`,
    `#!/bin/sh\nexit ${validationExit}\n`,
  );
  await Deno.chmod(`${root}/tools/validate.sh`, 0o755);
  await command(root, ["git", "init", "--quiet"]);
  await command(root, ["git", "config", "user.name", "Garfield Test"]);
  await command(root, [
    "git",
    "config",
    "user.email",
    "garfield@example.invalid",
  ]);
  await command(root, ["git", "add", "."]);
  await command(root, ["git", "commit", "--quiet", "-m", "base"]);
  return root;
}

async function makeFakeCodex(root: string): Promise<string> {
  const path = `${root}/fake-codex.sh`;
  const final = JSON.stringify(CLEAR_REVIEW);
  await Deno.writeTextFile(
    path,
    `#!/bin/sh
cat >/dev/null
printf '%s\\n' '${
      JSON.stringify({ type: "thread.started", thread_id: "fake-thread" })
    }'
printf '%s\\n' '${
      JSON.stringify({
        type: "item.completed",
        item: { type: "agent_message", text: final },
      })
    }'
printf '%s\\n' '${
      JSON.stringify({
        type: "turn.completed",
        usage: {
          input_tokens: 100,
          cached_input_tokens: 80,
          output_tokens: 20,
          reasoning_output_tokens: 5,
        },
      })
    }'
`,
  );
  await Deno.chmod(path, 0o755);
  await command(root, ["git", "add", "fake-codex.sh"]);
  await command(root, ["git", "commit", "--quiet", "-m", "add fake codex"]);
  return path;
}

async function makeAdaptiveFakeCodex(root: string): Promise<string> {
  const path = `${root}/fake-adaptive-codex.sh`;
  const assignments = [
    "comprehensive",
    "contract",
    "implementation",
    "evidence",
    "interfaces",
    "state",
    "generatedDependencies",
    "policies",
    "verification",
  ];
  const responseFor = (assignment: string) => ({
    ...structuredClone(CLEAR_REVIEW),
    assignment,
    coverage: Object.fromEntries(
      Object.keys(CLEAR_REVIEW.coverage).map((key) => [key, {
        status: "pass",
        evidence: `${key} inspected for ${assignment}`,
      }]),
    ),
  });
  const cases = assignments.map((assignment) => {
    const event = JSON.stringify({
      type: "item.completed",
      item: {
        type: "agent_message",
        text: JSON.stringify(responseFor(assignment)),
      },
    });
    return `*"Garfield ${assignment} reviewer"*) event='${event}' ;;`;
  }).join("\n");
  await Deno.writeTextFile(
    path,
    `#!/bin/sh
input=$(cat)
case "$input" in
${cases}
*) exit 2 ;;
esac
printf '%s\\n' '${
      JSON.stringify({ type: "thread.started", thread_id: "adaptive-thread" })
    }'
printf '%s\\n' "$event"
printf '%s\\n' '${
      JSON.stringify({
        type: "turn.completed",
        usage: {
          input_tokens: 100,
          cached_input_tokens: 80,
          output_tokens: 20,
          reasoning_output_tokens: 5,
        },
      })
    }'
`,
  );
  await Deno.chmod(path, 0o755);
  await command(root, ["git", "add", "fake-adaptive-codex.sh"]);
  await command(root, ["git", "commit", "--quiet", "-m", "add adaptive fake"]);
  return path;
}

async function makeComplexWorkspaceDirty(root: string): Promise<void> {
  const files: Record<string, string> = {
    "api/openapi.json": "{}\n",
    "cmd/root.ts": "export const route = 'root';\n",
    "generated/client.ts": "export interface Client {}\n",
    "migrations/001.sql": "create table state (id integer);\n",
    "package-lock.json": "{}\n",
    "src/repository.ts": "export function save() {}\n",
    "src/service.ts": "export interface Request { state: string }\n",
    "tests/service_test.ts": "// service evidence\n",
    "docs/api.md": "# API\n",
    "policies/release.md": "# Release policy\n",
  };
  for (const [relativePath, content] of Object.entries(files)) {
    const slash = relativePath.lastIndexOf("/");
    if (slash >= 0) {
      await Deno.mkdir(`${root}/${relativePath.slice(0, slash)}`, {
        recursive: true,
      });
    }
    await Deno.writeTextFile(`${root}/${relativePath}`, content);
  }
}

function runArgs(
  root: string,
  codex: string,
  workItem: string,
  maxActorCalls: number,
) {
  return {
    runId: `run-${workItem}`,
    workItem,
    workspaceDir: root,
    intent: "Review the prepared implementation slice.",
    validationProgram: "./tools/validate.sh",
    validationArgs: [],
    codexPath: codex,
    model: "test-model",
    reasoningEffort: "high" as const,
    agentTimeoutMs: 10_000,
    maxActorCalls,
    maxReviewCalls: 16,
    maxConcurrentReviewers: 3,
  };
}

function testContext(stored: Map<string, Record<string, unknown>>) {
  return {
    signal: new AbortController().signal,
    logger: {
      info: (_message: string, _properties?: Record<string, unknown>) => {},
      warning: (_message: string, _properties?: Record<string, unknown>) => {},
      error: (_message: string, _properties?: Record<string, unknown>) => {},
    },
    readResource: (name: string) => Promise.resolve(stored.get(name) ?? null),
    writeResource: (
      _specName: string,
      name: string,
      data: Record<string, unknown>,
    ) => {
      stored.set(name, structuredClone(data));
      return Promise.resolve({ name });
    },
  };
}

async function command(cwd: string, argv: string[]): Promise<void> {
  const result = await new Deno.Command(argv[0], {
    args: argv.slice(1),
    cwd,
    stdout: "piped",
    stderr: "piped",
  }).output();
  if (!result.success) {
    throw new Error(new TextDecoder().decode(result.stderr));
  }
}
