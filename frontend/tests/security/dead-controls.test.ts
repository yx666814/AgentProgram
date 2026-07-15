// @vitest-environment node

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import ts from "typescript";
import { expect, it } from "vitest";

import contractSnapshot from "../../contracts/capabilities.json";
import { controlContracts, dynamicControlLabels } from "./control-contract-map";

function expressionLabels(expression: ts.Expression | undefined): string[] {
  if (expression === undefined) return [];
  if (ts.isStringLiteral(expression) || ts.isNoSubstitutionTemplateLiteral(expression)) return [expression.text];
  if (ts.isConditionalExpression(expression)) return [...expressionLabels(expression.whenTrue), ...expressionLabels(expression.whenFalse)];
  return [];
}

function childLabels(children: ts.NodeArray<ts.JsxChild>): string[] {
  return children.flatMap((child) => {
    if (ts.isJsxText(child)) {
      const text = child.text.replace(/\s+/g, " ").trim();
      return text.length === 0 ? [] : [text];
    }
    if (ts.isJsxExpression(child)) return expressionLabels(child.expression);
    if (ts.isJsxElement(child)) return childLabels(child.children);
    return [];
  });
}

function hasUnknownLabelExpression(children: ts.NodeArray<ts.JsxChild>): boolean {
  return children.some((child) => {
    if (ts.isJsxExpression(child)) {
      return child.expression !== undefined && expressionLabels(child.expression).length === 0;
    }
    if (ts.isJsxElement(child)) return hasUnknownLabelExpression(child.children);
    return false;
  });
}

function controlsFromFile(path: string): string[] {
  const source = ts.createSourceFile(path, readFileSync(path, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const labels: string[] = [];
  function visit(node: ts.Node): void {
    if (ts.isJsxElement(node)) {
      const tag = node.openingElement.tagName.getText(source);
      if (tag === "Button" || tag === "NavLink") {
        const ariaLabel = node.openingElement.attributes.properties.find((property) => ts.isJsxAttribute(property) && property.name.getText(source) === "aria-label");
        const ariaLabels: string[] = [];
        if (ariaLabel !== undefined && ts.isJsxAttribute(ariaLabel)) {
          if (ariaLabel.initializer !== undefined && ts.isStringLiteral(ariaLabel.initializer)) ariaLabels.push(ariaLabel.initializer.text);
          if (ariaLabel.initializer !== undefined && ts.isJsxExpression(ariaLabel.initializer)) ariaLabels.push(...expressionLabels(ariaLabel.initializer.expression));
        }
        if (ariaLabels.length > 0) labels.push(...ariaLabels);
        else if (!hasUnknownLabelExpression(node.children)) labels.push(...childLabels(node.children));
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(source);
  return labels;
}

it("maps every static and dynamic renderer control to an operation, desktop bridge, view action or explicit unavailable state", () => {
  const root = resolve(process.cwd(), "src");
  const files = [
    "app/app-shell.tsx",
    "components/api-error-state.tsx",
    "features/approvals/approvals-page.tsx",
    "features/artifacts/artifacts-page.tsx",
    "features/diagnostics/diagnostics-page.tsx",
    "features/overview/project-overview-page.tsx",
    "features/preflight/preflight-page.tsx",
    "features/projects/projects-page.tsx",
    "features/recovery/recovery-page.tsx",
    "features/settings/settings-page.tsx",
    "features/stages/message-stream.tsx",
    "features/stages/stage-workspace-page.tsx",
    "features/stages/task-queue.tsx",
    "features/startup/startup-page.tsx",
  ].map((path) => resolve(root, path));
  const labels = new Set([...files.flatMap(controlsFromFile), ...dynamicControlLabels]);
  const missing = [...labels].filter((label) => controlContracts[label] === undefined).sort();
  expect(missing).toEqual([]);
});

it("uses only frozen backend operation ids and records reasons for unavailable controls", () => {
  const operations = new Set(Object.keys(contractSnapshot.capabilities));
  for (const contracts of Object.values(controlContracts)) {
    for (const contract of contracts) {
      if (contract.kind === "operation") {
        for (const operationId of contract.operations) expect(operations.has(operationId)).toBe(true);
      }
      if (contract.kind === "unavailable") expect(contract.reason.trim().length).toBeGreaterThan(10);
    }
  }
});
