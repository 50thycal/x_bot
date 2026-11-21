"""Verify the X API secrets without posting anything.

Calls GET /2/users/me (one owned read, ~$0.001) and reports:
- which account the keys belong to
- the token's access level from the `x-access-level` header (must be read-write to post)
"""
from __future__ import annotations

import os
import sys

from publisher import xbot

EXPECTED = os.environ.get("EXPECTED_HANDLE", "50th_ETH").lstrip("@").lower()


def main() -> int:
    missing = [k for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")
               if not os.environ.get(k, "").strip()]
    if missing:
        print(f"FAIL: missing GitHub secrets: {', '.join(missing)}")
        return 1
    creds = xbot.XCreds.from_env()
    try:
        data, headers = xbot.x_request_full("GET", "/users/me", creds)
    except xbot.XError as e:
        hint = {401: "keys/tokens wrong or revoked - regenerate and re-paste",
                402: "no API credit - add credit in the Developer Console",
                403: "app not attached to a project or not allowed this endpoint"}.get(e.status, "")
        print(f"FAIL: {e}\n{hint}")
        return 1
    user = data.get("data", {})
    level = headers.get("x-access-level", "unknown")
    print(f"Authenticated as @{user.get('username')} (id {user.get('id')})")
    print(f"Access level: {level}")
    ok = True
    if user.get("username", "").lower() != EXPECTED:
        print(f"FAIL: expected @{EXPECTED}. The access token was generated for a different account.")
        ok = False
    if level != "unknown" and "write" not in level:
        print("FAIL: token is read-only. Set app permissions to 'Read and write', then REGENERATE the "
              "Access Token and Secret and update the two GitHub secrets.")
        ok = False
    print("OK: keys are ready to post." if ok else "")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
