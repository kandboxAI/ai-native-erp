import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { readDeployment } from "./deployment.mjs";
import { coreMiniappPages, pluginFrontends, repositoryRoot } from "./plugin-frontends.mjs";
import { excludedWebViewRoots, selectMiniappPages } from "./frontend-deployment.mjs";

function withRoot(check) {
  const root = mkdtempSync(join(tmpdir(), "erp-deployment-test-"));
  mkdirSync(join(root, "plugins"));
  try {
    check(root, (key, { version = "1.0.0", layer = "L2", requires = [] } = {}) => {
      const directory = join(root, "plugins", key);
      mkdirSync(directory, { recursive: true });
      writeFileSync(join(directory, "plugin.toml"), [
        `key = "${key}"`,
        `name = "${key}"`,
        `layer = "${layer}"`,
        `version = "${version}"`,
        `requires = [${requires.map(value => `"${value}"`).join(", ")}]`,
        'module_codes = ["sample"]',
        'module_names = ["sample"]',
        'table_prefixes = ["sample_"]',
        "routers = []"
      ].join("\n"));
    });
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

function withDeployment(plugins, root, check) {
  const directory = mkdtempSync(join(tmpdir(), "erp-deployment-file-"));
  const path = join(directory, "deployment.json");
  try {
    writeFileSync(path, JSON.stringify({ format_version: 1, plugins }));
    check(readDeployment(path, root));
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

test("pure core starts with an empty deployment and excludes plugin pages", () => {
  withRoot(root => {
    const path = join(root, "deployment.json");
    writeFileSync(path, JSON.stringify({ format_version: 1, plugins: [] }));
    assert.deepEqual(readDeployment(path, root), { profile: "core", plugins: [], migrationBase: "core" });
  });

  const allPages = [...coreMiniappPages, ...Object.values(pluginFrontends).flatMap(manifest => manifest.miniapp_pages)];
  const selected = selectMiniappPages({ pages: allPages.map(path => ({ path })) }, []);
  assert.equal(selected.pages.length, coreMiniappPages.length);
});

test("deployment resolves generic plugin dependencies and permits optional L1 plugins", () => {
  withRoot((root, put) => {
    put("stock", { version: "1.2.0", layer: "L2" });
    put("mes", { version: "0.1.0", layer: "L3", requires: ["stock>=1.2.0"] });
    put("knowledge", { version: "0.1.0", layer: "L1" });

    withDeployment(["stock", "mes", "knowledge"], root, result => {
      assert.deepEqual(result, { profile: "custom", plugins: ["stock", "mes", "knowledge"], migrationBase: "core" });
    });
  });
});

test("deployment rejects invalid manifests, absent dependencies, and insufficient versions", () => {
  withRoot((root, put) => {
    put("stock", { version: "1.1.0", layer: "L2" });
    put("mes", { version: "0.1.0", layer: "L3", requires: ["stock>=1.2.0"] });
    const directory = mkdtempSync(join(tmpdir(), "erp-deployment-file-"));
    const path = join(directory, "deployment.json");
    try {
      writeFileSync(path, JSON.stringify({ format_version: 1, plugins: ["mes"] }));
      assert.throws(() => readDeployment(path, root), /缺少依赖 stock/);
      writeFileSync(path, JSON.stringify({ format_version: 1, plugins: ["stock", "mes"] }));
      assert.throws(() => readDeployment(path, root), /要求 stock>=1.2.0/);
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });

});

test("unknown plugin and invalid deployment shape fail closed", () => {
  assert.throws(() => readDeployment(join(repositoryRoot, "missing-deployment.json")), /无法读取部署清单/);
  const directory = mkdtempSync(join(tmpdir(), "erp-deployment-invalid-"));
  const path = join(directory, "deployment.json");
  try {
    for (const document of [
      {},
      { format_version: 2, plugins: [] },
      { format_version: 1, plugins: ["sample", "sample"] },
      { format_version: 1, plugins: ["../escape"] },
      { format_version: 1, plugins: [], secrets: "forbidden" }
    ]) {
      writeFileSync(path, JSON.stringify(document));
      assert.throws(() => readDeployment(path, repositoryRoot));
    }
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("plugin filtering remains available for knowledge and other frontends", () => {
  assert.ok(excludedWebViewRoots(["edu", "inv"]).some(root => root === "knowledge"));
  assert.ok(!excludedWebViewRoots(["edu", "inv", "knowledge"]).includes("knowledge"));
  assert.ok(pluginFrontends.knowledge);
});
