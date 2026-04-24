# JobRight Feed

A live job recommendation viewer backed by the JobRight scraper.

Backend: FastAPI + Playwright on Render (Docker)
Frontend: Next.js on Vercel

---

## Structure

```
jobright-web/
  backend/      FastAPI app (deploy to Render)
  frontend/     Next.js app (deploy to Vercel)
```

---

## Step 1: Prepare your session file

Run the login flow from your original repo to generate a fresh `jobright_state.json`:

```
python jobright_scrape.py --login
```

Copy `jobright_state.json` into the `backend/` folder:

```
cp /path/to/jobright_state.json backend/jobright_state.json
```

This file gets baked into the Docker image at build time.

---

## Step 2: Deploy the backend to Render

1. Push the entire `jobright-web/` folder to a new GitHub repo (or add it as a subfolder of your existing one).

2. Go to https://render.com and create a free account.

3. Click "New" > "Web Service".

4. Connect your GitHub repo. Set the root directory to `backend`.

5. Choose "Docker" as the runtime. Render will detect the Dockerfile automatically.

6. Set instance type to "Free".

7. Click "Create Web Service". Wait for the build (5-10 min first time, Playwright is large).

8. Once deployed, copy your Render URL (e.g. `https://jobright-backend.onrender.com`).

Note: the free tier spins down after 15 minutes of inactivity. The first request after sleep takes ~30 seconds to wake up. This is fine for a demo.

---

## Step 3: Deploy the frontend to Vercel

1. Go to https://vercel.com and create a free account.

2. Click "Add New" > "Project". Import your GitHub repo.

3. Set the root directory to `frontend`.

4. Under "Environment Variables", add:
   - Key: `NEXT_PUBLIC_API_URL`
   - Value: your Render URL from step 2 (no trailing slash)

5. Click "Deploy".

6. Once deployed, Vercel gives you a public URL to share with recruiters.

---

## Refreshing your session

Session cookies eventually expire (typically 30-90 days). When the scraper starts returning 401 errors:

1. Run `python jobright_scrape.py --login` locally to get a fresh `jobright_state.json`.
2. Copy it back into `backend/`.
3. Push to GitHub. Render will auto-redeploy.

---

## Local development

Backend:
```
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn main:app --reload
```

Frontend:
```
cd frontend
npm install
cp .env.example .env.local
# edit .env.local and set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```
