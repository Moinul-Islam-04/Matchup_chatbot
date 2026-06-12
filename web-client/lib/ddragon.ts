// Client-side Data Dragon loader: builds name → icon-URL maps for champions,
// items, and runes straight from the public CDN (no API key, permissive CORS).
// Used to render inline icons next to names the model mentions.

const BASE = "https://ddragon.leagueoflegends.com";

export type IconMaps = {
  version: string;
  champions: Map<string, string>;
  items: Map<string, string>;
  runes: Map<string, string>;
};

const norm = (s: string) => s.trim().toLowerCase();

let cache: Promise<IconMaps> | null = null;

export function loadIconMaps(): Promise<IconMaps> {
  if (!cache) cache = build();
  return cache;
}

async function build(): Promise<IconMaps> {
  const versions: string[] = await fetch(`${BASE}/api/versions.json`).then((r) =>
    r.json(),
  );
  const version = versions[0];
  const loc = "en_US";

  const [champ, item, runes] = await Promise.all([
    fetch(`${BASE}/cdn/${version}/data/${loc}/champion.json`).then((r) => r.json()),
    fetch(`${BASE}/cdn/${version}/data/${loc}/item.json`).then((r) => r.json()),
    fetch(`${BASE}/cdn/${version}/data/${loc}/runesReforged.json`).then((r) => r.json()),
  ]);

  const champions = new Map<string, string>();
  for (const c of Object.values<any>(champ.data)) {
    champions.set(norm(c.name), `${BASE}/cdn/${version}/img/champion/${c.image.full}`);
  }

  // item.json ships per-game-mode variants under the same name; prefer the
  // Summoner's Rift purchasable one for the icon.
  const items = new Map<string, string>();
  for (const it of Object.values<any>(item.data)) {
    const n = norm(it.name ?? "");
    if (!n || !it.image?.full) continue;
    const better = it.maps?.["11"] && it.gold?.purchasable;
    if (!items.has(n) || better) {
      items.set(n, `${BASE}/cdn/${version}/img/item/${it.image.full}`);
    }
  }

  // Rune icons live under /cdn/img/ (no version) using the rune's `icon` path.
  const runeMap = new Map<string, string>();
  for (const tree of runes as any[]) {
    for (const slot of tree.slots) {
      for (const r of slot.runes) {
        runeMap.set(norm(r.name), `${BASE}/cdn/img/${r.icon}`);
      }
    }
  }

  return { version, champions, items, runes: runeMap };
}

/** Exact (case-insensitive) lookup of an icon URL for a name the model wrote. */
export function lookupIcon(maps: IconMaps | null, text: string): string | null {
  if (!maps) return null;
  const key = norm(text);
  return (
    maps.champions.get(key) ?? maps.items.get(key) ?? maps.runes.get(key) ?? null
  );
}
