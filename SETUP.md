# Project Setup & Run Guide

This guide explains how to set up and run the Data Source Onboarding Agent from scratch on any system.

## Prerequisites
Make sure the system has the following installed:
1. **Python 3.11+**
2. **Node.js 18+** — builds the React front end, and runs the local embedded test
   database. Without it the server still starts and serves a fallback UI, but you
   will not get the React app.

---

## Step 1: Clone and Setup
First, move into the project directory and run the initialization script. This creates a sandboxed virtual environment (`.venv`), installs all Python dependencies, and builds the React front end into `frontend/dist`.

```bash
cd data-source-onboarding-agent
./bin/install.sh
```

## Step 2: Configure Environment Variables
Create an environment file at the root of the project to hold your API key.
```bash
touch .env
```
Inside the `.env` file, add your API key depending on which model you want to use. The backend supports both Gemini and Anthropic models:
```env
# For Gemini models (default: gemini-1.5-pro or gemini-2.5-flash)
GEMINI_API_KEY=your_gemini_api_key_here

# OR for Anthropic models (default: claude-3-5-sonnet-20241022)
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

*(Note: If you want to run the app in offline "Scripted Mode" for testing without an active API key, you can simply leave the `.env` file empty or leave out the `API_KEY` variable entirely. The scripted mode will use predefined responses for local testing!)*

## Step 3: Run the Web Server
```bash
npm run serve
```
This loads `.env`, builds the React front end if it has not been built yet, and
starts the API. Both come from the same process, so there is one URL and no CORS
setup: **http://localhost:8001**.

Prefer to drive uvicorn yourself? That works too — build the UI once first:
```bash
npm run ui:build
./.venv/bin/python -m uvicorn src.dsoa.api.main:app --port 8001 --env-file .env
```

### Working on the front end
```bash
npm run dev
```
Vite serves the UI with hot reload on **http://localhost:5173** and proxies
`/api` to uvicorn on `:8001`. Both processes stop when you stop the script.

---

## (Optional) Step 4: Setup the Local Test Database
If you want to test the connector generation against a real, locally hosted PostgreSQL database (like in the demo), you will need to start the embedded database using Node.js.

Open a second terminal window, stay in the project root, and run:
```bash
# Install the node dependencies
npm install

# Start the embedded Postgres test database
npm run up
```

In the web app, pick the first example (it points at this database), generate the
connector, then open the **Connection** tab and enter `dsoa` / `dsoa_local_dev`.
A successful test lists the three seeded tables.

That's it! The entire agent pipeline and test suite will be fully functional on the new system!
