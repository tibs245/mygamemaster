#!/usr/bin/env python3
"""
Phase 2 — N1 Call (Agent "Brief")
Gateway version: generates the prompt and passes it to the Hermes gateway for execution.

Usage:
  python3 call_pnj.py <campagne> <pnj_nom> "<contexte>"  # generate + gateway
  python3 call_pnj.py <campagne> <pnj_nom> --dry-run "<contexte>"  # show the prompt without calling
  python3 call_pnj.py <campagne> <pnj_nom> --stdin      # context from stdin
"""

import json, sys, os, subprocess, tempfile, textwrap

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
build_brief = os.path.join(SCRIPT_DIR, 'build_brief.py')


def get_brief(campagne, pnj_nom):
    result = subprocess.run(
        [sys.executable, build_brief, campagne, pnj_nom, '--cache'],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode != 0:
        print(f"❌ Error build_brief: {result.stderr}", file=sys.stderr)
        return None
    return result.stdout


def build_prompt(brief, contexte):
    system = textwrap.dedent(f"""\
    Tu es un assistant qui incarne un PERSONNAGE NON-JOUEUR (PNJ) dans une partie de jeu de rôle.
    Tu réponds EXACTEMENT comme ce PNJ le ferait, en utilisant UNIQUEMENT les informations
    de ton brief ci-dessous. Tu n'inventes rien. Tu ne sais que ce que ton brief dit.
    
    Tu réponds STRICTEMENT dans ce format :
    
    🎭 RP — Ce que ton personnage dit et fait, en jeu (dialogue, gestes, ton)
    🎯 INTENTION — Ce que tu VEUX faire (soumis au MJ)
    ❓ AU MJ — Questions ou clarifications sur la scène
    🔒 NOTES — Mises à jour de ton for intérieur (réflexions, plans, soupçons)
    
    RÈGLES ABSOLUES :
    - Tu n'inventes JAMAIS un fait qui n'est pas dans ton brief.
    - Tu ne connais PAS les intentions, secrets, ou pensées des autres personnages.
    - Tu restes cohérent avec ta personnalité décrite dans le brief.
    - Tu n'agis pas à la place des joueurs.
    """)
    return f"{system}\n\n## BRIEF DU PNJ\n\n{brief}\n\n## CONTEXTE DE SCÈNE\n\n{contexte}\n\nRéponds maintenant en tant que ce PNJ :"


def token_count(text):
    return int(len(text.split()) * 1.3)


def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python3 call_pnj.py <campagne> <pnj_nom> \"<contexte>\"")
        print("  python3 call_pnj.py <campagne> <pnj_nom> --dry-run \"<contexte>\"")
        print("  python3 call_pnj.py <campagne> <pnj_nom> --stdin")
        sys.exit(1)

    campagne = sys.argv[1]
    pnj_nom = sys.argv[2]

    dry_run = '--dry-run' in sys.argv
    use_stdin = '--stdin' in sys.argv

    if use_stdin:
        contexte = sys.stdin.read().strip()
    elif dry_run:
        idx = sys.argv.index('--dry-run')
        contexte = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
    else:
        if len(sys.argv) < 4:
            print("❌ Context required", file=sys.stderr)
            sys.exit(1)
        contexte = sys.argv[3]

    # Retrieve the brief
    print(f"📖 Retrieving brief for {pnj_nom}...", file=sys.stderr)
    brief = get_brief(campagne, pnj_nom)
    if not brief:
        sys.exit(1)

    prompt = build_prompt(brief, contexte)
    prompt_tokens = token_count(prompt)
    brief_tokens = token_count(brief)

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"📊 Stats:", file=sys.stderr)
    print(f"   Brief: ~{brief_tokens} tokens", file=sys.stderr)
    print(f"   Total prompt: ~{prompt_tokens} tokens", file=sys.stderr)
    print(f"   Context: ~{token_count(contexte)} tokens", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    if dry_run:
        print("\n" + "="*60)
        print("FULL PROMPT (DRY RUN)")
        print("="*60)
        print(prompt)
        print("="*60)
        print(f"\n✅ Dry-run complete.")
        sys.exit(0)

    # Normal mode: save the prompt to a file
    # The file will be read by the GM (or the Hermes gateway)
    prompt_path = f"/tmp/pnj_prompt_{pnj_nom.lower()}_{os.getpid()}.txt"
    with open(prompt_path, 'w') as f:
        f.write(prompt)
    
    print(f"📄 Prompt saved: {prompt_path}", file=sys.stderr)
    print(f"💡 To execute: cat {prompt_path} | hermes chat -p pnj-{pnj_nom.lower()} -q \"@prompt\"", file=sys.stderr)
    print(f"\n--- PROMPT ---")
    print(prompt)


if __name__ == '__main__':
    main()