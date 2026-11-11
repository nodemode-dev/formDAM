import { api, faceThumbUrl } from "../../engine/api.js";
import { countFmt } from "../../engine/format.js";
import { clearSelection, loadPeople, loadPeopleStatus, navigate, navigate as go, on, pollJob, state } from "../../engine/store.js";
import type { Media, Person } from "../../engine/types.js";
import { h } from "../dom.js";
import { bindTileSize } from "../zoomctl.js";
import { openContextMenu } from "../contextmenu.js";
import { setSelectbarContext } from "./selectbar.js";
import { attachMarquee } from "../marquee.js";
import { iconEl } from "../icons.js";
import { openModal, textField } from "../modal.js";
import { toast } from "../toast.js";
import { bindSelectionClasses, tileFor } from "./grid.js";

let selectMode = false;
const picked = new Set<number>();

function personCard(person: Person): HTMLElement {
  const face = h("div", { class: "person-face" });
  if (person.cover_face_id) {
    const img = h("img", { alt: "", loading: "lazy" }) as HTMLImageElement;
    img.src = faceThumbUrl(person.cover_face_id);
    img.addEventListener("load", () => img.classList.add("ready"), { once: true });
    face.append(img);
  } else {
    face.append(iconEl("person"));
  }
  const card = h(
    "div",
    { class: "person-card" },
    face,
    h("div", { class: "person-name" }, person.name ?? "Unnamed"),
    h("div", { class: "person-sub" }, `${countFmt(person.media)} items`),
  );
  card.addEventListener("click", () => {
    if (selectMode) {
      if (picked.has(person.id)) picked.delete(person.id);
      else picked.add(person.id);
      card.classList.toggle("selected", picked.has(person.id));
      document.dispatchEvent(new CustomEvent("dam-people-picked"));
      return;
    }
    navigate(`#/person/${person.id}`);
  });
  card.classList.add("selectable");
  card.dataset.pid = String(person.id);
  card.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    event.stopPropagation();
    openContextMenu(event.clientX, event.clientY, [
      { label: "Open", icon: "person", action: () => navigate(`#/person/${person.id}`) },
      { label: "Rename...", icon: "type", action: () => {
        const modal = openModal("Rename person");
        const { wrap, input } = textField("Name", "text", person.name ?? "");
        input.value = person.name ?? "";
        const go = h("button", { class: "btn primary", type: "button" }, "Save");
        go.addEventListener("click", async () => {
          await api(`/people/${person.id}`, { method: "PATCH", body: JSON.stringify({ name: input.value.trim() || null }) });
          modal.close();
          void loadPeople();
        });
        modal.body.append(wrap, h("div", { class: "modal-actions" }, go));
        input.focus();
      } },
      "sep",
      { label: "Hide from People", icon: "eyeOff", action: async () => {
        await api(`/people/${person.id}/hidden`, { method: "PATCH", body: JSON.stringify({ hidden: true }) });
        void loadPeople();
      } },
      { label: "Remove from People", icon: "trash", danger: true, action: async () => {
        await api(`/people/${person.id}`, { method: "DELETE" });
        void loadPeople();
      } },
    ]);
  });
  if (selectMode) {
    card.append(h("span", { class: "sel-dot" }, iconEl("check")));
  }
  card.classList.toggle("selected", picked.has(person.id));
  return card;
}

export function mountPeoplePage(host: HTMLElement): () => void {
  const banner = h("div", { class: "banner glass-panel hidden" });
  const grid = h("div", { class: "people-grid" });
  const scanBtn = h("button", { class: "btn primary", type: "button" }, iconEl("sparkle"), "Scan for People") as HTMLButtonElement;
  const filterInput = h("input", { type: "search", placeholder: "Search people", spellcheck: "false", autocomplete: "off", autocorrect: "off", autocapitalize: "off" }) as HTMLInputElement;
  let nameFilter = "";
  filterInput.addEventListener("input", () => {
    nameFilter = filterInput.value.trim().toLowerCase();
    picked.clear();
    allBtn.textContent = "Select All";
    renderPeople();
    refreshActionBar();
  });
  const filterWrap = h("span", { class: "search-wrap" }, iconEl("search"), filterInput);
  const selectBtn = h("button", { class: "btn", type: "button" }, "Select") as HTMLButtonElement;
  const allBtn = h("button", { class: "btn", type: "button" }, "Select All") as HTMLButtonElement;
  allBtn.style.display = "none";
  const thSlider = h("input", { type: "range", min: "0.35", max: "0.8", step: "0.01" }) as HTMLInputElement;
  const thVal = h("span", { class: "slider-val" }, "");
  void api<{ threshold: number }>("/people/threshold").then((res) => {
    thSlider.value = String(res.threshold);
    thVal.textContent = res.threshold.toFixed(2);
  });
  thSlider.addEventListener("input", () => {
    thVal.textContent = Number(thSlider.value).toFixed(2);
  });
  const rebuildBtn = h("button", { class: "btn", type: "button" }, iconEl("refresh"), "Rebuild groups") as HTMLButtonElement;
  rebuildBtn.addEventListener("click", () => {
    const modal = openModal("Rebuild people groups?");
    modal.body.append(
      h("p", { class: "settings-hint" },
        `Re-clusters every stored face at strictness ${Number(thSlider.value).toFixed(2)} (higher = stricter, fewer mixed groups). Uses saved embeddings, so it is fast & needs no re-detection. Manual names & merges reset.`),
    );
    const go = h("button", { class: "btn primary", type: "button" }, "Rebuild");
    go.addEventListener("click", async () => {
      go.setAttribute("disabled", "true");
      try {
        const res = await api<{ people: number; faces_assigned: number }>("/people/rebuild", {
          method: "POST", body: JSON.stringify({ threshold: Number(thSlider.value) }),
        });
        modal.close();
        toast(`Rebuilt: ${countFmt(res.people)} people from ${countFmt(res.faces_assigned)} faces`);
        void loadPeople();
      } catch (err) {
        toast(String((err as Error).message), "error");
      }
    });
    modal.body.append(h("div", { class: "modal-actions" }, go));
  });
  const actionCount = h("span", { class: "sel-count" }, "");
  const mergeBtn = h("button", { class: "btn", type: "button" }, iconEl("mergePeople"), "Merge") as HTMLButtonElement;
  const hidePersonBtn = h("button", { class: "btn", type: "button" }, iconEl("eyeOff"), "Hide") as HTMLButtonElement;
  const removeBtn = h("button", { class: "btn danger", type: "button" }, iconEl("trash"), "Remove") as HTMLButtonElement;
  const actionBar = h("div", { class: "sel-bar glass-panel hidden" }, actionCount, mergeBtn, hidePersonBtn, removeBtn);
  const pad = h(
    "div",
    { class: "view-pad" },
    h("div", { class: "section-head" }, h("h2", {}, "People"), filterWrap, h("span", { class: "head-spacer" }),
      h("span", { class: "zoom-wrap", title: "Match strictness" }, iconEl("sliders"), thSlider, thVal),
      rebuildBtn, allBtn, selectBtn, scanBtn),
    banner,
    grid,
    actionBar,
  );
  host.append(pad);

  function refreshActionBar(): void {
    actionBar.classList.toggle("hidden", !selectMode || picked.size === 0);
    actionCount.textContent = `${countFmt(picked.size)} selected`;
    mergeBtn.disabled = picked.size < 2;
  }
  document.addEventListener("dam-people-picked", refreshActionBar);

  function setSelectMode(next: boolean): void {
    selectMode = next;
    if (!selectMode) picked.clear();
    selectBtn.textContent = selectMode ? "Done" : "Select";
    selectBtn.classList.toggle("primary", selectMode);
    allBtn.style.display = selectMode ? "" : "none";
    renderPeople();
    refreshActionBar();
  }
  selectBtn.addEventListener("click", () => setSelectMode(!selectMode));
  allBtn.addEventListener("click", () => {
    const everyone = (nameFilter
      ? state.people.filter((p) => (p.name ?? "unnamed").toLowerCase().includes(nameFilter))
      : state.people).map((p) => p.id);
    const allPicked = everyone.every((id) => picked.has(id));
    picked.clear();
    if (!allPicked) everyone.forEach((id) => picked.add(id));
    allBtn.textContent = allPicked ? "Select All" : "Select None";
    renderPeople();
    refreshActionBar();
  });
  const onKey = (event: KeyboardEvent) => {
    if (event.key === "Escape" && selectMode) setSelectMode(false);
  };
  document.addEventListener("keydown", onKey);
  const disposeMarquee = attachMarquee(pad, {
    itemSelector: ".person-card[data-pid]",
    idOf: (el) => (el.dataset.pid ? Number(el.dataset.pid) : null),
    isSelected: (id) => picked.has(id),
    setSelected: (id, on) => {
      if (!selectMode) setSelectMode(true);
      if (on) picked.add(id);
      else picked.delete(id);
      const card = pad.querySelector(`.person-card[data-pid="${id}"]`);
      card?.classList.toggle("selected", on);
    },
    onFinish: () => refreshActionBar(),
    enabled: () => true,
  });

  mergeBtn.addEventListener("click", () => {
    const ids = [...picked];
    const modal = openModal("Merge people: keep which?");
    const list = h("div", { class: "list-rows" });
    for (const pid of ids) {
      const person = state.people.find((p) => p.id === pid);
      const row = h("button", { class: "list-row glass-panel", type: "button" },
        iconEl("person"),
        h("div", { class: "list-main" }, h("div", { class: "list-title" }, person?.name ?? "Unnamed"),
          h("div", { class: "list-sub" }, `${countFmt(person?.media ?? 0)} items`)));
      row.addEventListener("click", async () => {
        try {
          await api("/people/merge", { method: "POST", body: JSON.stringify({ into_id: pid, from_ids: ids.filter((x) => x !== pid) }) });
          modal.close();
          picked.clear();
          refreshActionBar();
          void loadPeople();
          toast("Merged");
        } catch (err) {
          toast(String((err as Error).message), "error");
        }
      });
      list.append(row);
    }
    modal.body.append(h("p", { class: "settings-hint" }, "All faces move into the person you pick; the others are removed."), list);
  });

  hidePersonBtn.addEventListener("click", async () => {
    for (const pid of picked) {
      await api(`/people/${pid}/hidden`, { method: "PATCH", body: JSON.stringify({ hidden: true }) });
    }
    picked.clear();
    refreshActionBar();
    void loadPeople();
    toast("Hidden from People");
  });

  removeBtn.addEventListener("click", async () => {
    for (const pid of picked) {
      await api(`/people/${pid}`, { method: "DELETE" });
    }
    picked.clear();
    refreshActionBar();
    void loadPeople();
    toast("Removed from People (faces stay unassigned)");
  });

  function renderStatus(): void {
    const status = state.peopleStatus;
    if (!status) return;
    if (!status.ready) {
      banner.classList.remove("hidden");
      const missing = !status.cv2
        ? "OpenCV is not installed for the backend."
        : `Missing models: ${status.missing_models.join(", ")}.`;
      banner.replaceChildren(
        iconEl("warn"),
        h("span", { class: "banner-text" }, `Face recognition is not ready. ${missing} Run ./formDAM (or setup/formDAM_oc_install) to set it up.`),
      );
      scanBtn.disabled = true;
      return;
    }
    scanBtn.disabled = Boolean(status.job);
    if (status.job) {
      const counts = status.job.counts;
      banner.classList.remove("hidden");
      banner.replaceChildren(
        h("span", { class: "spin" }, iconEl("refresh")),
        h("span", { class: "banner-text" },
          `Scanning faces: ${countFmt(counts.scanned ?? 0)} scanned, ${countFmt(counts.faces ?? 0)} faces, ${countFmt(counts.people_new ?? 0)} new people`),
      );
    } else if (status.pending_media > 0) {
      banner.classList.remove("hidden");
      banner.replaceChildren(
        iconEl("people"),
        h("span", { class: "banner-text" }, `${countFmt(status.pending_media)} items have not been scanned for faces yet. Photos & videos both count.`),
      );
    } else {
      banner.classList.add("hidden");
    }
  }

  function renderPeople(): void {
    if (state.people.length === 0) {
      grid.replaceChildren(
        h("div", { class: "empty-center" }, h("div", { class: "empty-card glass-panel" },
          iconEl("people"),
          h("span", { class: "empty-title" }, "No People Yet"),
          h("span", { class: "empty-sub" }, "Run a scan & faces found in photos & video frames are grouped by visual similarity."),
        )),
      );
      return;
    }
    const visible = nameFilter
      ? state.people.filter((p) => (p.name ?? "unnamed").toLowerCase().includes(nameFilter))
      : state.people;
    grid.replaceChildren(...visible.map(personCard));
  }

  scanBtn.addEventListener("click", async () => {
    try {
      const res = await api<{ job_id: string }>("/people/scan", { method: "POST" });
      toast("Face scan started");
      void loadPeopleStatus();
      pollJob(res.job_id, (job) => {
        if (job.phase === "error") toast(job.error, "error");
        else toast(`Scan finished: ${countFmt(job.counts.faces ?? 0)} faces across ${countFmt(job.counts.scanned ?? 0)} items`);
        void loadPeopleStatus();
        void loadPeople();
      });
      const tickStatus = () => {
        if (state.peopleStatus?.job) {
          void loadPeopleStatus();
          setTimeout(tickStatus, 900);
        }
      };
      setTimeout(tickStatus, 900);
    } catch (err) {
      toast(String((err as Error).message), "error");
    }
  });

  const offs = [on("people", renderPeople), on("peopleStatus", renderStatus)];
  renderPeople();
  renderStatus();
  void loadPeople();
  void loadPeopleStatus();
  return () => {
    disposeMarquee();
    document.removeEventListener("keydown", onKey);
    document.removeEventListener("dam-people-picked", refreshActionBar);
    offs.forEach((off) => off());
    selectMode = false;
    picked.clear();
  };
}

export function mountPersonPage(host: HTMLElement, personId: number): () => void {
  const backBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Back to People" }, iconEl("back"));
  backBtn.addEventListener("click", () => go("#/people"));
  const title = h("h2", { title: "Double-click to rename" }, "Person");
  const renameBtn = h("button", { class: "icon-btn", type: "button", "aria-label": "Rename" }, iconEl("type"));
  const facesStrip = h("div", { class: "faces-strip" });
  const clearContext = setSelectbarContext([{
    label: "Move to person...",
    icon: "mergePeople",
    handler: (mediaIds) => void openMoveFlow(mediaIds),
  }]);
  async function openMoveFlow(mediaIds: number[]): Promise<void> {
    const people = await api<{ people: Person[] }>("/people?include_hidden=true");
    const modal = openModal("Move faces in selected items to");
    const list = h("div", { class: "list-rows", style: "max-height:320px;overflow-y:auto" });
    async function moveMedia(target: number | null, newName?: string): Promise<void> {
      await api(`/people/${personId}/reassign-media`, {
        method: "POST",
        body: JSON.stringify({ media_ids: mediaIds, target_person_id: target, new_name: newName ?? null }),
      });
      modal.close();
      clearSelection();
      toast("Face crops followed the move; matching updates immediately");
      void load();
      void loadFaces();
      void loadPeople();
    }
    for (const person of people.people.filter((p) => p.id !== personId)) {
      const row = h("button", { class: "list-row glass-panel", type: "button" },
        iconEl("person"),
        h("div", { class: "list-main" }, h("div", { class: "list-title" }, person.name ?? "Unnamed"),
          h("div", { class: "list-sub" }, `${countFmt(person.faces)} faces`)));
      row.addEventListener("click", () => void moveMedia(person.id));
      list.append(row);
    }
    const { wrap, input } = textField("New person name", "text", "e.g. Ada");
    const createBtn = h("button", { class: "btn", type: "button" }, iconEl("plus"), "Create & move");
    createBtn.addEventListener("click", () => void moveMedia(null, input.value.trim() || undefined));
    modal.body.append(list, wrap, h("div", { class: "modal-actions" }, createBtn));
  }


  let reassignMode = false;
  const pickedFaces = new Set<number>();
  const reassignBtn = h("button", { class: "btn", type: "button" }, "Reassign faces") as HTMLButtonElement;
  const moveBtn = h("button", { class: "btn primary", type: "button" }, iconEl("mergePeople"), "Move to...") as HTMLButtonElement;
  moveBtn.style.display = "none";

  function refreshMove(): void {
    moveBtn.style.display = reassignMode ? "" : "none";
    moveBtn.disabled = pickedFaces.size === 0;
    moveBtn.replaceChildren(iconEl("mergePeople"), pickedFaces.size ? `Move ${pickedFaces.size} to...` : "Move to...");
  }

  reassignBtn.addEventListener("click", () => {
    reassignMode = !reassignMode;
    if (!reassignMode) pickedFaces.clear();
    reassignBtn.textContent = reassignMode ? "Done" : "Reassign faces";
    reassignBtn.classList.toggle("primary", reassignMode);
    refreshMove();
    void loadFaces();
  });

  moveBtn.addEventListener("click", async () => {
    const people = await api<{ people: Person[] }>("/people?include_hidden=true");
    const modal = openModal("Move faces to");
    const list = h("div", { class: "list-rows", style: "max-height:320px;overflow-y:auto" });
    async function moveAll(personId2: number | null, newName?: string): Promise<void> {
      let target = personId2;
      for (const fid of pickedFaces) {
        const res = await api<{ person_id: number }>(`/faces/${fid}/person`, {
          method: "PATCH",
          body: JSON.stringify(target === null ? { person_id: null, new_name: newName ?? null } : { person_id: target }),
        });
        target = res.person_id;
      }
      modal.close();
      pickedFaces.clear();
      reassignMode = false;
      reassignBtn.textContent = "Reassign faces";
      reassignBtn.classList.remove("primary");
      refreshMove();
      toast("Faces moved; matching updates on the next scan or rebuild");
      void loadFaces();
      void load();
      void loadPeople();
    }
    for (const person of people.people.filter((p) => p.id !== personId)) {
      const row = h("button", { class: "list-row glass-panel", type: "button" },
        iconEl("person"),
        h("div", { class: "list-main" }, h("div", { class: "list-title" }, person.name ?? "Unnamed"),
          h("div", { class: "list-sub" }, `${countFmt(person.faces)} faces`)));
      row.addEventListener("click", () => void moveAll(person.id));
      list.append(row);
    }
    const { wrap, input } = textField("New person name", "text", "e.g. Ada");
    const createBtn = h("button", { class: "btn", type: "button" }, iconEl("plus"), "Create & move");
    createBtn.addEventListener("click", () => void moveAll(null, input.value.trim() || undefined));
    modal.body.append(list, wrap, h("div", { class: "modal-actions" }, createBtn));
  });

  const grid = h("div", { class: "tile-grid" });
  const unbindTiles = bindTileSize(grid);
  const unbindSel = bindSelectionClasses(grid);
  const pad = h(
    "div",
    { class: "view-pad" },
    h("div", { class: "section-head" }, backBtn, title, h("span", { class: "head-spacer" }), moveBtn, reassignBtn, renameBtn),
    facesStrip,
    grid,
  );
  host.append(pad);
  let items: Media[] = [];

  function editName(): void {
    const current = title.textContent === "Unnamed" ? "" : (title.textContent ?? "");
    const input = h("input", { class: "field-input", value: current, spellcheck: "false", autocomplete: "off", autocorrect: "off", autocapitalize: "off", style: "font-size:17px;font-weight:700" }) as HTMLInputElement;
    title.replaceWith(input);
    input.focus();
    input.select();
    const finish = async (save: boolean) => {
      if (save && input.value.trim()) {
        try {
          await api(`/people/${personId}`, { method: "PATCH", body: JSON.stringify({ name: input.value.trim() }) });
          title.textContent = input.value.trim();
          void loadPeople();
        } catch (err) {
          toast(String((err as Error).message), "error");
        }
      }
      input.replaceWith(title);
    };
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") void finish(true);
      if (event.key === "Escape") void finish(false);
    });
    input.addEventListener("blur", () => void finish(true));
  }
  title.addEventListener("dblclick", editName);

  async function loadFaces(): Promise<void> {
    const data = await api<{ faces: Array<{ id: number; media_id: number }> }>(`/people/${personId}/faces?limit=24`);
    facesStrip.replaceChildren(
      ...data.faces.map((face) => {
        const img = h("img", { alt: "", loading: "lazy", src: faceThumbUrl(face.id) });
        const chip = h("div", { class: "face-chip", title: reassignMode ? "Click to pick" : "Best face crops train this person's matching" }, img);
        if (reassignMode) {
          chip.append(h("span", { class: "sel-dot", style: "top:2px;left:2px;width:18px;height:18px" }, iconEl("check")));
          chip.classList.toggle("selected", pickedFaces.has(face.id));
          chip.addEventListener("click", () => {
            if (pickedFaces.has(face.id)) pickedFaces.delete(face.id);
            else pickedFaces.add(face.id);
            chip.classList.toggle("selected", pickedFaces.has(face.id));
            refreshMove();
          });
        } else {
          const removeFace = h("button", { class: "face-x", type: "button", "aria-label": "Not this person" }, iconEl("close"));
          removeFace.addEventListener("click", async (event) => {
            event.stopPropagation();
            await api(`/faces/${face.id}/person`, { method: "DELETE" });
            toast("Face unassigned; future scans learn from the correction");
            void loadFaces();
            void load();
            void loadPeople();
          });
          chip.append(removeFace);
        }
        return chip;
      }),
    );
  }

  async function load(): Promise<void> {
    const detail = await api<{ id: number; name: string | null; items: Media[] }>(`/people/${personId}`);
    title.textContent = detail.name ?? "Unnamed";
    items = detail.items;
    for (const item of items) state.byId.set(item.id, item);
    grid.replaceChildren(...items.map((item) => tileFor(item, () => items.map((m) => m.id), true, (media) => [
      { label: "Set as Cover", icon: "person", action: async () => {
        try {
          await api(`/people/${personId}/cover`, { method: "POST", body: JSON.stringify({ media_id: media.id }) });
          toast("Cover updated");
          void loadPeople();
        } catch (err) {
          toast(String((err as Error).message), "error");
        }
      } },
    ])));
    void loadFaces();
  }

  renameBtn.addEventListener("click", () => {
    const modal = openModal("Name this person");
    const { wrap, input } = textField("Name", "text", title.textContent ?? "");
    input.value = title.textContent === "Unnamed" ? "" : (title.textContent ?? "");
    const save = h("button", { class: "btn primary", type: "button" }, "Save");
    save.addEventListener("click", async () => {
      try {
        await api(`/people/${personId}`, { method: "PATCH", body: JSON.stringify({ name: input.value }) });
        modal.close();
        void load();
        void loadPeople();
      } catch (err) {
        toast(String((err as Error).message), "error");
      }
    });
    modal.body.append(wrap, h("div", { class: "modal-actions" }, save));
    input.focus();
  });

  void load();
  return () => {
    unbindTiles();
    unbindSel();
    clearContext();
    clearSelection();
  };
}
