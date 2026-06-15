#!/usr/bin/env python3
"""
Phase 1 — NPC brief cache
Extracts the brief for an NPC from npcs.json, with checksum-based caching.
Avoids re-paying the read/parsing cost if nothing has changed.

Usage:
  python3 build_brief.py <campagne> <pnj_nom>              # extract + display
  python3 build_brief.py <campagne> <pnj_nom> --cache       # use/refresh the cache
  python3 build_brief.py <campagne> <pnj_nom> --invalidate  # clear the cache
  python3 build_brief.py <campagne> --list                  # list available NPCs
"""

import json, sys, os, hashlib, textwrap

CACHE_DIR = os.path.expanduser("~/.hermes/mygamemaster/cache-briefs")


def checksum_file(path):
    """MD5 of the file — detects any change."""
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def find_pnj(pnj_list, name):
    """Search for an NPC by name, case-insensitive match."""
    name_lower = name.lower().strip()
    for pnj in pnj_list:
        if pnj.get('nom', '').lower() == name_lower:
            return pnj
    # Partial match
    for pnj in pnj_list:
        if name_lower in pnj.get('nom', '').lower():
            return pnj
    return None


def build_brief(pnj):
    """Build the text brief for an NPC from their sheet."""
    lines = []
    lines.append(f"=== NPC BRIEF : {pnj.get('nom', 'UNKNOWN')} ===")
    lines.append(f"Title: {pnj.get('titre', '')}")
    lines.append(f"Description: {pnj.get('description', '')}")
    lines.append(f"Attitude: {pnj.get('attitude', '')}")
    lines.append(f"Relation: {pnj.get('relation_niveau', '')}")
    lines.append(f"Location: {pnj.get('localisation_actuelle', 'Unknown')}")
    lines.append("")

    faits = pnj.get('established_facts', [])
    if faits:
        lines.append("--- ESTABLISHED FACTS (what the NPC knows) ---")
        for f in faits:
            lines.append(f"  • {f}")
        lines.append("")

    limites = pnj.get('limites', {})
    if limites:
        lignes = limites.get('lignes_rouges', [])
        if lignes:
            lines.append("--- RED LINES ---")
            for l in lignes:
                lines.append(f"  • {l}")
        peurs = limites.get('peurs', [])
        if peurs:
            lines.append("--- FEARS ---")
            for p in peurs:
                lines.append(f"  • {p}")
        motivations = limites.get('motivations_personnelles', [])
        if motivations:
            lines.append("--- MOTIVATIONS ---")
            for m in motivations:
                lines.append(f"  • {m}")
        lines.append("")

    inv = pnj.get('inventaire', [])
    if inv:
        lines.append("--- INVENTORY ---")
        for item in inv:
            lines.append(f"  • {item}")
        lines.append("")

    competences = pnj.get('competences_observees', {})
    if competences:
        lines.append("--- OBSERVED SKILLS ---")
        for nom, data in competences.items():
            bonus = data.get('bonus', 0)
            lines.append(f"  • {nom} (+{bonus})")
        lines.append("")

    stats = pnj.get('stats', {})
    if stats:
        lines.append("--- STATS ---")
        stat_str = ", ".join(f"{k}:{v}" for k, v in stats.items())
        lines.append(f"  {stat_str}")
        lines.append("")

    # Private notes (inner monologue) if present
    notes = pnj.get('notes_privees', [])
    if notes:
        lines.append("--- INNER MONOLOGUE ---")
        for n in notes:
            lines.append(f"  • {n}")
        lines.append("")

    lines.append("=== END OF BRIEF ===")
    return "\n".join(lines)


def cache_path(campagne_nom, pnj_nom):
    """Path to the cache file for a given NPC."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    slug = f"{campagne_nom}_{pnj_nom}".lower().replace(" ", "_").replace("'", "")
    return os.path.join(CACHE_DIR, f"brief_{slug}.json")


def load_cache(campagne_nom, pnj_nom, pnj_json_path):
    """Load from cache if valid, otherwise None."""
    cpath = cache_path(campagne_nom, pnj_nom)
    if not os.path.exists(cpath):
        return None
    try:
        with open(cpath, 'r') as f:
            data = json.load(f)
        # Verify the checksum
        current_cs = checksum_file(pnj_json_path)
        if data.get('checksum') == current_cs:
            return data.get('brief')
        else:
            return None
    except (json.JSONDecodeError, KeyError):
        return None


def save_cache(campagne_nom, pnj_nom, pnj_json_path, brief):
    """Save the brief to cache."""
    cpath = cache_path(campagne_nom, pnj_nom)
    data = {
        'checksum': checksum_file(pnj_json_path),
        'campagne': campagne_nom,
        'pnj_nom': pnj_nom,
        'brief': brief
    }
    with open(cpath, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return cpath


def invalidate_cache(campagne_nom, pnj_nom):
    """Delete the cache for an NPC."""
    cpath = cache_path(campagne_nom, pnj_nom)
    if os.path.exists(cpath):
        os.remove(cpath)
        return True
    return False


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 build_brief.py <campagne> <pnj_nom>              # extract + display")
        print("  python3 build_brief.py <campagne> <pnj_nom> --cache      # use the cache")
        print("  python3 build_brief.py <campagne> <pnj_nom> --invalidate # clear the cache")
        print("  python3 build_brief.py <campagne> --list                 # list NPCs")
        sys.exit(1)

    campagne_path = sys.argv[1]
    # If it is a relative path, resolve it
    if not campagne_path.startswith('/'):
        base = os.path.expanduser("~/.hermes/mygamemaster/campaigns")
        campagne_path = os.path.join(base, campagne_path)

    # Extract the campaign name for the cache
    campagne_nom = os.path.basename(campagne_path.rstrip('/'))

    pnj_json_path = os.path.join(campagne_path, 'npcs.json')

    if not os.path.exists(pnj_json_path):
        print(f"❌ File not found: {pnj_json_path}")
        sys.exit(1)

    with open(pnj_json_path, 'r') as f:
        pnj_data = json.load(f)

    # --list mode
    if '--list' in sys.argv:
        print("NPCs available in this campaign:")
        for pnj in pnj_data:
            loc = pnj.get('localisation_actuelle', '?')
            print(f"  • {pnj['nom']:20s} [{loc}]")
        sys.exit(0)

    if len(sys.argv) < 3:
        print("❌ NPC name required (or --list)")
        sys.exit(1)

    pnj_nom = sys.argv[2]
    use_cache = '--cache' in sys.argv
    invalidate = '--invalidate' in sys.argv

    # Cache invalidation
    if invalidate:
        if invalidate_cache(campagne_nom, pnj_nom):
            print(f"✅ Cache cleared for {pnj_nom}")
        else:
            print(f"ℹ️  No cache found for {pnj_nom}")
        sys.exit(0)

    # Look up the NPC
    pnj = find_pnj(pnj_data, pnj_nom)
    if not pnj:
        print(f"❌ NPC '{pnj_nom}' not found in {pnj_json_path}")
        print("Available NPCs:")
        for p in pnj_data:
            print(f"  • {p['nom']}")
        sys.exit(1)

    # Attempt cache lookup
    if use_cache:
        cached = load_cache(campagne_nom, pnj_nom, pnj_json_path)
        if cached:
            print(cached)
            # Stats on stderr
            print(f"\n--- [Cache HIT — npcs.json unchanged] ---", file=sys.stderr)
            sys.exit(0)
        else:
            print("\n--- [Cache MISS — regenerating] ---", file=sys.stderr)

    # Build the brief
    brief = build_brief(pnj)

    # Save to cache if requested
    if use_cache:
        cpath = save_cache(campagne_nom, pnj_nom, pnj_json_path, brief)
        print(f"📦 Brief cached: {cpath}", file=sys.stderr)

    print(brief)
    # Stats on stderr
    token_estimation = len(brief.split()) * 1.3  # ~1.3 tokens/word
    print(f"\n--- [Brief size: ~{token_estimation:.0f} estimated tokens] ---", file=sys.stderr)


if __name__ == '__main__':
    main()