import { resolve } from "node:path";

/**
 * The camera layer, shared by everything that records a run.
 *
 * Two things are drawn on top of the app and neither touches it: a cursor,
 * because an OS pointer does not appear in a screen recording, and a caption
 * band, because an audience watching silent automation cannot tell which part
 * was the clever bit.
 *
 * Extracted from `autodemo.mjs` so that a second recorder does not grow a
 * second copy that drifts. `autodemo.mjs` drives the local demo stage; the
 * clip recorders drive the deployed apps. They should look identical on
 * screen, and the only way to be sure of that is for them to be the same code.
 */

const OVERLAY = `
  (() => {
    // The stage is three documents. Only the outer one gets a cursor, or each
    // iframe draws its own and the recording shows three pointers.
    if (window.top !== window) return;
    const cursor = document.createElement('div');
    cursor.id = '__demo_cursor';
    Object.assign(cursor.style, {
      position: 'fixed', zIndex: 2147483647, width: '22px', height: '22px',
      marginLeft: '-5px', marginTop: '-3px', pointerEvents: 'none',
      transition: 'transform 60ms linear', left: '0', top: '0',
    });
    cursor.innerHTML =
      '<svg viewBox="0 0 22 22" width="22" height="22">' +
      '<path d="M4 2 L4 17 L8.2 13.2 L11 19.4 L13.6 18.2 L10.9 12.2 L16.4 12.1 Z"' +
      ' fill="#1d1d1f" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/></svg>';

    const title = document.createElement('div');
    title.id = '__demo_title';
    Object.assign(title.style, {
      position: 'fixed', zIndex: 2147483646, left: '0', right: '0', top: '0',
      bottom: '0', display: 'flex', flexDirection: 'column', gap: '10px',
      alignItems: 'center', justifyContent: 'center', textAlign: 'center',
      background: 'rgba(16,16,18,0.9)', color: '#fff', opacity: '0',
      transition: 'opacity 320ms ease', pointerEvents: 'none',
      backdropFilter: 'saturate(140%) blur(6px)',
      font: '600 44px/1.15 -apple-system, BlinkMacSystemFont, "SF Pro Display", system-ui, sans-serif',
      letterSpacing: '-0.03em',
    });

    const caption = document.createElement('div');
    caption.id = '__demo_caption';
    Object.assign(caption.style, {
      position: 'fixed', zIndex: 2147483646, left: '50%', bottom: '28px',
      transform: 'translateX(-50%)', maxWidth: 'min(900px, 86vw)',
      padding: '12px 20px', borderRadius: '14px',
      background: 'rgba(29,29,31,0.92)', color: '#fff',
      font: '500 16px/1.45 -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif',
      letterSpacing: '-0.01em', textAlign: 'center', opacity: '0',
      transition: 'opacity 220ms ease', boxShadow: '0 10px 40px rgba(0,0,0,0.3)',
      pointerEvents: 'none', backdropFilter: 'saturate(180%) blur(12px)',
    });

    const attach = () => {
      if (!document.body) return;
      if (!document.getElementById('__demo_cursor')) document.body.appendChild(cursor);
      if (!document.getElementById('__demo_caption')) document.body.appendChild(caption);
      if (!document.getElementById('__demo_title')) document.body.appendChild(title);
    };
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', attach);
    } else {
      attach();
    }

    window.__demoMove = (x, y) => {
      attach();
      cursor.style.transform = 'translate(' + x + 'px,' + y + 'px)';
    };
    window.__demoTitle = (heading, sub) => {
      attach();
      title.innerHTML = '';
      if (!heading) { title.style.opacity = '0'; return; }
      const h = document.createElement('div');
      h.textContent = heading;
      title.appendChild(h);
      if (sub) {
        const s2 = document.createElement('div');
        s2.textContent = sub;
        Object.assign(s2.style, {
          font: '400 19px/1.4 -apple-system, BlinkMacSystemFont, system-ui, sans-serif',
          letterSpacing: '-0.01em', color: '#a1a1a6',
        });
        title.appendChild(s2);
      }
      title.style.opacity = '1';
    };
    window.__demoSay = (text) => {
      attach();
      caption.textContent = text || '';
      caption.style.opacity = text ? '1' : '0';
    };
    // Mirror real mouse movement too, so a human can take over mid-recording.
    window.addEventListener('mousemove', (e) => window.__demoMove(e.clientX, e.clientY));
  })();
`;

class Demo {
  /**
   * @param page       the Playwright page being recorded
   * @param viewport   so the cursor starts somewhere sensible
   * @param beat       default caption hold, ms
   * @param stills     where `shot()` writes frames; omit to skip stills
   */
  constructor(page, { viewport = { width: 1920, height: 1080 }, beat = 900, stills = null } = {}) {
    this.page = page;
    this.viewport = viewport;
    this.beat = beat;
    this.stills = stills;
    this.at = { x: viewport.width / 2, y: 140 };
  }

  /** Press Advance until the story says it is finished.
   *
   *  Never a counted number of presses: a story that gains a beat silently
   *  ends one short, and a disabled button cannot tell "busy" from "done".
   *  The progress counter is the only unambiguous signal, and it is the one a
   *  presenter is reading anyway. */
  async runOut(frame, advance, lines = []) {
    for (let i = 0; i < 12; i += 1) {
      const progress = await frame.locator(".story-progress").first().textContent();
      const [done, total] = (progress ?? "0/0").split("/").map(Number);
      if (!Number.isFinite(total) || done >= total) return;
      if (lines[i]) await this.say(lines[i], 2300);
      await this.click(advance);
      await this.page.waitForTimeout(2900);
    }
  }

  /** Scroll something, visibly. A screen that never moves reads as a mockup,
   *  and the content below the fold is half of what each app has to show. */
  async scroll(locator, by) {
    const box = await locator.boundingBox().catch(() => null);
    if (!box) return;
    await this.moveTo(box.x + box.width / 2, box.y + box.height / 2);
    // In steps, so the motion is visible rather than a jump cut.
    for (let i = 0; i < 6; i += 1) {
      await this.page.mouse.wheel(0, by / 6);
      await this.page.waitForTimeout(90);
    }
    await this.page.waitForTimeout(500);
  }

  /** Give one screen the whole stage, or put them all back.
   *
   *  Side by side is right for the moment an event crosses between them, and
   *  wrong for reading a thread or a worklist — at a third of the width each
   *  screen is legible on a monitor and not on a projector. Modes: All, Phone,
   *  Desk, Navigator. */
  async focus(mode) {
    await this.click(this.page.locator(".st-focus button", { hasText: mode }), {
      label: `focus ${mode}`,
    });
    await this.page.waitForTimeout(700);
  }

  /** A full-screen act card. Structure the audience can hold on to — without
   *  it, four minutes of two screens reacting reads as one undifferentiated
   *  thing and nobody can tell which part was the point. */
  async title(heading, sub = "", hold = 2600) {
    await this.raiseTitle(heading, sub);
    await this.page.waitForTimeout(hold);
    await this.dropTitle();
  }

  async raiseTitle(heading, sub = "") {
    await this.page.evaluate(([h, s2]) => window.__demoTitle?.(h, s2), [heading, sub]);
    await this.page.evaluate(() => window.__demoSay?.(""));
  }

  async dropTitle() {
    await this.page.evaluate(() => window.__demoTitle?.(""));
    await this.page.waitForTimeout(420);
  }

  async say(text, hold = this.beat) {
    await this.page.evaluate((t) => window.__demoSay?.(t), text);
    await this.page.waitForTimeout(hold);
  }

  async clear() {
    await this.page.evaluate(() => window.__demoSay?.(""));
  }

  /** Move in a slight arc, the way a hand does, rather than a straight jump. */
  async moveTo(x, y) {
    const steps = 22;
    const { x: fromX, y: fromY } = this.at;
    for (let i = 1; i <= steps; i += 1) {
      const t = i / steps;
      const ease = t < 0.5 ? 2 * t * t : 1 - (2 - 2 * t) ** 2 / 2;
      const cx = fromX + (x - fromX) * ease;
      const cy = fromY + (y - fromY) * ease - Math.sin(ease * Math.PI) * 18;
      await this.page.mouse.move(cx, cy);
      await this.page.evaluate(([px, py]) => window.__demoMove?.(px, py), [cx, cy]);
      await this.page.waitForTimeout(9);
    }
    this.at = { x, y };
  }

  /** Point at something without clicking it. The caption says "watch the
   *  phone"; without this the cursor stays wherever it last clicked and the
   *  audience is looking at the wrong half of the screen. */
  async lookAt(locator) {
    const box = await locator.boundingBox().catch(() => null);
    if (!box) return;
    await this.moveTo(box.x + box.width / 2, box.y + Math.min(box.height / 2, 90));
  }

  /** Keep a frame. Named, numbered, and written beside the recording. */
  async shot(name) {
    if (!this.stills) return;
    this.frame = (this.frame ?? 0) + 1;
    const file = resolve(this.stills, `${String(this.frame).padStart(2, "0")}-${name}.png`);
    await this.page.screenshot({ path: file }).catch(() => {});
  }

  async click(locator, { label } = {}) {
    // Wait for the control to be ready. The Advance button disables itself
    // while a beat is running, and a click landing in that window is silently
    // swallowed — which is exactly how the first recording stopped at beat 3
    // of 4 while appearing to have pressed it four times.
    await locator.waitFor({ state: "visible", timeout: 15000 });
    for (let i = 0; i < 60 && !(await locator.isEnabled().catch(() => true)); i += 1) {
      await this.page.waitForTimeout(250);
    }
    await locator.scrollIntoViewIfNeeded().catch(() => {});
    const box = await locator.boundingBox();
    if (!box) throw new Error(`nothing to click${label ? ` for ${label}` : ""}`);
    await this.moveTo(box.x + box.width / 2, box.y + box.height / 2);
    await this.page.waitForTimeout(140);
    await locator.click();
    await this.page.waitForTimeout(260);
  }

  async type(locator, text) {
    await this.click(locator);
    await locator.fill("");
    await this.page.keyboard.type(text, { delay: 55 });
    await this.page.waitForTimeout(300);
  }
}

export { OVERLAY, Demo };
