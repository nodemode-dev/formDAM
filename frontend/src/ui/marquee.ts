import { h } from "./dom.js";

export interface MarqueeOptions {
  itemSelector: string;
  idOf: (el: HTMLElement) => number | null;
  isSelected: (id: number) => boolean;
  setSelected: (id: number, on: boolean) => void;
  onFinish?: () => void;
  enabled?: () => boolean;
}

export function attachMarquee(container: HTMLElement, opts: MarqueeOptions): () => void {
  let rect: HTMLElement | null = null;
  let originX = 0;
  let originY = 0;
  let baseline: Set<number> | null = null;
  let dragging = false;

  function intersects(a: DOMRect, b: DOMRect): boolean {
    return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
  }

  function apply(x0: number, y0: number, x1: number, y1: number): void {
    const box = new DOMRect(Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0));
    if (rect) {
      rect.style.left = `${box.x}px`;
      rect.style.top = `${box.y}px`;
      rect.style.width = `${box.width}px`;
      rect.style.height = `${box.height}px`;
    }
    for (const el of container.querySelectorAll<HTMLElement>(opts.itemSelector)) {
      const id = opts.idOf(el);
      if (id === null) continue;
      const hit = intersects(box, el.getBoundingClientRect());
      const want = hit ? true : baseline?.has(id) ?? false;
      if (want !== opts.isSelected(id)) opts.setSelected(id, want);
    }
  }

  function onDown(event: PointerEvent): void {
    if (event.button !== 0) return;
    if (opts.enabled && !opts.enabled()) return;
    const target = event.target as HTMLElement;
    if (target.closest("button, a, input, video, .viewer, .modal-card")) return;
    if (target.closest(opts.itemSelector)) return;
    originX = event.clientX;
    originY = event.clientY;
    baseline = null;
    dragging = false;

    const onMove = (move: PointerEvent) => {
      if (!dragging) {
        if (Math.hypot(move.clientX - originX, move.clientY - originY) < 6) return;
        dragging = true;
        baseline = new Set<number>();
        for (const el of container.querySelectorAll<HTMLElement>(opts.itemSelector)) {
          const id = opts.idOf(el);
          if (id !== null && opts.isSelected(id)) baseline.add(id);
        }
        rect = h("div", { class: "marquee-rect" });
        document.body.append(rect);
      }
      move.preventDefault();
      apply(originX, originY, move.clientX, move.clientY);
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      if (dragging) {
        rect?.remove();
        rect = null;
        baseline = null;
        opts.onFinish?.();
      }
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  container.addEventListener("pointerdown", onDown);
  return () => {
    container.removeEventListener("pointerdown", onDown);
    rect?.remove();
  };
}
