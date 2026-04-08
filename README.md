# 🎒 Smart Lost & Found System

Zero-dependency Python web app — runs with **plain Python 3.8+**, no pip install needed.

---

## ✅ Requirements

- Python 3.8 or higher (check: `python --version`)
- That's it. No pip, no virtual environment, no extra packages.

---

## 🚀 How to Run (VS Code / Terminal)

### Step 1 — Open the project folder
```
File → Open Folder → select smart-lost-found/
```

### Step 2 — Open terminal in VS Code
```
Terminal → New Terminal
```

### Step 3 — Start the server
```bash
python server.py
```

You should see:
```
╔══════════════════════════════════════════════════════╗
║       Smart Lost & Found System  v2.0               ║
╠══════════════════════════════════════════════════════╣
║  Frontend  →  http://localhost:8000                  ║
║  API Info  →  http://localhost:8000/api              ║
╠══════════════════════════════════════════════════════╣
║  Admin login:  admin@lostfound.com / admin123       ║
╚══════════════════════════════════════════════════════╝
```

### Step 4 — Open in browser
```
http://localhost:8000
```

### Stop the server
Press `Ctrl + C` in the terminal.

---

## 🔐 Default Admin Account

| Field    | Value                 |
|----------|-----------------------|
| Email    | admin@lostfound.com   |
| Password | admin123              |

---

## 📁 Project Structure

```
smart-lost-found/
├── server.py          ← The entire backend (single file, zero deps)
├── frontend/
│   └── index.html     ← The entire frontend (single file)
├── uploads/           ← Auto-created for image uploads
├── lostfound.db       ← Auto-created SQLite database
└── README.md
```

---

## ✨ Features

| Feature | Description |
|---|---|
| Register / Login | JWT-based auth (built-in, no library) |
| Report Lost Item | Name, description, category, location, date, image |
| Report Found Item | Same fields |
| Browse & Search | Keyword + category filter |
| Smart Matching | Jaccard similarity on name + description + category |
| Query / Ticket System | Users raise queries, admin responds |
| Admin Dashboard | Analytics, status updates, query responses |

---

## 🔗 API Endpoints

Visit `http://localhost:8000/api` for the full list.

| Method | URL | Description |
|--------|-----|-------------|
| POST | /register | Register new user |
| POST | /login | Login → JWT token |
| GET | /me | Current user info |
| POST | /report-lost | Report lost item |
| POST | /report-found | Report found item |
| GET | /items/lost | All lost items |
| GET | /items/found | All found items |
| GET | /search | Search/filter items |
| GET | /match/{id} | Smart match for lost item |
| POST | /query | Raise a query |
| GET | /queries | My queries |
| GET | /admin/analytics | Dashboard stats |
| PUT | /admin/update-status | Update item status |
| POST | /admin/respond-query | Admin reply to query |

---

## 🧠 Smart Matching Algorithm

Compares a lost item against all found items using:

- **Name similarity** — Jaccard word overlap (45% weight)
- **Description keywords** — Jaccard word overlap (35% weight)  
- **Category match** — Exact/partial match (20% weight)

Returns matches sorted by score (0–100%) with human-readable reasons.

---

## 📊 Agile Sprint Plan

| Sprint | Goal |
|--------|------|
| 1 | Project setup + JWT auth |
| 2 | Lost/Found item reporting |
| 3 | Admin dashboard |
| 4 | Query/ticket system |
| 5 | Smart matching algorithm |
| 6 | Frontend UI + testing |

create a uploads folder after pulling the repository to save the uploaded database
