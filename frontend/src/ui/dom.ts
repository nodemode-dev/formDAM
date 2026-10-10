type Attrs = Record<string, string | number | boolean | ((event: Event) => void)>;

export function h(tag: string, attrs?: Attrs, ...children: Array<Node | string>): HTMLElement {
  const node = document.createElement(tag);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (key.startsWith("on") && typeof value === "function") {
        node.addEventListener(key.slice(2), value as EventListener);
      } else if (key === "class") {
        node.className = String(value);
      } else if (typeof value === "boolean") {
        if (value) node.setAttribute(key, "");
      } else {
        node.setAttribute(key, String(value));
      }
    }
  }
  node.append(...children);
  return node;
}

export function delayedIndicator(
  show: () => void,
  hide: () => void,
  delay = 300,
  minVisible = 250,
): () => void {
  let timer: number | undefined;
  let shownAt = 0;
  timer = window.setTimeout(() => {
    shownAt = performance.now();
    show();
  }, delay);
  return () => {
    if (timer !== undefined && shownAt === 0) {
      window.clearTimeout(timer);
      return;
    }
    const remaining = Math.max(0, minVisible - (performance.now() - shownAt));
    window.setTimeout(hide, remaining);
  };
}
