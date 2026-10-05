import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { RULES, R4_SUBTYPE_ASSIGNEES, CTX_CLASSES, routeOperation, auditManifest, verifyEvidence } from "../scripts/route-policy.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function op(overrides = {}) {
  return {
    description: "op",
    producesDiff: false,
    outward: false,
    interpretationRequired: false,
    singleShot: false,
    allowlistedCommand: false,
    kind: "read",
    spec: {},
    ...overrides
  };
}

// 表形式: ルーティング代表・境界ケース (仕様書「受け入れ条件」対応表)。
const cases = [
  {
    name: "outward な操作 (git push) は P0",
    input: op({ description: "git push", outward: true, kind: "modify" }),
    expectedRule: "P0"
  },
  {
    name: "許可リスト内の単発読み取り (git status) は R0",
    input: op({ description: "git status", singleShot: true, allowlistedCommand: true, kind: "read" }),
    expectedRule: "R0"
  },
  {
    name: "同一サブタスク内の 2 手目以降 (singleShot=false) は R0 ではなく R1",
    input: op({ description: "2 手目の read", singleShot: false, allowlistedCommand: true, kind: "read" }),
    expectedRule: "R1"
  },
  {
    name: "grep 系の探索 (kind=search) は R1",
    input: op({ description: "grep for TODO", kind: "search", singleShot: true, allowlistedCommand: false }),
    expectedRule: "R1"
  },
  {
    name: "interpretationRequired=true の read (受け入れ判定用の diff 読解) は R4",
    input: op({ description: "diff を読み解いて受け入れ判定", kind: "read", interpretationRequired: true }),
    expectedRule: "R4",
    expectReasonIncludes: "interpretationRequired=true"
  },
  {
    name: "既知検証手順の実行 (npm test) は R2",
    input: op({ description: "npm test を実行", kind: "execute-verification" }),
    expectedRule: "R2"
  },
  {
    name: "失敗原因の仮説形成 (kind=judge) は分解せず R4",
    input: op({ description: "失敗原因の仮説形成", kind: "judge" }),
    expectedRule: "R4",
    expectReasonIncludes: "judge"
  },
  {
    name: "spec 4 フィールド完備の実装委譲は R3",
    input: op({
      description: "仕様確定済みの実装",
      producesDiff: true,
      kind: "modify",
      spec: { target: "t", expectedResult: "e", allowedScope: "a", verification: "v" }
    }),
    expectedRule: "R3"
  },
  {
    name: "spec の 1 フィールドが空だと R4 (reasons に欠落フィールド名)",
    input: op({
      description: "仕様が書き切れない実装",
      producesDiff: true,
      kind: "modify",
      spec: { target: "t", expectedResult: "e", allowedScope: "a", verification: "" }
    }),
    expectedRule: "R4",
    expectReasonIncludes: "verification"
  },
  {
    name: "kind=modify で spec なしは R4 (reasons に全欠落フィールド名)",
    input: op({ description: "spec 未記入の実装", producesDiff: true, kind: "modify" }),
    expectedRule: "R4",
    expectReasonIncludes: "target"
  }
];

for (const { name, input, expectedRule, expectReasonIncludes } of cases) {
  test(`routeOperation: ${name}`, () => {
    const result = routeOperation(input);
    assert.equal(result.rule, expectedRule);
    if (expectedRule === "R4") {
      assert.ok(result.reasons.length > 0, "R4 は reasons を持つ必要がある");
      if (expectReasonIncludes) {
        assert.ok(
          result.reasons.some((reason) => reason.includes(expectReasonIncludes)),
          `reasons に "${expectReasonIncludes}" を含む行が必要: ${JSON.stringify(result.reasons)}`
        );
      }
    } else {
      assert.deepEqual(result.reasons, []);
    }
  });
}

function manifest(tasks) {
  return { mode: "judge-main", modeSource: "default", sessionModel: "claude-opus-4-8", tasks };
}

function task(overrides = {}) {
  return {
    id: "t1",
    description: "task",
    rule: "R1",
    plannedAssignee: "haiku-scout",
    actualAssignee: "haiku-scout",
    status: "completed",
    ...overrides
  };
}

const auditCases = [
  {
    name: "予定どおり実効した R1 タスクは PASS",
    input: manifest([task()]),
    expectedStatus: "PASS",
    expectedCodes: []
  },
  {
    name: "未知の rule ID は UNKNOWN_RULE",
    input: manifest([task({ rule: "R9" })]),
    expectedStatus: "FINDINGS",
    expectedCodes: ["UNKNOWN_RULE"]
  },
  {
    name: "planned と actual が異なるのに deviationNote がなければ UNDOCUMENTED_DEVIATION",
    input: manifest([task({ plannedAssignee: "haiku-scout", actualAssignee: "main" })]),
    expectedStatus: "FINDINGS",
    expectedCodes: ["UNDOCUMENTED_DEVIATION"]
  },
  {
    name: "R4 行に r4Reason がなければ MISSING_R4_REASON",
    input: manifest([task({ rule: "R4", plannedAssignee: "main", actualAssignee: "main" })]),
    expectedStatus: "FINDINGS",
    expectedCodes: ["MISSING_R4_REASON"]
  },
  {
    name: "R3 行の specFields が欠落していれば INCOMPLETE_R3_SPEC",
    input: manifest([
      task({
        rule: "R3",
        plannedAssignee: "sonnet-implementer",
        actualAssignee: "sonnet-implementer",
        specFields: { target: "t", expectedResult: "e", allowedScope: "a" }
      })
    ]),
    expectedStatus: "FINDINGS",
    expectedCodes: ["INCOMPLETE_R3_SPEC"]
  },
  {
    name: "P0 行が assignee を持てば P0_HAS_ASSIGNEE",
    input: manifest([task({ rule: "P0", plannedAssignee: "main", actualAssignee: "main" })]),
    expectedStatus: "FINDINGS",
    expectedCodes: ["P0_HAS_ASSIGNEE"]
  }
];

for (const { name, input, expectedStatus, expectedCodes } of auditCases) {
  test(`auditManifest: ${name}`, () => {
    const result = auditManifest(input);
    assert.equal(result.status, expectedStatus);
    for (const code of expectedCodes) {
      assert.ok(result.findings.some((finding) => finding.code === code), `findings に ${code} が必要`);
    }
    if (expectedCodes.length === 0) {
      assert.deepEqual(result.findings, []);
    }
  });
}

// 二重正本ドリフト検知: references/02-decision-matrix.md はルール表の解説であり、
// scripts/route-policy.mjs の RULES がルーティングの正本。両者のルール ID と
// assignee 名がズレたらこのテストが落ちる。
test("references/02-decision-matrix.md は RULES の全 id と claude / codex 両側の assignee 名を含む", () => {
  const doc = fs.readFileSync(path.join(__dirname, "../references/02-decision-matrix.md"), "utf8");
  for (const rule of RULES) {
    assert.ok(doc.includes(rule.id), `02-decision-matrix.md に ${rule.id} が見つからない`);
    for (const runtime of ["claude", "codex"]) {
      assert.ok(
        doc.includes(`\`${rule.assignee[runtime]}\``),
        `02-decision-matrix.md に ${runtime} 側 assignee "${rule.assignee[runtime]}" (${rule.id}) が見つからない`
      );
    }
  }
});

// Codex 側の委譲先はモデル名ではなく 07-codex.md の agents.<name> で定義した役割名。
// モデルと effort への対応は 07 だけが持つ。
test("Codex 側の委譲先 assignee は references/07-codex.md の agents.<name> として定義されている", () => {
  const doc = fs.readFileSync(path.join(__dirname, "../references/07-codex.md"), "utf8");
  const delegated = new Set([
    ...["R1", "R2", "R3"].map((id) => RULES.find((rule) => rule.id === id).assignee.codex),
    R4_SUBTYPE_ASSIGNEES.R4a.codex
  ]);
  for (const name of delegated) {
    assert.ok(doc.includes(`agents.${name}`), `07-codex.md に agents.${name} が見つからない`);
  }
});

// 02 同期テスト (v0.3.0 追加分): R4 サブタイプ (R4-ctx/R4a/R4b) が解説文書に
// 出現するかを検査する (正本は route-policy.mjs の deriveR4Subtype)。
test("references/02-decision-matrix.md は R4 サブタイプ (R4-ctx/R4a/R4b) を含む", () => {
  const doc = fs.readFileSync(path.join(__dirname, "../references/02-decision-matrix.md"), "utf8");
  for (const subtype of ["R4-ctx", "R4a", "R4b"]) {
    assert.ok(doc.includes(subtype), `02-decision-matrix.md に ${subtype} が見つからない`);
  }
});

// --- v0.3.0: conductor mode (mode パラメータ・R4 サブタイプ機械導出) ---

function conductorOp(overrides = {}) {
  return op({ producesDiff: true, interpretationRequired: true, kind: "judge", ...overrides });
}

test("routeOperation: mode 省略は judge-main と同一の出力で、R4 は subtype を持たずメインが担う", () => {
  const withoutMode = routeOperation(conductorOp());
  const withJudgeMain = routeOperation(conductorOp(), { mode: "judge-main" });
  assert.equal(withoutMode.rule, "R4");
  assert.equal(withoutMode.subtype, null);
  assert.deepEqual(withoutMode.assignee, { claude: "main", codex: "main" });
  assert.deepEqual(withoutMode, withJudgeMain, "mode 省略と mode:'judge-main' 明示は同一の出力");
});

test("routeOperation: 戻り値は mode とルールに関係なく { rule, subtype, assignee: { claude, codex }, reasons } の形", () => {
  const ops = [
    op({ outward: true }),
    op({ singleShot: true, allowlistedCommand: true }),
    op({ kind: "execute-verification" }),
    conductorOp(),
    conductorOp({ ctxClass: CTX_CLASSES[0] })
  ];
  for (const mode of ["judge-main", "conductor"]) {
    for (const input of ops) {
      const result = routeOperation(input, { mode });
      assert.deepEqual(Object.keys(result).sort(), ["assignee", "reasons", "rule", "subtype"]);
      assert.deepEqual(Object.keys(result.assignee).sort(), ["claude", "codex"]);
      if (mode !== "conductor" || result.rule !== "R4") {
        assert.equal(result.subtype, null, `${mode} の ${result.rule} は subtype を持たない`);
      }
    }
  }
});

test("routeOperation: conductor mode の R4-ctx — ctxClass が CTX_CLASSES に所属すれば ctx 扱い", () => {
  for (const ctxClass of CTX_CLASSES) {
    const result = routeOperation(conductorOp({ ctxClass }), { mode: "conductor" });
    assert.equal(result.rule, "R4");
    assert.equal(result.subtype, "R4-ctx");
    assert.deepEqual(result.assignee, { claude: "main", codex: "main" });
  }
});

test("routeOperation: conductor mode の R4a (closed) — packet 6 フィールド完備・dependsOn 空", () => {
  const packet = {
    question: "q",
    options: "a/b",
    evidencePointers: "file.md:12",
    constraints: "c",
    acceptanceCriteria: "ac",
    impactScope: "scope"
  };
  const result = routeOperation(conductorOp({ packet, dependsOn: [] }), { mode: "conductor" });
  assert.equal(result.rule, "R4");
  assert.equal(result.subtype, "R4a");
  assert.deepEqual(result.assignee, { claude: "judge", codex: "judge" });
});

test("routeOperation: conductor mode の R4b (adaptive) — packet 未完結", () => {
  const packet = { question: "q", options: "a/b", evidencePointers: "", constraints: "c", acceptanceCriteria: "ac", impactScope: "scope" };
  const result = routeOperation(conductorOp({ packet, dependsOn: [] }), { mode: "conductor" });
  assert.equal(result.rule, "R4");
  assert.equal(result.subtype, "R4b");
  assert.deepEqual(result.assignee, { claude: "session-escalation", codex: "session-escalation" });
});

test("routeOperation: conductor mode の R4b (adaptive) — packet 完備でも dependsOn 非空なら R4b", () => {
  const packet = {
    question: "q",
    options: "a/b",
    evidencePointers: "file.md:12",
    constraints: "c",
    acceptanceCriteria: "ac",
    impactScope: "scope"
  };
  const result = routeOperation(conductorOp({ packet, dependsOn: ["row-1"] }), { mode: "conductor" });
  assert.equal(result.subtype, "R4b");
  assert.deepEqual(result.assignee, { claude: "session-escalation", codex: "session-escalation" });
});

test("routeOperation: conductor mode で CTX_CLASSES 外の ctxClass 主張は判断型 (R4a/R4b) として評価される", () => {
  const packet = {
    question: "q",
    options: "a/b",
    evidencePointers: "file.md:12",
    constraints: "c",
    acceptanceCriteria: "ac",
    impactScope: "scope"
  };
  const result = routeOperation(conductorOp({ ctxClass: "not-a-real-class", packet, dependsOn: [] }), { mode: "conductor" });
  assert.notEqual(result.subtype, "R4-ctx", "enum 外の ctxClass は ctx として扱われない");
  assert.equal(result.subtype, "R4a");
});

// --- v0.3.0: auditManifest の新 findings (各 1) ---

function conductorManifest(tasks, overrides = {}) {
  return { mode: "conductor", modeSource: "env", sessionModel: "claude-sonnet-4-5", tasks, ...overrides };
}

test("auditManifest: mode=conductor かつ sessionModel が opus/fable を含むと MODE_MODEL_MISMATCH", () => {
  const result = auditManifest(conductorManifest([], { sessionModel: "claude-opus-4-8" }));
  assert.equal(result.status, "FINDINGS");
  assert.ok(result.findings.some((f) => f.code === "MODE_MODEL_MISMATCH"));
});

test("auditManifest: mode=judge-main かつ sessionModel が sonnet を含むと MODE_MODEL_MISMATCH", () => {
  const result = auditManifest({ mode: "judge-main", modeSource: "default", sessionModel: "claude-sonnet-4-5", tasks: [] });
  assert.equal(result.status, "FINDINGS");
  assert.ok(result.findings.some((f) => f.code === "MODE_MODEL_MISMATCH"));
});

test("auditManifest: conductor mode で判断型 R4 行の actualAssignee が main だと CONDUCTOR_EXECUTED_R4 (deviationNote があっても抑制されない)", () => {
  const t = task({
    id: "r4-1",
    rule: "R4",
    plannedAssignee: "judge",
    actualAssignee: "main",
    r4Reason: "reason",
    deviationNote: "conductor が判断した",
    packet: {
      question: "q",
      options: "a/b",
      evidencePointers: "file.md:12",
      constraints: "c",
      acceptanceCriteria: "ac",
      impactScope: "scope"
    },
    dependsOn: []
  });
  const result = auditManifest(conductorManifest([t]));
  assert.equal(result.status, "FINDINGS");
  assert.ok(result.findings.some((f) => f.code === "CONDUCTOR_EXECUTED_R4" && f.ref === "r4-1"));
  assert.ok(
    !result.findings.some((f) => f.code === "UNDOCUMENTED_DEVIATION" && f.ref === "r4-1"),
    "CONDUCTOR_EXECUTED_R4 と同一行の UNDOCUMENTED_DEVIATION は抑制される"
  );
});

test("auditManifest: CTX_CLASSES 外の ctxClass 主張は INVALID_CTX_CLASS を発火し、CONDUCTOR_EXECUTED_R4 の判定対象に含まれる (自己分類による回避を許さない)", () => {
  const t = task({
    id: "r4-2",
    rule: "R4",
    plannedAssignee: "judge",
    actualAssignee: "main",
    r4Reason: "reason",
    ctxClass: "not-a-real-class",
    packet: {
      question: "q",
      options: "a/b",
      evidencePointers: "file.md:12",
      constraints: "c",
      acceptanceCriteria: "ac",
      impactScope: "scope"
    },
    dependsOn: []
  });
  const result = auditManifest(conductorManifest([t]));
  assert.ok(result.findings.some((f) => f.code === "INVALID_CTX_CLASS" && f.ref === "r4-2"));
  assert.ok(result.findings.some((f) => f.code === "CONDUCTOR_EXECUTED_R4" && f.ref === "r4-2"));
});

test("auditManifest: R4a 行に judgeRef が欠落していれば MISSING_JUDGE_REF", () => {
  const t = task({
    id: "r4a-1",
    rule: "R4",
    plannedAssignee: "judge",
    actualAssignee: "judge",
    r4Reason: "reason",
    packet: {
      question: "q",
      options: "a/b",
      evidencePointers: "file.md:12",
      constraints: "c",
      acceptanceCriteria: "ac",
      impactScope: "scope"
    },
    dependsOn: []
  });
  const result = auditManifest(conductorManifest([t]));
  assert.equal(result.status, "FINDINGS");
  assert.ok(result.findings.some((f) => f.code === "MISSING_JUDGE_REF" && f.ref === "r4a-1"));
});

test("auditManifest: R4a 行に judgeRef が完備していれば MISSING_JUDGE_REF は発火しない", () => {
  const t = task({
    id: "r4a-2",
    rule: "R4",
    plannedAssignee: "judge",
    actualAssignee: "judge",
    r4Reason: "reason",
    packet: {
      question: "q",
      options: "a/b",
      evidencePointers: "file.md:12",
      constraints: "c",
      acceptanceCriteria: "ac",
      impactScope: "scope"
    },
    dependsOn: [],
    judgeRef: { agent: "judge", requestedModel: "opus", resultSummary: "決定: X" }
  });
  const result = auditManifest(conductorManifest([t]));
  assert.ok(!result.findings.some((f) => f.code === "MISSING_JUDGE_REF"));
});

test("auditManifest: R3 行に contractRef が欠落していれば DANGLING_SPEC", () => {
  const t = task({
    rule: "R3",
    plannedAssignee: "sonnet-implementer",
    actualAssignee: "sonnet-implementer",
    specFields: { target: "t", expectedResult: "e", allowedScope: "a", verification: "v" }
  });
  const result = auditManifest(manifest([t]));
  assert.equal(result.status, "FINDINGS");
  assert.ok(result.findings.some((f) => f.code === "DANGLING_SPEC"));
});

test("auditManifest: 完了した R3 行の verificationRef が R2 行を指していなければ UNFALSIFIABLE_VERIFICATION", () => {
  const t = task({
    rule: "R3",
    status: "completed",
    plannedAssignee: "sonnet-implementer",
    actualAssignee: "sonnet-implementer",
    specFields: { target: "t", expectedResult: "e", allowedScope: "a", verification: "v" },
    contractRef: "accept-criteria-1",
    verificationRef: "does-not-exist"
  });
  const result = auditManifest(manifest([t]));
  assert.equal(result.status, "FINDINGS");
  assert.ok(result.findings.some((f) => f.code === "UNFALSIFIABLE_VERIFICATION"));
});

test("auditManifest: 完了した R3 行の verificationRef が実在する R2 行を指していれば UNFALSIFIABLE_VERIFICATION は発火しない", () => {
  const r2 = task({ id: "verify-1", rule: "R2", plannedAssignee: "haiku-scout", actualAssignee: "haiku-scout" });
  const r3 = task({
    id: "impl-1",
    rule: "R3",
    status: "completed",
    plannedAssignee: "sonnet-implementer",
    actualAssignee: "sonnet-implementer",
    specFields: { target: "t", expectedResult: "e", allowedScope: "a", verification: "v" },
    contractRef: "accept-criteria-1",
    verificationRef: "verify-1"
  });
  const result = auditManifest(manifest([r2, r3]));
  assert.ok(!result.findings.some((f) => f.code === "UNFALSIFIABLE_VERIFICATION"));
});

test("auditManifest: 凍結後に追加された R3 行 (addedAfterFreeze) に deviationNote がなければ SCOPE_EXPANSION", () => {
  const t = task({
    rule: "R3",
    plannedAssignee: "sonnet-implementer",
    actualAssignee: "sonnet-implementer",
    specFields: { target: "t", expectedResult: "e", allowedScope: "a", verification: "v" },
    contractRef: "accept-criteria-1",
    addedAfterFreeze: true
  });
  const result = auditManifest(manifest([t]));
  assert.ok(result.findings.some((f) => f.code === "SCOPE_EXPANSION"));
});

test("auditManifest: baseline.contractHash と currentContractHash が食い違えば SCOPE_EXPANSION", () => {
  const result = auditManifest(
    conductorManifest([], {
      baseline: { manifestId: "m1", globs: ["plugins/model-strategy/**"], contractHash: "hash-a" },
      currentContractHash: "hash-b"
    })
  );
  assert.ok(result.findings.some((f) => f.code === "SCOPE_EXPANSION"));
});

test("auditManifest: mode を省略したマニフェストは、判断型 R4 を main が実行していても PASS せず MISSING_MODE_FIELDS", () => {
  const t = task({ id: "r4-3", rule: "R4", plannedAssignee: "judge", actualAssignee: "main", r4Reason: "reason", deviationNote: "note" });
  const result = auditManifest({ tasks: [t] });
  assert.equal(result.status, "FINDINGS");
  assert.ok(result.findings.some((f) => f.code === "MISSING_MODE_FIELDS"));
});

test("auditManifest: mode が enum 外の値だと MISSING_MODE_FIELDS", () => {
  const result = auditManifest({ mode: "not-a-mode", modeSource: "env", sessionModel: "claude-sonnet-4-5", tasks: [] });
  assert.ok(result.findings.some((f) => f.code === "MISSING_MODE_FIELDS"));
});

test("auditManifest: modeSource/sessionModel が欠落していると MISSING_MODE_FIELDS", () => {
  const result = auditManifest({ mode: "judge-main", tasks: [] });
  assert.ok(result.findings.some((f) => f.code === "MISSING_MODE_FIELDS"));
});

test("auditManifest: mode=conductor かつ R3 行が存在するが baseline がなければ MISSING_BASELINE", () => {
  const t = task({
    rule: "R3",
    plannedAssignee: "sonnet-implementer",
    actualAssignee: "sonnet-implementer",
    specFields: { target: "t", expectedResult: "e", allowedScope: "a", verification: "v" },
    contractRef: "accept-criteria-1"
  });
  const result = auditManifest(conductorManifest([t]));
  assert.ok(result.findings.some((f) => f.code === "MISSING_BASELINE"));
});

test("auditManifest: mode=conductor かつ baseline が記録されていれば MISSING_BASELINE は発火しない", () => {
  const t = task({
    rule: "R3",
    plannedAssignee: "sonnet-implementer",
    actualAssignee: "sonnet-implementer",
    specFields: { target: "t", expectedResult: "e", allowedScope: "a", verification: "v" },
    contractRef: "accept-criteria-1"
  });
  const result = auditManifest(
    conductorManifest([t], { baseline: { manifestId: "m1", globs: ["plugins/model-strategy/**"], contractHash: "h1" } })
  );
  assert.ok(!result.findings.some((f) => f.code === "MISSING_BASELINE"));
});

// --- v0.3.0: verify-evidence サブコマンド (引用実在検査) ---

test("verifyEvidence: 実在する quote は found=true・実際の行番号・行ズレを返す", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "model-strategy-verify-evidence-"));
  const file = path.join(dir, "sample.md");
  fs.writeFileSync(file, "line one\nline two\ntarget quote here\nline four\n", "utf8");

  const result = verifyEvidence({ items: [{ file, line: 1, quote: "target quote here" }] });
  assert.equal(result.status, "PASS");
  assert.equal(result.items[0].found, true);
  assert.equal(result.items[0].actualLine, 3);
  assert.equal(result.items[0].lineDrift, 2, "申告 line=1 と実際の行 3 のズレ");
});

test("verifyEvidence: 存在しない quote (幻覚引用) は found=false で FAIL", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "model-strategy-verify-evidence-"));
  const file = path.join(dir, "sample.md");
  fs.writeFileSync(file, "line one\nline two\n", "utf8");

  const result = verifyEvidence({ items: [{ file, line: 1, quote: "this text does not exist in the file" }] });
  assert.equal(result.status, "FAIL");
  assert.equal(result.items[0].found, false);
  assert.equal(result.items[0].actualLine, null);
});

test("verifyEvidence: 行ズレなしで一致すれば lineDrift=0", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "model-strategy-verify-evidence-"));
  const file = path.join(dir, "sample.md");
  fs.writeFileSync(file, "alpha\nbeta gamma\ndelta\n", "utf8");

  const result = verifyEvidence({ items: [{ file, line: 2, quote: "beta gamma" }] });
  assert.equal(result.status, "PASS");
  assert.equal(result.items[0].lineDrift, 0);
});
