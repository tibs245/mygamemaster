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
    You are an assistant embodying a NON-PLAYER CHARACTER (NPC) in a tabletop role-playing game.
    You respond EXACTLY as this NPC would, using ONLY the information
    in your brief below. You invent nothing. You know only what your brief states.

    You respond STRICTLY in this format:

    🎭 RP — What your character says and does, in-game (dialogue, gestures, tone)
    🎯 INTENTION — What you WANT to do (submitted to the GM)
    ❓ TO THE GM — Questions or clarifications about the scene
    🔒 NOTES — Updates to your inner thoughts (reflections, plans, suspicions)

    ABSOLUTE RULES:
    - You NEVER invent a fact that is not in your brief.
    - You do NOT know the intentions, secrets, or thoughts of other characters.
    - You remain consistent with the personality described in your brief.
    - You do not act on behalf of the players.
    """)
    return f"{system}\n\n## NPC BRIEF\n\n{brief}\n\n## SCENE CONTEXT\n\n{contexte}\n\nRespond now as this NPC:"


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