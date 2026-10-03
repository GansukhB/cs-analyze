# 24-hour JWT access tokens in localStorage, no server-side logout

The public app keeps a JWT access token in `localStorage` and sends it as an `Authorization: Bearer` header. The token is valid for 24 hours, there is no refresh token, and logout only deletes the token on the client. We chose this over a Redis-backed session in an httpOnly cookie (and over a Redis denylist on logout) to keep auth stateless and to let Swagger's "Authorize" button work with the same flow the app uses.

## Consequences

- If a token is stolen through XSS, it keeps working for up to 24 hours, even after the User logs out.
- The only server-side cut-off is deactivating the User: every request reloads the User and rejects tokens of a Deactivated User.
- Moving to cookies or adding a denylist later means changing both apps' auth flow.
