import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * The shape of the frontend, checked without a browser.
 *
 * There are six apps on six fixed ports, and one of them (the demo stage) frames
 * the others by address. If a port changes in one place and not another, the stage
 * shows a blank frame and nothing says why. These tests are where that is caught.
 */

const here = dirname(fileURLToPath(import.meta.url));
const read = (...parts: string[]) => readFileSync(resolve(here, ...parts), "utf8");

const apps = readdirSync(here, { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name)
  .sort();

const STAFF = ["navigator", "desk", "doctor", "admin"];

function viteConfig(app: string): { name: string; port: number } {
  const match = read(app, "vite.config.ts").match(/appConfig\("([\w-]+)",\s*(\d+)\)/);
  if (!match) throw new Error(`${app}/vite.config.ts does not call appConfig(name, port)`);
  return { name: match[1], port: Number(match[2]) };
}

const portOf = (app: string) => viteConfig(app).port;

describe("the apps", () => {
  it("are the six we expect", () => {
    expect(apps).toEqual(["admin", "demo-stage", "desk", "doctor", "family-web", "navigator"]);
  });

  it.each(apps)("%s is a complete app", (app) => {
    for (const file of ["index.html", "src/main.tsx", "src/App.tsx", "public/config.json", "tsconfig.json"]) {
      expect(existsSync(resolve(here, app, file)), `${app}/${file}`).toBe(true);
    }
    const pkg = JSON.parse(read(app, "package.json"));
    expect(pkg.name).toBe(`@saathi/${app}`);
    expect(pkg.scripts.dev).toBeDefined();
    expect(pkg.scripts.build).toBeDefined();
  });

  it.each(apps)("%s names itself consistently in its Vite config", (app) => {
    expect(viteConfig(app).name).toBe(app);
  });

  it("each have their own port", () => {
    const ports = apps.map(portOf);
    expect(new Set(ports).size).toBe(ports.length);
  });

  it.each(apps)("%s reads config.json before it renders", (app) => {
    const main = read(app, "src/main.tsx");
    expect(main).toContain("loadRuntimeConfig()");
    expect(main.indexOf("loadRuntimeConfig")).toBeLessThan(main.indexOf("render("));
  });

  it.each(apps)("%s ships a config.json that is valid JSON naming the API", (app) => {
    const config = JSON.parse(read(app, "public/config.json"));
    expect(config.apiBase).toBe("/api");
  });

  it.each(STAFF)("%s uses the shared staff stylesheet and the shell", (app) => {
    expect(read(app, "src/main.tsx")).toContain("@saathi/ui-web/styles.css");
    expect(read(app, "src/App.tsx")).toContain("AppShell");
  });

  it("keep the family app free of the staff stylesheet", () => {
    // A phone should not download the hospital's whole kit.
    expect(read("family-web", "src/main.tsx")).not.toContain("styles.css\"");
    expect(read("family-web", "src/main.tsx")).toContain("@saathi/ui-web/base.css");
  });
});

describe("the demo stage", () => {
  const stage = JSON.parse(read("demo-stage", "public/config.json"));

  it("frames each app at the port that app actually runs on", () => {
    expect(stage.apps.navigator).toBe(`http://localhost:${portOf("navigator")}`);
    expect(stage.apps.desk).toBe(`http://localhost:${portOf("desk")}`);
    expect(stage.apps.family).toBe(`http://localhost:${portOf("family-web")}`);
  });

  it("falls back to the same ports when there is no config.json", () => {
    const source = read("demo-stage", "src/App.tsx");
    expect(source).toContain(`family: "http://localhost:${portOf("family-web")}"`);
    expect(source).toContain(`desk: "http://localhost:${portOf("desk")}"`);
    expect(source).toContain(`navigator: "http://localhost:${portOf("navigator")}"`);
  });

  it("is the only place the presenter's controls live", () => {
    for (const app of apps.filter((a) => a !== "demo-stage")) {
      const source = readdirSync(resolve(here, app, "src")).map((f) => (f.endsWith(".tsx") ? read(app, "src", f) : ""));
      const text = source.join("\n");
      expect(text, `${app} has a story bar`).not.toContain("StoryBar");
      expect(text, `${app} has clock controls`).not.toContain("live.control");
    }
  });
});

describe("running them", () => {
  it("starts every app with `npm run dev`", () => {
    const dev: string = JSON.parse(readFileSync(resolve(here, "../package.json"), "utf8")).scripts.dev;
    for (const app of apps) expect(dev, app).toContain(`@saathi/${app}`);
  });

  it("keeps the launch config in step with the ports", () => {
    const launch = JSON.parse(readFileSync(resolve(here, "../../.claude/launch.json"), "utf8"));
    for (const entry of launch.configurations) {
      expect(entry.port, entry.name).toBe(portOf(entry.name));
    }
  });
});
