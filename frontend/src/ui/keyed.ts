export function patchList<T>(
  container: HTMLElement,
  items: T[],
  keyOf: (item: T) => string,
  create: (item: T) => HTMLElement,
  update?: (node: HTMLElement, item: T) => void,
): void {
  const existing = new Map<string, HTMLElement>();
  for (const child of Array.from(container.children) as HTMLElement[]) {
    const key = child.dataset.key;
    if (key !== undefined) existing.set(key, child);
  }
  const wanted = new Set<string>();
  let cursor: Element | null = container.firstElementChild;
  for (const item of items) {
    const key = keyOf(item);
    wanted.add(key);
    let node = existing.get(key);
    if (!node) {
      node = create(item);
      node.dataset.key = key;
    } else if (update) {
      update(node, item);
    }
    if (node !== cursor) container.insertBefore(node, cursor);
    else cursor = cursor.nextElementSibling;
  }
  for (const [key, node] of existing) {
    if (!wanted.has(key)) node.remove();
  }
}

export function setText(node: HTMLElement, text: string): void {
  if (node.textContent !== text) node.textContent = text;
}
