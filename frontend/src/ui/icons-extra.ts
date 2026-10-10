export const EXTRA_GLYPHS = {
  tag: '<path d="M3.5 12.2V4.5a1 1 0 0 1 1-1h7.7l8.3 8.3a1.4 1.4 0 0 1 0 2l-6.2 6.2a1.4 1.4 0 0 1-2 0z"/><circle cx="8" cy="8" r="1.4"/>',
  flag: '<path d="M5.5 21V4"/><path d="M5.5 4.5h11l-2.5 4 2.5 4h-11"/>',
  stack: '<rect x="6.5" y="9" width="12" height="11" rx="1.6"/><path d="M4.5 16V7.5a1.5 1.5 0 0 1 1.5-1.5h9"/><path d="M2.5 12.5V5a1.5 1.5 0 0 1 1.5-1.5h7"/>',
  crop: '<path d="M6.5 2.5v14a1 1 0 0 0 1 1h14"/><path d="M2.5 6.5h14a1 1 0 0 1 1 1v14"/>',
  rotate: '<path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3"/><path d="M4.2 3.6v3.6h3.6"/>',
  flipH: '<path d="M12 3v18"/><path d="M8.5 6.5L3.5 17.5h5z"/><path d="M15.5 6.5l5 11h-5z"/>',
  flipV: '<path d="M3 12h18"/><path d="M6.5 8.5l11-5v5z"/><path d="M6.5 15.5l11 5v-5z"/>',
  wand: '<path d="M4 20l11-11"/><path d="M13.5 7.5l3 3"/><path d="M18 3v3M16.5 4.5h3M20 9v2M19 10h2M9 3v2M8 4h2"/>',
  brush: '<path d="M14.5 4.5l5 5-7.5 7.5-5-5z"/><path d="M7 12l-2.5 2.5c-1 1-1 3 0 4s3 1 4 0L11 16"/>',
  pen: '<path d="M4 20l1.2-4.4L16.3 4.5a1.8 1.8 0 0 1 2.6 0l.6.6a1.8 1.8 0 0 1 0 2.6L8.4 18.8z"/><path d="M14.5 6.5l3 3"/>',
  pin: '<path d="M9 3.5h6l-1 5 3 3v1.5H7V11.5l3-3z"/><path d="M12 13v7.5"/>',
  place: '<path d="M12 21s-6.5-6-6.5-11a6.5 6.5 0 0 1 13 0c0 5-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.3"/>',
  printer: '<path d="M6.5 9V3.5h11V9"/><rect x="3.5" y="9" width="17" height="7.5" rx="1.6"/><path d="M6.5 14h11v6.5h-11z"/>',
  compare: '<rect x="3" y="4.5" width="7.5" height="15" rx="1.4"/><rect x="13.5" y="4.5" width="7.5" height="15" rx="1.4"/>',
  paw: '<circle cx="7" cy="9" r="1.8"/><circle cx="12" cy="6.5" r="1.8"/><circle cx="17" cy="9" r="1.8"/><path d="M8 16.5c0-2.5 1.8-4.5 4-4.5s4 2 4 4.5c0 1.6-1.3 2.5-2.7 2.5-.6 0-.9-.3-1.3-.3s-.7.3-1.3.3C9.3 19 8 18.1 8 16.5z"/>',
  folderPlus: '<path d="M3.5 7a1.5 1.5 0 0 1 1.5-1.5h4.3l2 2H19a1.5 1.5 0 0 1 1.5 1.5v8.5A1.5 1.5 0 0 1 19 19H5a1.5 1.5 0 0 1-1.5-1.5z"/><path d="M12 10.5v5M9.5 13h5"/>',
  smart: '<path d="M3.5 7a1.5 1.5 0 0 1 1.5-1.5h4.3l2 2H19a1.5 1.5 0 0 1 1.5 1.5v8.5A1.5 1.5 0 0 1 19 19H5a1.5 1.5 0 0 1-1.5-1.5z"/><path d="M12.8 9.8l-2 3.4h2.4l-2 3.4"/>',
  rename: '<path d="M4 18.5h16"/><path d="M6.5 15l1-3.5 7-7a1.6 1.6 0 0 1 2.3 0l.7.7a1.6 1.6 0 0 1 0 2.3l-7 7z"/>',
  qr: '<rect x="3.5" y="3.5" width="6.5" height="6.5" rx="1"/><rect x="14" y="3.5" width="6.5" height="6.5" rx="1"/><rect x="3.5" y="14" width="6.5" height="6.5" rx="1"/><path d="M14 14h2.5v2.5H14zM18 18h2.5v2.5H18zM14 18.5v2M18.5 14h2"/>',
  doc: '<path d="M6.5 3.5h7l4 4v13h-11z"/><path d="M13.5 3.5v4h4M9 12h6M9 15.5h6"/>',
  receipt: '<path d="M6 3.5h12v17l-2-1.4-2 1.4-2-1.4-2 1.4-2-1.4-2 1.4z"/><path d="M9 8h6M9 11.5h6M9 15h3.5"/>',
  shared: '<circle cx="9" cy="9" r="3"/><circle cx="17" cy="10" r="2.4"/><path d="M3.5 19c.6-3 2.8-4.5 5.5-4.5s4.9 1.5 5.5 4.5M15 15.2c2.6-.4 4.8.8 5.5 3.8"/>',
  pause: '<path d="M8.5 5v14M15.5 5v14"/>',
  slideshow: '<rect x="3" y="4.5" width="18" height="12.5" rx="1.6"/><path d="M10.5 8.3v5l4-2.5z"/><path d="M8 20.5h8"/>',
  layers: '<path d="M12 3.5l8.5 4.5-8.5 4.5L3.5 8z"/><path d="M3.5 12.5l8.5 4.5 8.5-4.5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>',
  scissors: '<circle cx="6.5" cy="7" r="2.5"/><circle cx="6.5" cy="17" r="2.5"/><path d="M8.6 8.4L20 17M8.6 15.6L20 7"/>',
  workflow: '<rect x="3" y="4" width="6" height="5" rx="1"/><rect x="15" y="15" width="6" height="5" rx="1"/><path d="M9 6.5h4.5a2 2 0 0 1 2 2V15"/>',
  memory: '<rect x="3.5" y="5.5" width="17" height="13" rx="2"/><path d="M3.5 15l4.5-4 3.5 3 3-2.5 6 4.5"/><path d="M16 3v5M13.5 5.5h5"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  share: '<path d="M12 3.5v11M8 7.5l4-4 4 4"/><path d="M8.5 10.5H6.5a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1v-8a1 1 0 0 0-1-1h-2"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1.2 1.2"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1.2-1.2"/>',
  sync: '<path d="M19.5 9A8 8 0 0 0 5.2 7.2L4 8.5M4.5 15a8 8 0 0 0 14.3 1.8l1.2-1.3"/><path d="M4 4v4.5h4.5M20 20v-4.5h-4.5"/>',
} as const;

export type ExtraIcon = keyof typeof EXTRA_GLYPHS;

export function extraSvg(name: ExtraIcon): string {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${EXTRA_GLYPHS[name]}</svg>`;
}
