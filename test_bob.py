"""
Test IBM Bob API Connection
===========================
Tests the live connection via bob_client.py's two strategies:
  1. Bob Shell subprocess  (BOBSHELL_API_KEY in .env)
  2. Direct HTTP with bobshell/1.0.6 User-Agent + OAuth token from Bob IDE store

Usage:
    python test_bob.py
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

SEP = "=" * 60

def main():
    print(SEP)
    print("IBM Bob API Connection Test")
    print(SEP)

    # Import after load_dotenv so env vars are picked up
    from agents.bob_client import call_bob, BobAPIError, BOB_API_URL, BOB_MODEL, BOB_API_KEY, BOBSHELL_API_KEY

    print(f"\n  Endpoint     : {BOB_API_URL}")
    print(f"  Model        : {BOB_MODEL}")
    print(f"  API key set  : {'YES (' + BOB_API_KEY[:12] + '...)' if BOB_API_KEY else 'NO'}")
    print(f"  Shell key    : {'YES (' + BOBSHELL_API_KEY[:12] + '...)' if BOBSHELL_API_KEY else 'NO'}")

    # Check Bob Shell
    import shutil
    bob_bin = shutil.which("bob")
    print(f"  Bob Shell    : {bob_bin or 'NOT FOUND'}")

    print(f"\nTesting call_bob()...")

    system_prompt = "You are an expert data quality analyst for IBM Transport Analytics platform."
    user_message  = "In exactly one sentence, confirm you are connected and ready to analyse data quality."

    try:
        reply = call_bob(system_prompt, user_message, temperature=0.3)
        print(f"\n  [OK] Connected! Bob replied:")
        # Print safely, replacing any unmappable chars
        safe = reply.encode("ascii", errors="replace").decode("ascii")
        print(f"  \"{safe}\"")
        print(f"""
Add / update these lines in your .env file:

  BOB_API_URL={BOB_API_URL}
  BOB_MODEL={BOB_MODEL}
  BOB_INSTANCE_ID=your-instance-id-here
  BOB_TEAM_ID=your-team-id-here

Then start the server:  python app.py
All 5 agents will use live IBM Bob AI.
""")
        print(SEP)
        sys.exit(0)

    except BobAPIError as exc:
        print(f"\n  [FAIL] {exc}")
        print(f"""
Troubleshooting:
  1. Is IBM Bob IDE open and logged in?
     - Open Bob, make one chat request to refresh the OAuth token
  2. Is BOBSHELL_API_KEY set in .env?
     - BOB_API_KEY=bob_prod_bob-apikey_...  (Inference key from bob.ibm.com)
  3. Is Bob Shell installed?
     - npm install -g bobshell
  4. Are you on IBM VPN (Cisco AnyConnect)?
     - Required for /inference/v1/ endpoint

See HOW_TO_CONNECT_BOB.md for full instructions.
""")
        print(SEP)
        sys.exit(1)

if __name__ == "__main__":
    main()
