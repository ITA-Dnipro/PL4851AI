# Backend

Django + Django REST Framework API.

## Requirements

- Python 3.11

## Setup

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # app deps + linters/formatters
cp .env.example .env
```

Fill in `SECRET_KEY` in `.env`. See [Database](#database) below.

Code style and pre-commit hooks are described in the [root README](../README.md#code-style--linting).

## Database

The project needs PostgreSQL: `Project.tags` is a PostgreSQL array field. SQLite (used when `DB_NAME` is empty) is no longer supported: migrations and tests of the `projects` app don't work on it, so don't leave `DB_NAME` empty.

With Docker the database is already there (`docker compose up db`; it listens on port `5433` on the host). To use PostgreSQL installed locally, create a user and a database (pick any names and password):

```bash
sudo -u postgres psql -c "CREATE USER <db_user> WITH PASSWORD '<db_password>';"
sudo -u postgres psql -c "CREATE DATABASE <db_name> OWNER <db_user>;"
```

Then set the same values in `.env`:

```
DB_NAME=<db_name>
DB_USER=<db_user>
DB_PASSWORD=<db_password>
DB_HOST=localhost
DB_PORT=5432
```

## Commands

```bash
python manage.py migrate     # apply migrations
python manage.py runserver   # start dev server at http://127.0.0.1:8000
```

Health check: `GET /api/health/` returns `{"status": "ok"}`.

## Landing content

`GET /api/content/landing/` returns the landing page content: hero, banner, "for whom" and "why worth" blocks.

Content is edited in the admin:

- **Content: sections** — the blocks themselves (texts, images, cards);
- **Content: pages → Landing Page** — which blocks are shown on the page.

Load the initial content after `migrate`:

```bash
python manage.py loaddata landing
```

The fixture lives in `content/pages/fixtures/landing.json`. Loading it again overwrites the landing records with the fixture data, so changes made in the admin will be lost.

## Authentication

`POST /api/auth/login/` — log in with email and password.

```json
{ "email": "user@example.com", "password": "P@ssw0rd", "remember": true }
```

Response `200`:

```json
{ "access": "<jwt>", "user": { "id": 1, "email": "user@example.com", "role": "startup" } }
```

The refresh token is set in the `refresh_token` cookie: `HttpOnly` (JavaScript can't read it), `SameSite=Lax`, `Path=/api/auth/`, `Secure` when `DEBUG` is off. Without `"remember": true` it's a session cookie, removed when the browser closes.

- Access token lives 15 minutes, refresh token 1 day (30 days with `"remember": true`).
- Send the access token as `Authorization: Bearer <access>`. Keep it in memory, not in `localStorage`.
- Errors: `400` invalid data, `401` wrong email or password, `429` too many requests or too many failed attempts: 5 for this email from one client (IP) → that client is locked for 15 minutes; 20 for this email from any clients → the email is locked for 1 hour.

`POST /api/auth/refresh/` — get a new access token, e.g. when the old one expires or after a page reload. No body: the token is taken from the cookie.

Response `200`:

```json
{ "access": "<jwt>" }
```

- The refresh token itself stays the same, so the session still ends 1 day (or 30 days) after login.
- Errors: `401` no cookie, or the token is invalid, expired, revoked, or the user is inactive or deleted. The client should then show the login page.

`POST /api/auth/logout/` — revoke the refresh token and delete the cookie. No body.

- Always returns `204`, even without a cookie or with an invalid one: the client can't delete an `HttpOnly` cookie, so it relies on this endpoint.
- The access token can't be revoked and keeps working until it expires (up to 15 minutes), so the client should drop it on logout.
- Issued and revoked refresh tokens are stored in the database (admin: **Token Blacklist**). Expired ones can be removed with `python manage.py flushexpiredtokens`.

Frontend requests to `/api/auth/` must use `credentials: 'include'`, otherwise the browser doesn't send or save the cookie. CORS allows it for the origins in `CORS_ALLOWED_ORIGINS`. `SameSite=Lax` works while the frontend and the API are on the same site (as `localhost:5173` and `localhost:8000` are); on different domains the cookie would need `SameSite=None` and CSRF protection.

- Use `localhost` for both the frontend and the API, not `127.0.0.1`: for the browser they are different sites, so the cookie isn't sent and refresh returns `401`.
- Login, refresh and logout check the `Origin` header: requests from other sites get `403`, so a foreign page can't log the user in or out through a form. Allowed origins are the API's own (the browsable API) and `CORS_ALLOWED_ORIGINS`; requests without `Origin` (curl, Postman) are allowed.

## Investors

Public, read-only endpoints. No authentication is needed. Only verified investors (`is_verified=True`) are returned.

`GET /api/investors/` — paginated list.

- Query params: `page`, `page_size` (default 8, max 100), `search` (by name, case-insensitive substring), `type` (`private`, `fund` or `company`).
- Response `200`: `count`, `next`, `previous` and `results`; each item has `investor_id`, `investor_name`, `investor_type`, `investment_min` (a string like `"50000.00"`, or `null`).
- Errors: `400` unknown, empty or wrongly cased `type` (the message lists the allowed values), `404` page out of range.

`GET /api/investors/{id}/` — public profile.

```json
{
  "investor_id": 901,
  "investor_name": "Green Capital",
  "investor_type": "fund",
  "investor_description": "We invest in craft food and eco packaging.",
  "contact": { "phone": "+380501234567" },
  "investment_min": "50000.00",
  "is_verified": true
}
```

- `contact.phone` is an empty string if the phone is not set.
- Errors: `404` for an unknown id and for an unverified investor (the response is the same, so the existence is not revealed).
- `investor_description` is returned as stored, without sanitization. Show it as plain text, not as HTML.
- The user and the registration number (`edrpou_or_ipn`) are never exposed.

Load sample investors (3 verified, 1 unverified):

```bash
python manage.py loaddata investors
```

## Projects

A project belongs to a startup. Its id is a UUID. `status` is one of `idea`, `mvp`, `fundraising`, `funded`, `closed` (default `idea`); `visibility` is `public`, `private` or `unlisted` (default `public`).

| Method | URL | Who |
|---|---|---|
| `GET` | `/api/startups/{startup_id}/projects/` | anyone: public projects; the owner also sees their `private` and `unlisted` ones |
| `POST` | `/api/startups/{startup_id}/projects/` | the owner of the startup |
| `GET` | `/api/projects/{id}/` | anyone for public projects; the owner for the rest |
| `PATCH`, `PUT` | `/api/projects/{id}/` | the owner |
| `DELETE` | `/api/projects/{id}/` | the owner (soft delete, `204`) |
| `GET` | `/api/projects/{id}/history/` | the owner: paginated change history, newest first |

Create request (only `title`, `description` and `target_amount` are required):

```json
{
  "title": "Handmade Chairs",
  "short_description": "Oak chairs",
  "description": "<p>full text</p>",
  "target_amount": "50000",
  "currency": "UAH",
  "tags": ["wood", "furniture"],
  "visibility": "public"
}
```

Response `201` has a `Location` header and the project: `id`, `title`, `slug`, `short_description`, `description`, `status`, `target_amount`, `raised_amount`, `currency`, `tags`, `visibility`, `logo`, `created_at`, `updated_at`.

- `slug` is made from the title when the project is created and never changes. `startup` and `slug` in a request are ignored, so a project can't be moved to another startup.
- `currency` is 3 uppercase letters (default `UAH`), `tags` has up to 10 items of up to 30 characters, `target_amount` must be above 0, `raised_amount` can't be negative. `raised_amount` is set by the owner by hand.
- Statuses can be changed freely: the allowed transitions are not checked yet.
- `private` and `unlisted` projects exist only for their owner: anyone else gets `404`. For writes on a public project a non-owner gets `403`, anonymous users get `401`.
- Deleted projects are hidden everywhere (`404`) but stay in the database. Admin (**Projects**) can change the visibility, delete and restore projects with actions.
- Every create, update and delete (API and admin actions) is written to the history: `changes` is `{"field": {"before": ..., "after": ...}}`. Updates that change nothing are not recorded.
- `projects_count` in `GET /api/startups/{id}/` counts only public, not deleted projects.

Load sample projects (5 projects with different statuses, one private):

```bash
python manage.py loaddata projects
```
