"""
Fantasy Baseball Keeper League - Yahoo OAuth2 Authorization

Run this script ONCE to complete the OAuth2 authorization flow.
After successful auth, oauth2.json will be created with your access token.

Steps:
1. Run this script
2. Open the printed URL in your browser
3. Log in to Yahoo and authorize the app
4. Copy the verification code from the browser
5. Paste it back here

After that, test_yahoo_api.py and other scripts can use the saved token.
"""
from __future__ import annotations

import json
import os
import sys
import webbrowser
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv(project_root / ".env")


def main():
    print("=" * 55)
    print(" Yahoo Fantasy API - OAuth2 Authorization")
    print("=" * 55)

    client_id = os.getenv("YAHOO_CLIENT_ID")
    client_secret = os.getenv("YAHOO_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("\nError: YAHOO_CLIENT_ID / YAHOO_CLIENT_SECRET not found in .env")
        return

    oauth_file = project_root / "oauth2.json"

    # Create initial OAuth credentials file
    creds = {
        "consumer_key": client_id,
        "consumer_secret": client_secret,
    }
    oauth_file.write_text(json.dumps(creds, indent=2))
    print(f"\nCreated: {oauth_file}")

    # Build authorization URL
    auth_url = (
        "https://api.login.yahoo.com/oauth2/request_auth"
        f"?redirect_uri=oob"
        f"&response_type=code"
        f"&client_id={client_id}"
    )

    print(f"\n--- Step 1: Open this URL in your browser ---")
    print(f"\n{auth_url}\n")

    # Try to open browser automatically
    try:
        webbrowser.open(auth_url)
        print("(Browser should open automatically)")
    except Exception:
        print("(Please copy and paste the URL above into your browser)")

    print(f"\n--- Step 2: Log in to Yahoo and authorize the app ---")
    print(f"\n--- Step 3: Copy the verification code and paste it below ---\n")

    verifier = input("Enter verification code: ").strip()

    if not verifier:
        print("No code entered. Aborting.")
        return

    print(f"\nExchanging code for access token...")

    # Exchange verification code for access token
    try:
        import requests
        from requests.auth import HTTPBasicAuth

        token_url = "https://api.login.yahoo.com/oauth2/get_token"
        response = requests.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "redirect_uri": "oob",
                "code": verifier,
            },
            auth=HTTPBasicAuth(client_id, client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code == 200:
            token_data = response.json()

            # Save complete OAuth data
            oauth_data = {
                "consumer_key": client_id,
                "consumer_secret": client_secret,
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "token_type": token_data.get("token_type", "bearer"),
                "guid": token_data.get("xoauth_yahoo_guid", ""),
            }
            oauth_file.write_text(json.dumps(oauth_data, indent=2))

            print(f"\nAuthorization successful!")
            print(f"Token saved to: {oauth_file}")
            print(f"GUID: {oauth_data['guid']}")
            print(f"\nYou can now run: python scripts/test_yahoo_api.py")
        else:
            print(f"\nToken exchange failed: {response.status_code}")
            print(f"Response: {response.text}")
            print(f"\nPlease try again. Make sure you enter the code quickly")
            print(f"(it expires in about 30 seconds).")
    except Exception as e:
        print(f"\nError: {e}")
        print(f"\nIf this fails, you can also try running:")
        print(f"  python -c \"from yahoo_oauth import OAuth2; OAuth2(None, None, from_file='oauth2.json')\"")


if __name__ == "__main__":
    main()
