# Security Notice

## Hardcoded OAuth Client IDs
- EU: `62778dc4-1de3-44f4-af95-115f06a3a008` (const.py line 113)
- CN: `3f36efb1-f84b-4402-b5a2-68a118fec33e` (const.py line 114)

## Password Stored in HA Config Entry
The user's Mercedes Me password is stored in the HA config_entry data
(const.py line 90) and reused for automatic re-login on 429 errors
(websocket.py line 414-420). This persists the password on disk.

## ROPC Grant with PIN
oauth.py line 390 sends credentials via password grant:
`grant_type=password&username={email}&password={nonce}:{pin}`

## Recommendations
1. Remove password from config_entry after initial login
2. Use refresh_token exclusively for session recovery
3. Move OAuth client IDs to environment variables
