# ShopAgents: Centralized Multi-Agent Shopping Assistant

A website where registered customers ask questions about **food**, **clothes** and **electronics**
in plain language. A **central router agent** splits each question by category, sends the parts to
three **specialist agents** at the same time, and combines their answers into one reply. Each
specialist agent owns its own website list and database, which it refreshes automatically
every day by scraping its websites. Every user's chat history is saved, and administrators
can review it.

The full requirements and design are in
[docs/Multi_Agent_Shopping_Assistant_Requirements.pdf](docs/Multi_Agent_Shopping_Assistant_Requirements.pdf).

```
 Customer / Admin
        |
   Website + API  (FastAPI, /api/...)
     |        \
 User          Central router agent ---- saves every message ----> app.db (users, chat history)
 management    plan -> call agents in parallel -> combine
     |          /            |              \
  app.db   Food agent   Clothes agent   Electronics agent
               |              |                 |
            food.db       clothes.db      electronics.db
               \              |                 /
                 Daily refresh at 00:00 (each agent scrapes its own websites)
```

---

## 1. Requirements

- **Python 3.11 or newer** (tested with Python 3.14 on Windows 11)
- **Internet access** the first time you run the app, so the agents can scrape their websites
- No API key is needed. Claude is optional (see section 6).

## 2. Setup (first time only)

Open **PowerShell** in the project folder:

```powershell
cd "C:\Chevon\Multi agent system\MutiAgentProject\Multi_Agent_System"
git checkout feature/multi-agent-system
```

Create a virtual environment and install the dependencies:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

(On macOS/Linux use `.venv/bin/python` instead of `.venv\Scripts\python`.)

Optional: copy the settings file if you want to change anything (port, scrape time, Claude):

```powershell
copy .env.example .env
```

Every setting has a working default, so you can skip this step.

## 3. Create the admin account

Admins cannot sign up on the website (UM-7). Create one from the command line. You will be
asked to type the password twice (8–72 characters):

```powershell
.venv\Scripts\python scripts\create_admin.py --email admin@example.com --name "Site Admin"
```

Running it again with an existing email makes that user an admin and resets their password.

## 4. Load product data (recommended before the first start)

This scrapes every website once and fills the three product databases. It takes about one minute:

```powershell
.venv\Scripts\python -m app.scheduler.run_now
```

Expected output (product counts can change as the sites change):

```
Refreshing the food agent ...
  web-scraping.dev: 6 products
  dummyjson.com: 27 products
Refreshing the clothes agent ...
  ...
Refreshing the electronics agent ...
  webscraper.io: 144 products
  ...
```

You can also refresh a single agent: `.venv\Scripts\python -m app.scheduler.run_now food`.
If you skip this step, the app scrapes in the background on its first start anyway.

## 5. Run the application

```powershell
.venv\Scripts\python run.py
```

Then open **http://127.0.0.1:8000** in your browser. Press `Ctrl+C` in the terminal to stop.

Options: `python run.py --port 8010` (another port), `--host 0.0.0.0` (let other devices on your
network open it), `--data-dir PATH` (use a different folder for the databases).

While the server runs, it refreshes every agent's data at 00:00 each day (FR-7).

### Try it

1. Open the site. Guests only see the login page.
2. Click **Create an account**, register and you are logged in.
3. Try these questions (or click the example buttons):
   - `Cheapest rice?` → food agent
   - `Laptops under $500 with 8GB RAM` → electronics agent with a price filter
   - `A rain jacket and a power bank` → clothes **and** electronics, one combined reply
   - `Show me cheaper ones` → the assistant asks which category you mean
   - `shirts` / `power banks` → only that agent is called
   - `Running shoes and earphones under $150 in total` → combinations that fit the budget
   - `Apple` → asks whether you mean the fruit or the brand
   - `What's the weather today?` → polite out-of-scope reply
4. **Click any product card** to open its details on the right side of the same page: photos,
   price, rating, description and specifications. Press `Esc` or `×` to close it.
5. **Click "How it works (live)"** at the top, or **"See how the agents answered this"** under any
   reply. The live architecture page animates the real request on the system diagram:
   customer → website/API → login check → central agent (task planner) → the domain agents in
   parallel → their databases → answer combiner → app.db → customer. The step-by-step list shows
   the real data and timing of each step: the tasks created, how many products each agent
   checked and matched, and how long each step took. You can also ask new questions there
   (choose "Slow" when presenting).
6. Log out and back in: your conversations are still in the sidebar.
7. Log in as the admin and click **Admin dashboard**:
   - **Users and chat history:** search users, open any conversation (read-only), and see
     which agents answered each message. Deactivate or reactivate accounts.
   - **Agents and data sources:** product counts and scrape runs per agent, plus a
     **Refresh all agents now** button.
   - **Audit log:** every time an admin opened a user's history.

## 6. Optional: use Claude for planning and replies

By default the system is **rule-based**: a keyword planner decides which agents to call, and
replies use a fixed template. To let Claude plan tasks and write replies, edit `.env`:

```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-key-here
LLM_MODEL=claude-opus-5-5
```

If the key is wrong, the API is unreachable, or Claude returns a link that no agent found,
the system falls back to the rules automatically. Answers always contain only products from
the databases (FR-4, FR-13).

## 7. Run the tests

```powershell
.venv\Scripts\python -m pytest
```

There are 84 tests and none of them use the network. They cover routing, follow-ups and
clarifying questions, combined answers, partial failures, scraping and robots.txt, the daily
refresh, search, the budget solver, login and access control, history, the admin features
and response times. Test names refer to the test case IDs (TC-xx) in the requirements document.

## 8. Configuration (`.env`)

| Setting | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `none` | `none` = rule-based, `anthropic` = use Claude |
| `LLM_MODEL` | `claude-opus-5-5` | Claude model when `LLM_PROVIDER=anthropic` |
| `ANTHROPIC_API_KEY` | – | Needed only for Claude |
| `JWT_SECRET` | generated | Login token secret. If empty, a random one is saved in `data/.jwt_secret` |
| `TOKEN_HOURS` | `24` | How long a login lasts |
| `HOST`, `PORT` | `127.0.0.1`, `8000` | Web server address |
| `ENABLE_SCHEDULER` | `true` | Run the daily refresh while the server runs |
| `SCRAPE_HOUR`, `SCRAPE_MINUTE` | `0`, `0` | Time of the daily refresh |
| `TIMEZONE` | computer's zone | e.g. `Asia/Colombo` |
| `SCRAPE_ON_STARTUP` | `if_empty` | `if_empty`, `always` or `never` |
| `REQUEST_DELAY_SECONDS` | `1.0` | Minimum gap between requests to one site (robots.txt crawl-delay is also obeyed) |
| `AGENT_TIMEOUT_SECONDS` | `10` | Time limit per agent before its section says it couldn't be checked |
| `RESULTS_PER_CATEGORY` | `5` | Products shown per category |
| `HISTORY_CONTEXT_MESSAGES` | `10` | Messages of history used for follow-ups |

## 9. Websites each agent uses

Each agent's list is in [config/websites.yaml](config/websites.yaml) (FR-5). All sources are
practice sites or free demo data services made for this kind of project:

| Agent | Sources |
|---|---|
| Food | web-scraping.dev (HTML, consumables), dummyjson.com (groceries API) |
| Clothes | web-scraping.dev (HTML, apparel), dummyjson.com (shirts, shoes, dresses, tops), fakestoreapi.com (men's and women's clothing) |
| Electronics | webscraper.io test e-commerce site (HTML: laptops, tablets, phones), dummyjson.com (phones, laptops, tablets, accessories), fakestoreapi.com (electronics) |

The scrapers check every site's robots.txt (wildcards included), identify themselves with a
clear User-Agent, and wait at least 1 second between requests to the same site (2 seconds
for web-scraping.dev, as its robots.txt asks). scrapingcourse.com was dropped because its
robots.txt disallows `/ecommerce/*`. **Only text is stored: no images or image links** (FR-8).
Product photos on the website are looked up live from the source site when a product is shown
(one request returns all photo links for the API sources; HTML sites need one product-page
request) and are kept in memory only.

To add a site with one of the existing layouts, add an entry to `websites.yaml`; it is
scraped at the next refresh. A site with a new layout needs a parser in
`app/scrapers/parsers/`.

## 10. Project structure

```
Multi_Agent_System/
├── run.py                      # start the web server
├── requirements.txt / requirements-dev.txt
├── .env.example                # all settings with defaults
├── config/
│   ├── settings.py             # reads .env
│   └── websites.yaml           # website list for each agent
├── app/
│   ├── main.py                 # FastAPI app, scheduler start-up
│   ├── services.py             # builds and wires all components
│   ├── catalog_keywords.py     # product-type keywords per category
│   ├── text_utils.py
│   ├── api/                    # /api/chat, /api/me, product details, system status
│   ├── auth/                   # bcrypt + JWT, register/login/logout, role checks
│   ├── users/                  # users, admin routes, audit log
│   ├── history/                # conversations, messages, agent calls
│   ├── orchestrator/
│   │   ├── central_agent.py    # plan -> parallel agent calls -> combine -> save
│   │   ├── task_planner.py     # clarifications and follow-ups; uses Claude or the rules
│   │   ├── keyword_fallback.py # rule-based planner
│   │   ├── answer_combiner.py  # one reply with a section per category
│   │   ├── budget_solver.py    # shared budget across categories (CSP, backtracking)
│   │   └── prompts.py
│   ├── agents/                 # base agent + food, clothes, electronics agents
│   ├── scrapers/               # polite fetcher, robots.txt, parsers, live product photos (media.py)
│   ├── db/                     # SQLite schema, product repository (search), models
│   ├── scheduler/              # daily jobs, run_now command
│   └── llm/client.py           # optional Claude client with automatic fallback
├── frontend/                   # login, register, chat (with product panel), admin and
│                               # architecture.html (live "how it works" page)
├── scripts/create_admin.py
├── tests/                      # 84 automated tests
├── data/                       # databases (created at run time, not in git)
├── logs/                       # app.log
└── docs/                       # requirements and implementation specification (PDF)
```

## 11. API

All endpoints are under `/api`. Interactive documentation is at **http://127.0.0.1:8000/docs**.

| Method | Endpoint | Access |
|---|---|---|
| POST | `/api/auth/register`, `/api/auth/login` | Guest |
| POST | `/api/auth/logout` | Logged in |
| GET | `/api/me` | Logged in |
| POST | `/api/chat` `{conversation_id?, message}`: reply, product sections and the execution trace | Logged in |
| GET | `/api/products/{category}/{id}`, `/api/products/{category}/{id}/image` | Logged in |
| GET | `/api/system/status` (agents, product counts, refresh time) | Logged in |
| GET / DELETE | `/api/conversations`, `/api/conversations/{id}` | Owner |
| GET | `/api/admin/users?search=`, `/api/admin/users/{id}/conversations`, `/api/admin/conversations/{id}` | Admin (audited) |
| PATCH | `/api/admin/users/{id}` `{is_active}` | Admin |
| GET | `/api/admin/audit`, `/api/admin/sources` | Admin |
| POST | `/api/admin/refresh?agent=all` | Admin |
| GET | `/api/health` | Anyone |

## 12. Notes on the implementation

These are the points where the implementation fills in or adjusts details from the specification:

- **Open-question defaults:** agents don't talk to each other directly (OQ-1); deleting a
  conversation hides it from the customer, but admins still see it (OQ-2); admins can read
  histories and deactivate accounts (OQ-3); shared budgets are supported (FR-14, OQ-4).
- **"Show me cheaper ones"** returns products the customer hasn't been shown yet that cost
  less than the middle price of the products shown. "More" or "others" shows the next
  matches. "More expensive" works the same way upwards.
- **Data sources:** some sources are JSON demo APIs instead of HTML pages, because they
  allow automated access and give richer data. HTML scraping is still used for
  web-scraping.dev and webscraper.io.
- **Database access:** SQLite through Python's built-in `sqlite3` module (no SQLAlchemy needed).
- **Admin refresh:** admins can start a refresh from the dashboard, as well as with the
  `run_now` command.
- **Login token:** kept in the browser's localStorage for simplicity. A production system
  should use an HttpOnly cookie.

## 13. Troubleshooting

- **"No matching products" for everything:** the databases are empty. Run
  `.venv\Scripts\python -m app.scheduler.run_now` (needs internet).
- **A site shows `failed` in the admin dashboard:** the site was unreachable or changed. The
  agent keeps the previous data for that site, and the other sites still work. The error is
  shown when you hover over the status, and also in `logs/app.log`.
- **Port 8000 is busy:** set `PORT=8010` in `.env`.
- **Forgot the admin password:** run `scripts\create_admin.py` again with the same email.
- **Start from a clean state:** stop the server and delete the files in `data/` (keep `.gitkeep`).
