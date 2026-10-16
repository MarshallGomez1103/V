# Local server authentication

`ServerAuthMiddleware` provides optional shared-token authentication for the
entire ASGI application. With `token=None`, requests and lifecycle messages pass
through unchanged. A configured token protects every HTTP path, including the
web interface, static assets, health checks, SSE and media downloads. There are
no public-path exceptions, accounts or per-user permissions.

## Setup

Create an explicitly chosen private token file and pass it when starting the
server:

```sh
v auth-token --output ../v-server-token.txt
v serve --host 0.0.0.0 --auth-token-file ../v-server-token.txt --no-browser
```

The token file is explicitly chosen, created exclusively with private permissions
(0600 on POSIX), and never printed by the creation command. Keep it outside the
repository. Tokens contain 32–512 URL-safe ASCII characters (`A-Z`, `a-z`, `0-9`,
`_`, `-`). The CLI requires a valid private token file for any bind
outside loopback, before checking whether an existing server can be reused.
For loopback, authentication remains optional:

```sh
v serve --host 127.0.0.1 --auth-token-file ../v-server-token.txt
```

Authentication does not encrypt traffic. Use an encrypted transport when the
network is not trusted. Basic transmits a reversible Base64 representation of
the credentials; Bearer also carries the token in the request. Do not put tokens
in URLs, shell arguments, diagnostics or logs. See
[RFC 7617](https://www.rfc-editor.org/rfc/rfc7617.html) and
[RFC 6750](https://www.rfc-editor.org/rfc/rfc6750.html).

## Clients

API clients send one `Authorization: Bearer <token>` header. They may omit
`Origin`; when supplied, it must match the request's scheme, Host and effective
port. Tokens in query parameters, cookies or bodies are not accepted.

Browsers receive a `Basic realm="V"` challenge. Enter username **`v`** and the
token as the password in the browser's native authentication prompt. The browser
can then reuse credentials for assets, fetch, EventSource and media requests on
the same server. The production bundle has been exercised in Chromium using the Basic
challenge, cached credentials for assets and fetch, and a same-origin POST.
The challenge was answered through browser automation; a human-operated prompt
and other browser implementations have not been verified.

Basic requests with an `Origin` must match the server origin. Basic operations
other than HTTP GET and HEAD require that matching header, including WebSocket
connections. A Basic POST without Origin is rejected; a non-browser client can
use Bearer instead. `Sec-Fetch-Site`, when present with Basic, must be
`same-origin` or `none`. Thus foreign origins cannot use cached browser
credentials to modify state. GET and HEAD routes must remain free of state
changes. Origin comparison follows the scheme/host/port model in
[RFC 6454](https://www.rfc-editor.org/rfc/rfc6454.html).

Origin checks use the ASGI scheme and Host, without trusting `Forwarded` or
`X-Forwarded-*` headers. Keep the Host guard enabled. If TLS terminates at a
reverse proxy, configure the ASGI server's trusted proxy handling explicitly so
its scheme matches the external origin.

## Failure contract

Invalid credentials produce HTTP 401 without invoking the application or
reading the request body:

```json
{"detail":{"code":"server_auth_required","message":"Valid server credentials are required."}}
```

The response includes `Cache-Control: no-store` and separate Basic and Bearer
`WWW-Authenticate` challenges. It never reflects the supplied token or header.
Duplicate security headers, Authorization values over 1024 bytes, non-ASCII
credentials and malformed credentials are rejected. Token comparisons use
`hmac.compare_digest`; the configured token is private and excluded from the
middleware representation. Invalid configuration raises `ServerAuthTokenError`
with code `server_auth_token_invalid` and a fixed safe message.

Unauthorized WebSocket scopes emit `websocket.close` with code 1008 before
acceptance. As described in the
[ASGI specification](https://asgi.readthedocs.io/en/latest/specs/www.html), an
ASGI server may represent this pre-accept denial as HTTP 403 on the wire.
Valid scopes retain the original `scope`, `receive` and `send` objects; upload
chunks, SSE, Range responses, disconnects and lifespan events are not buffered.
