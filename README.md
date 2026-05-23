# DBA / Data Roles -- Job Search Launchpad

A local Flask app: a job-search launchpad for DBA / data roles. Each card opens a
live, pre-filtered search on a job site, rebuilt from your current search term and
active location. Includes in-app controls to add/remove job types and locations
(country / state-province / city), plus an "Active leads" tab.

## Run

```
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5050

## Files

- `app.py` -- Flask backend + the launchpad page (HTML/CSS/JS)
- `config.json` -- saved state: job types, locations, search term, leads
- `requirements.txt` -- dependencies (Flask)
