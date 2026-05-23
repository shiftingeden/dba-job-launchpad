#!/usr/bin/env python3
"""
DBA / Data Roles -- Job Search Launchpad (Flask edition)
========================================================

A local web app that recreates the "DBA Job Launchpad" with the same visuals,
plus in-app controls to:
  * add / remove job types (the search-term presets)
  * add / remove locations (country / state-province / city)

The chosen location rebuilds every job-site search link live.

HOW TO RUN
----------
    pip install -r requirements.txt
    python app.py

then open the URL it prints (http://127.0.0.1:5050) in your browser.

All editable state is persisted to config.json next to this file, so your
job types, locations and checkmarks survive restarts.
"""

import json
import os
import signal
import subprocess
import time
import uuid

from flask import Flask, request, jsonify, render_template_string

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

app = Flask(__name__)

# ---------------------------------------------------------------------------
# SITE CATALOG
# ---------------------------------------------------------------------------
# Each card has: name, badge (css class), label, desc, tpl (URL template),
# and an optional noCount flag (recruiter pages have no "new" count pill).
#
# URL template placeholders -- substituted in the browser so the term stays
# live as you type, and the active location is baked in on page load:
#   {Q}          encoded search term          {S}            term slug
#   {CITY}       raw city                     {CITY_ENC}     encoded city
#   {CITY_SLUG}  hyphen-slug city
#   {STATE}      raw state/province           {STATE_ENC}    encoded state
#   {STATE_SLUG} hyphen-slug state
#   {COUNTRY}    raw country                  {COUNTRY_ENC}  encoded country
# ---------------------------------------------------------------------------
SITES = {
    "onsite-aggr": [
        {
            "name": "Job Bank (Government of Canada)", "badge": "b-gov", "label": "Gov",
            "desc": "Federal board carrying public-sector and private postings, with strong location filtering.",
            "tpl": "https://www.jobbank.gc.ca/jobsearch/jobsearch?searchstring={Q}&locationstring={CITY_ENC}",
        },
        {
            "name": "Eluta.ca", "badge": "b-aggr", "label": "Aggregator",
            "desc": "Indexes postings straight from employers' own career pages -- catches roles the big boards miss.",
            "tpl": "https://www.eluta.ca/search?q={Q}&l={CITY_ENC}+{STATE_ENC}",
        },
    ],
    "onsite-board": [
        {
            "name": "Jobillico", "badge": "b-board", "label": "Job board",
            "desc": "Large regional board, pre-filtered to the active city. Also try the local-language term.",
            "tpl": "https://www.jobillico.com/search-jobs/{S}/{CITY_SLUG}/{STATE_SLUG}",
        },
        {
            "name": "Jobboom", "badge": "b-board", "label": "Job board",
            "desc": "Established Quebec board, French-first; pre-filtered to the active city.",
            "tpl": "https://www.jobboom.com/en/jobs?keywords={Q}&where={CITY_ENC}",
        },
        {
            "name": "Workhoppers", "badge": "b-board", "label": "Job board",
            "desc": "Local board with contract and flexible IT listings for the active city.",
            "tpl": "https://www.workhoppers.com/en/jobs/{CITY_SLUG}?keywords={Q}",
        },
    ],
    "onsite-recruit": [
        {
            "name": "Robert Half Technology", "badge": "b-recruit", "label": "Recruiter",
            "desc": "Major staffing firm; many contract/perm data roles run through them.",
            "tpl": "https://www.roberthalf.com/ca/en/jobs?keyword={Q}&location={CITY_ENC}%2C+{STATE_ENC}",
            "noCount": True,
        },
        {
            "name": "S.i. Systems", "badge": "b-recruit", "label": "Recruiter",
            "desc": "Canadian IT staffing agency, frequent DBA / data contracts.",
            "tpl": "https://www.sisystems.com/search-jobs/?keyword={Q}",
            "noCount": True,
        },
        {
            "name": "Akkodis (formerly Modis)", "badge": "b-recruit", "label": "Recruiter",
            "desc": "Global tech recruiter actively placing senior data professionals.",
            "tpl": "https://www.akkodis.com/en-ca/jobs?query={Q}&location={CITY_ENC}",
            "noCount": True,
        },
        {
            "name": "Fed IT (Groupe Fed)", "badge": "b-recruit", "label": "Recruiter",
            "desc": "IT recruitment specialist with recurring database postings.",
            "tpl": "https://www.fed-it.ca/en/it-jobs/?s={Q}",
            "noCount": True,
        },
        {
            "name": "Procom", "badge": "b-recruit", "label": "Recruiter",
            "desc": "Large Canadian IT contracting firm with a steady contract flow.",
            "tpl": "https://www.procom.ca/job-search/?keywords={Q}&location={CITY_ENC}",
            "noCount": True,
        },
        {
            "name": "Kovasys IT Recruitment", "badge": "b-recruit", "label": "Recruiter",
            "desc": "IT recruiter -- worth sending a resume to even when nothing is posted.",
            "tpl": "https://kovasys.com/it-jobs/",
            "noCount": True,
        },
    ],
    "remote-board": [
        {
            "name": "We Work Remotely", "badge": "b-board", "label": "Remote board",
            "desc": "One of the largest remote-only boards. Confirm your country is in scope per posting.",
            "tpl": "https://weworkremotely.com/remote-jobs/search?term={Q}",
        },
        {
            "name": "Jobgether", "badge": "b-aggr", "label": "Remote aggregator",
            "desc": "Aggregates fully-remote roles; filter by region.",
            "tpl": "https://jobgether.com/remote-jobs/{S}",
        },
        {
            "name": "Remote Rocketship", "badge": "b-board", "label": "Remote board",
            "desc": "Remote roles; flags location restrictions per posting.",
            "tpl": "https://www.remoterocketship.com/jobs/{S}/",
        },
        {
            "name": "Working Nomads", "badge": "b-board", "label": "Remote board",
            "desc": "Curated remote listings. Confirm the role is open to your country.",
            "tpl": "https://www.workingnomads.com/remote-jobs?search={Q}",
        },
        {
            "name": "Built In", "badge": "b-board", "label": "Remote board",
            "desc": "Tech-company board with a remote Data/Analytics filter -- catches SaaS roles.",
            "tpl": "https://builtin.com/jobs/remote/data-analytics/search/{S}",
        },
        {
            "name": "DailyRemote", "badge": "b-board", "label": "Remote board",
            "desc": "Remote listings aggregated from multiple sources.",
            "tpl": "https://dailyremote.com/remote-jobs?search={Q}",
        },
    ],
    "remote-aggr": [
        {
            "name": "Job Bank -- remote filter", "badge": "b-gov", "label": "Gov",
            "desc": "Teleworkable filter on for nationwide postings -- read the body to exclude hybrid.",
            "tpl": "https://www.jobbank.gc.ca/jobsearch/jobsearch?searchstring={Q}&fteleworkable=true&sort=D",
        },
        {
            "name": "Eluta.ca -- nationwide", "badge": "b-aggr", "label": "Aggregator",
            "desc": "Employer-page aggregator; nationwide search -- scan for fully-remote.",
            "tpl": "https://www.eluta.ca/search?q={Q}",
        },
    ],
    # Canadian "Big Six" bank career sites -- apply direct. These are nationwide
    # employer portals, so they take only the search term ({Q}); filter location
    # on the bank's own site. Like recruiters, they are not lead-counted.
    "bank-direct": [
        {
            "name": "RBC -- Royal Bank of Canada", "badge": "b-bank", "label": "Bank",
            "desc": "Canada's largest bank. Searches data, technology and DBA roles on RBC's careers site.",
            "tpl": "https://jobs.rbc.com/ca/en/search-results?keywords={Q}",
            "noCount": True,
        },
        {
            "name": "TD -- Toronto-Dominion Bank", "badge": "b-bank", "label": "Bank",
            "desc": "Major data and technology employer; searches TD's careers portal.",
            "tpl": "https://jobs.td.com/en/job-search-results/?keywords={Q}",
            "noCount": True,
        },
        {
            "name": "Scotiabank -- Bank of Nova Scotia", "badge": "b-bank", "label": "Bank",
            "desc": "Searches Scotiabank's global careers portal for data and database roles.",
            "tpl": "https://jobs.scotiabank.com/search/?q={Q}",
            "noCount": True,
        },
        {
            "name": "BMO -- Bank of Montreal", "badge": "b-bank", "label": "Bank",
            "desc": "Digital-first bank investing in data and AI; searches BMO's Canadian careers site.",
            "tpl": "https://jobs.bmo.com/ca/en/search-results?keywords={Q}",
            "noCount": True,
        },
        {
            "name": "CIBC -- Canadian Imperial Bank of Commerce", "badge": "b-bank", "label": "Bank",
            "desc": "Searches CIBC's Workday careers portal across all divisions.",
            "tpl": "https://cibc.wd3.myworkdayjobs.com/search?q={Q}",
            "noCount": True,
        },
        {
            "name": "National Bank of Canada", "badge": "b-bank", "label": "Bank",
            "desc": "Montreal-headquartered Big Six bank; searches National Bank's careers site.",
            "tpl": "https://emplois.bnc.ca/en_CA/careers/SearchJobs/?keyword={Q}",
            "noCount": True,
        },
    ],
}

# ---------------------------------------------------------------------------
# DEFAULT CONFIG (written to config.json on first run)
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "term": "SQL Server DBA",
    "job_types": [
        "SQL Server DBA", "Database Administrator", "Data Engineer",
        "SQL Developer", "Data Architect",
    ],
    "locations": [
        {"id": "loc-montreal", "country": "Canada", "state": "Quebec", "city": "Montreal"},
    ],
    "active_location": "loc-montreal",
    "last_scan": "Fri May 22, 2026",
    "leads": {
        "leads-onsite": [
            {
                "name": "National Bank -- Oracle Application Database Administrator (DBA)",
                "src": "onsite-board-0", "firstSeen": "Thu May 21, 2026",
                "desc": "Senior DBA specialist on National Bank's Master Data Profile team, Montreal on-site; manages and optimizes database environments across Unix/Linux and Windows. Posted on Jobillico.",
                "url": "https://www.jobillico.com/en/job-offer/national-bank/oracle-application-database-administrator-dba-/16517994",
            },
            {
                "name": "CONSULTATION ISGA INC. -- DBA, 1 Place Ville Marie",
                "src": "onsite-aggr-0", "firstSeen": "Thu May 21, 2026",
                "desc": "Montreal DBA posting on Job Bank, surfaced with an application deadline of May 29, 2026 -- time-sensitive, verify and apply soon if it fits.",
                "url": "https://www.jobbank.gc.ca/jobsearch/jobposting/49046313",
            },
            {
                "name": "Services Conseils IntelliSoft -- Senior SQL Server DBA",
                "src": "onsite-aggr-1", "firstSeen": "Thu May 21, 2026",
                "desc": "Senior SQL Server DBA in Montreal; salary cited around $53K-$100K. Confirm it is still posted.",
                "url": "https://www.eluta.ca/search?q=SQL%20Server%20DBA&l=Montreal+QC",
            },
            {
                "name": "Akkodis -- Senior Database Administrator (SQL Server / Oracle)",
                "src": None, "firstSeen": "Thu May 21, 2026",
                "desc": "Senior DBA managing MS SQL Server and/or Oracle environments, full-time, Montreal.",
                "url": "https://www.akkodis.com/en-ca/jobs?query=database%20administrator&location=Montreal",
            },
            {
                "name": "Groupe Fed (Fed IT) -- Database Administrator",
                "src": "onsite-board-0", "firstSeen": "Thu May 21, 2026",
                "desc": "Montreal DBA role: MS SQL Server multi-server environments, T-SQL / SSIS / SSRS / SSMS.",
                "url": "https://www.jobillico.com/en/job-offer/fed-it-dszhrq/database-administrator/11371758",
            },
            {
                "name": "Renaps Technology Canada -- DBA, Centre of Excellence",
                "src": "onsite-aggr-1", "firstSeen": "Thu May 21, 2026",
                "desc": "Database Administrator joining Renaps' Centre of Excellence team in Montreal.",
                "url": "https://www.eluta.ca/search?q=database%20administrator&l=Montreal+QC",
            },
            {
                "name": "Intact Financial -- Database Administrator",
                "src": None, "firstSeen": "Thu May 21, 2026",
                "desc": "DBA openings in Montreal at Intact -- check their career site for current SQL Server roles.",
                "url": "https://careers.intact.ca/ca/en/search-results?keywords=database%20administrator",
            },
        ],
        "leads-remote": [
            {
                "name": "PointClickCare -- Sr. MS SQL Database Administrator",
                "src": "remote-board-4", "firstSeen": "Thu May 21, 2026",
                "desc": "Senior MSSQL DBA for a Canadian healthcare-SaaS company (HQ Mississauga, ON); posting is listed remote and is carried on Canadian job boards -- confirmed Canada-eligible. Strong SQL Server match.",
                "url": "https://builtin.com/job/senior-ms-sql-dba/2129862",
            },
            {
                "name": "CMHC -- Senior Specialist, Database Administrator (SQL Server / Azure SQL)",
                "src": "remote-aggr-0", "firstSeen": "Thu May 21, 2026",
                "desc": "Canadian crown corporation with senior SQL Server / Azure SQL DBA postings on Job Bank. Canada-eligible, but Ottawa-based government roles are typically hybrid -- confirm it is fully remote before treating it as a pure remote lead.",
                "url": "https://www.jobbank.gc.ca/jobsearch/jobposting/49378553",
            },
            {
                "name": "Fleetio -- Senior Database Administrator (DBA)",
                "src": "remote-board-0", "firstSeen": "Fri May 22, 2026",
                "desc": "Senior DBA at a fleet-management SaaS, posted on We Work Remotely. Fully remote and explicitly open to candidates in Canada (US / Canada / Mexico) -- confirmed not hybrid; 80%+ of engineering is remote.",
                "url": "https://weworkremotely.com/remote-jobs/fleetio-senior-database-administrator-dba",
            },
        ],
    },
}


# ---------------------------------------------------------------------------
# CONFIG PERSISTENCE
# ---------------------------------------------------------------------------
def load_config():
    """Load config.json, creating it from defaults if missing/corrupt."""
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (json.JSONDecodeError, OSError):
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    # backfill any missing top-level keys
    for key, val in DEFAULT_CONFIG.items():
        cfg.setdefault(key, json.loads(json.dumps(val)))
    if not cfg["locations"]:
        cfg["locations"] = json.loads(json.dumps(DEFAULT_CONFIG["locations"]))
    if not any(l["id"] == cfg.get("active_location") for l in cfg["locations"]):
        cfg["active_location"] = cfg["locations"][0]["id"]
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)


def active_location(cfg):
    for loc in cfg["locations"]:
        if loc["id"] == cfg.get("active_location"):
            return loc
    return cfg["locations"][0]


# ---------------------------------------------------------------------------
# ROUTES -- PAGE
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    cfg = load_config()
    return render_template_string(
        TEMPLATE, cfg=cfg, sites=SITES, active=active_location(cfg)
    )


# ---------------------------------------------------------------------------
# ROUTES -- JOB TYPES
# ---------------------------------------------------------------------------
@app.route("/api/job-types/add", methods=["POST"])
def add_job_type():
    cfg = load_config()
    name = ((request.get_json(silent=True) or {}).get("name") or "").strip()
    if not name:
        return jsonify(ok=False, error="Enter a job type."), 400
    if name.lower() not in [j.lower() for j in cfg["job_types"]]:
        cfg["job_types"].append(name)
        save_config(cfg)
    return jsonify(ok=True)


@app.route("/api/job-types/delete", methods=["POST"])
def delete_job_type():
    cfg = load_config()
    name = ((request.get_json(silent=True) or {}).get("name") or "").strip()
    cfg["job_types"] = [j for j in cfg["job_types"] if j.lower() != name.lower()]
    save_config(cfg)
    return jsonify(ok=True)


# ---------------------------------------------------------------------------
# ROUTES -- LOCATIONS
# ---------------------------------------------------------------------------
@app.route("/api/locations/add", methods=["POST"])
def add_location():
    cfg = load_config()
    data = request.get_json(silent=True) or {}
    country = (data.get("country") or "").strip()
    state = (data.get("state") or "").strip()
    city = (data.get("city") or "").strip()
    if not (country or state or city):
        return jsonify(ok=False, error="Enter at least a country, state/province or city."), 400
    loc = {
        "id": "loc-" + uuid.uuid4().hex[:8],
        "country": country, "state": state, "city": city,
    }
    cfg["locations"].append(loc)
    cfg["active_location"] = loc["id"]  # new location becomes active
    save_config(cfg)
    return jsonify(ok=True, id=loc["id"])


@app.route("/api/locations/delete", methods=["POST"])
def delete_location():
    cfg = load_config()
    loc_id = (request.get_json(silent=True) or {}).get("id")
    if len(cfg["locations"]) <= 1:
        return jsonify(ok=False, error="Keep at least one location."), 400
    cfg["locations"] = [l for l in cfg["locations"] if l["id"] != loc_id]
    if cfg["active_location"] == loc_id:
        cfg["active_location"] = cfg["locations"][0]["id"]
    save_config(cfg)
    return jsonify(ok=True)


@app.route("/api/locations/active", methods=["POST"])
def set_active_location():
    cfg = load_config()
    loc_id = (request.get_json(silent=True) or {}).get("id")
    if any(l["id"] == loc_id for l in cfg["locations"]):
        cfg["active_location"] = loc_id
        save_config(cfg)
        return jsonify(ok=True)
    return jsonify(ok=False, error="Unknown location."), 400


# ---------------------------------------------------------------------------
# ROUTES -- SEARCH TERM
# ---------------------------------------------------------------------------
@app.route("/api/term", methods=["POST"])
def set_term():
    cfg = load_config()
    term = ((request.get_json(silent=True) or {}).get("term") or "").strip()
    if term:
        cfg["term"] = term
        save_config(cfg)
    return jsonify(ok=True)


# ---------------------------------------------------------------------------
# HTML TEMPLATE  (visuals ported verbatim from the original launchpad artifact)
# ---------------------------------------------------------------------------
TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DBA / Data Roles -- Job Search Launchpad</title>
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #f6f7f9; color: #1c2024; line-height: 1.5;
    padding: 20px; -webkit-font-smoothing: antialiased;
  }
  .wrap { max-width: 880px; margin: 0 auto; }
  header { margin-bottom: 6px; }
  h1 { font-size: 22px; font-weight: 700; letter-spacing: -0.01em; }
  .sub { color: #5b6168; font-size: 13px; margin-top: 4px; }

  /* search-term + location controls */
  .term-box {
    background: #fff; border: 1px solid #e3e6e9; border-radius: 10px;
    padding: 13px 14px; margin: 14px 0 12px;
  }
  .term-label { font-size: 12px; font-weight: 700; color: #3c4248; margin-bottom: 8px; }
  .term-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .term-row input, .loc-row select {
    flex: 1; min-width: 200px; font-size: 14px; padding: 8px 11px;
    border: 1px solid #c4c9cf; border-radius: 7px; color: #1c2024; background: #fff;
  }
  .term-row input:focus, .loc-row select:focus,
  .addrow input:focus, .loc-add input:focus { outline: 2px solid #1a5c9c; outline-offset: -1px; }
  .presets { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 9px; }
  .preset {
    display: inline-flex; align-items: center; gap: 5px;
    border: 1px solid #d4d8dd; background: #f6f7f9; color: #3c4248;
    padding: 4px 8px 4px 10px; border-radius: 999px; font-size: 11.5px;
  }
  .preset .lbl { cursor: pointer; }
  .preset:hover { border-color: #9aa0a8; }
  .preset.on { background: #1c2024; color: #fff; border-color: #1c2024; }
  .preset .x {
    cursor: pointer; font-weight: 700; font-size: 13px; line-height: 1;
    color: #9aa0a8; padding: 0 1px;
  }
  .preset .x:hover { color: #c0392b; }
  .preset.on .x { color: #9aa0a8; }
  .preset.on .x:hover { color: #ff8a7a; }

  .addrow { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 9px; }
  .addrow input {
    flex: 1; min-width: 160px; font-size: 12.5px; padding: 7px 10px;
    border: 1px solid #c4c9cf; border-radius: 6px; color: #1c2024;
  }
  .btn {
    background: #1c2024; color: #fff; border: none; cursor: pointer;
    padding: 7px 13px; border-radius: 6px; font-size: 12px; font-weight: 600;
  }
  .btn:hover { background: #34393f; }
  .btn.ghost { background: #fff; color: #3c4248; border: 1px solid #d4d8dd; }
  .btn.ghost:hover { border-color: #9aa0a8; background: #f6f7f9; }

  .loc-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  details.loc-add-wrap { margin-top: 10px; }
  details.loc-add-wrap summary {
    cursor: pointer; font-size: 12px; color: #1a5c9c; font-weight: 600;
    list-style: none; width: fit-content;
  }
  details.loc-add-wrap summary::-webkit-details-marker { display: none; }
  details.loc-add-wrap summary::before { content: "+ "; }
  details.loc-add-wrap[open] summary::before { content: "- "; }
  .loc-add { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 9px; }
  .loc-add input {
    flex: 1; min-width: 130px; font-size: 12.5px; padding: 7px 10px;
    border: 1px solid #c4c9cf; border-radius: 6px; color: #1c2024;
  }
  .ctrl-hint { font-size: 11px; color: #8a9098; margin-top: 8px; }

  .statusbar {
    display: flex; gap: 6px 16px; flex-wrap: wrap; font-size: 11.5px;
    color: #6b7178; margin-bottom: 16px;
  }
  .statusbar b { color: #3c4248; font-weight: 600; }
  .dot { width: 7px; height: 7px; border-radius: 50%; background: #2e9e5b;
    display: inline-block; margin-right: 4px; vertical-align: middle; }

  .note {
    background: #fff8e6; border: 1px solid #f0d98a; border-radius: 8px;
    padding: 11px 13px; font-size: 12.5px; color: #6b5618; margin-bottom: 16px;
  }
  .note strong { color: #5a4810; }

  .tabs { display: flex; gap: 6px; margin-bottom: 16px; flex-wrap: wrap; }
  .tab {
    border: 1px solid #d4d8dd; background: #fff; color: #3c4248;
    padding: 7px 14px; border-radius: 999px; font-size: 13px; cursor: pointer;
    font-weight: 500; transition: all .12s;
  }
  .tab:hover { border-color: #9aa0a8; }
  .tab.active { background: #1c2024; color: #fff; border-color: #1c2024; }
  .cnt { opacity: .6; font-size: 11px; }
  .cnt.hasnew {
    opacity: 1; font-weight: 700; color: #fff; background: #2e9e5b;
    padding: 1px 7px; border-radius: 999px; font-size: 10.5px;
  }
  .tab.active .cnt.hasnew { color: #fff; }
  .refresh-btn {
    margin-left: auto; border: 1px solid #1a5c9c; background: #fff; color: #1a5c9c;
    padding: 7px 15px; border-radius: 999px; font-size: 13px; font-weight: 600;
    cursor: pointer; transition: all .12s;
  }
  .refresh-btn:hover { background: #1a5c9c; color: #fff; }

  .panel { display: none; }
  .panel.active { display: block; }

  .grp-label {
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em;
    color: #8a9098; margin: 18px 0 9px;
  }
  .grp-label:first-child { margin-top: 0; }
  .empty-msg { font-size: 12.5px; color: #8a9098; font-style: italic; margin-bottom: 6px; }

  .card {
    background: #fff; border: 1px solid #e3e6e9; border-radius: 10px;
    padding: 13px 14px; margin-bottom: 9px; display: flex; gap: 12px; align-items: flex-start;
  }
  .card.done { opacity: .55; }
  .card.isnew { border-color: #9bd3b2; box-shadow: 0 0 0 2px #e4f4ea; }
  .chk { width: 18px; height: 18px; margin-top: 2px; flex-shrink: 0; cursor: pointer; accent-color: #1c2024; }
  .body { flex: 1; min-width: 0; }
  .row1 { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
  .name { font-size: 14.5px; font-weight: 650; }
  .badge {
    font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
    padding: 2px 7px; border-radius: 4px;
  }
  .b-gov { background: #e3effa; color: #1a5c9c; }
  .b-aggr { background: #eae6fa; color: #5a3fb0; }
  .b-board { background: #e4f4ea; color: #1f7a4d; }
  .b-recruit { background: #fae6ef; color: #a8326f; }
  .b-lead { background: #fde8da; color: #b8540f; }
  .b-bank { background: #def0ef; color: #0f6b66; }
  .tag-new { background: #2e9e5b; color: #fff; }
  .desc { font-size: 12.5px; color: #565c63; margin-top: 4px; }
  .meta { font-size: 11px; color: #8a9098; margin-top: 5px; }
  .actions { margin-top: 8px; }
  a.open { font-size: 12.5px; font-weight: 600; color: #1a5c9c; text-decoration: none; }
  a.open:hover { text-decoration: underline; }

  /* count pill */
  .countcol { flex-shrink: 0; text-align: center; min-width: 54px; }
  .pill {
    display: inline-block; min-width: 38px; padding: 5px 8px; border-radius: 8px;
    background: #f0f2f4; border: 1px solid #e3e6e9;
  }
  .pill.live { background: #e4f4ea; border-color: #9bd3b2; }
  .pill .num { font-size: 16px; font-weight: 700; color: #1c2024; line-height: 1; }
  .pill .num.empty { color: #b4b9bf; }
  .pill.live .num { color: #1f7a4d; }
  .pill .lbl { font-size: 8.5px; text-transform: uppercase; letter-spacing: .04em;
    color: #8a9098; margin-top: 2px; }

  footer {
    margin-top: 22px; padding-top: 14px; border-top: 1px solid #e3e6e9;
    font-size: 12px; color: #6b7178;
  }
  footer h3 { font-size: 12.5px; color: #3c4248; margin: 12px 0 6px; }
  footer ul { margin: 0 0 6px 18px; }
  footer li { margin-bottom: 3px; }
  .reset {
    background: none; border: 1px solid #d4d8dd; color: #6b7178;
    font-size: 11px; padding: 4px 10px; border-radius: 6px; cursor: pointer; margin-top: 8px;
  }
  .reset:hover { border-color: #9aa0a8; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>DBA / Data Roles -- Job Search Launchpad</h1>
    <div class="sub">On-site &amp; fully-remote roles, focused on channels beyond Indeed / Glassdoor / LinkedIn.</div>
  </header>

  <!-- ===== search term ===== -->
  <div class="term-box">
    <div class="term-label">What are you searching for?</div>
    <div class="term-row">
      <input id="term" type="text" placeholder="e.g. SQL Server DBA" autocomplete="off">
    </div>
    <div class="presets" id="presets"></div>
    <div class="addrow">
      <input id="addType" type="text" placeholder="Add a job type (e.g. Data Analyst)" autocomplete="off">
      <button class="btn" id="addTypeBtn">Add type</button>
    </div>
    <div class="ctrl-hint">
      Editing the box rebuilds every &ldquo;Open search&rdquo; link below. Click a chip to use it;
      click its &times; to remove it. Job types are saved on the server.
    </div>
  </div>

  <!-- ===== location ===== -->
  <div class="term-box">
    <div class="term-label">Where are you searching?</div>
    <div class="loc-row">
      <select id="locSelect">
        {% for l in cfg.locations %}
        <option value="{{ l.id }}" {% if l.id == cfg.active_location %}selected{% endif %}>
          {{ [l.city, l.state, l.country] | select | join(', ') }}
        </option>
        {% endfor %}
      </select>
      <button class="btn ghost" id="locRemove">Remove this location</button>
    </div>
    <details class="loc-add-wrap">
      <summary>Add a location</summary>
      <div class="loc-add">
        <input id="addCountry" type="text" placeholder="Country" autocomplete="off">
        <input id="addState" type="text" placeholder="State / Province" autocomplete="off">
        <input id="addCity" type="text" placeholder="City" autocomplete="off">
        <button class="btn" id="addLocBtn">Add</button>
      </div>
      <div class="ctrl-hint">
        Selecting a location rebuilds the city/state-aware search links. At least one
        field is required; the new location becomes active automatically.
      </div>
    </details>
  </div>

  <div class="statusbar">
    <span><b>Active location:</b> <span id="locName"></span></span>
    <span><b>Leads last refreshed:</b> {{ cfg.last_scan or 'pending first scan' }}</span>
    <span><span class="dot"></span><b>Job types:</b> <span id="jtCount"></span></span>
  </div>

  <div class="note">
    <strong>How to use this:</strong> set your search term and location above; each card opens a
    <em>live, pre-filtered search</em> on that site. The count pill shows how many leads in the
    &ldquo;Active leads&rdquo; tab were found via that site on the latest refresh. Use
    <strong>Add type</strong> / the chip &times; to manage job types, and the location box to add
    countries, states/provinces and cities. Verify a role is still open, the right level, and
    (for remote roles) actually open to candidates in your country before applying.
    Checkmarks save on this device.
  </div>

  <div class="tabs">
    <button class="tab active" data-panel="onsite">On-site <span class="cnt" id="c-onsite"></span></button>
    <button class="tab" data-panel="remote">Remote <span class="cnt" id="c-remote"></span></button>
    <button class="tab" data-panel="banks">Big Six banks</button>
    <button class="tab" data-panel="leads">Active leads <span class="cnt" id="c-leads"></span></button>
    <button class="refresh-btn" id="rerun" title="Reload the page and rebuild every search link">&#8635; Re-run</button>
  </div>

  <div class="panel active" id="onsite">
    <div class="grp-label">Government &amp; employer-page aggregators</div>
    <div id="onsite-aggr"></div>
    <div class="grp-label">Regional job boards</div>
    <div id="onsite-board"></div>
    <div class="grp-label">Specialist IT recruiters (many roles never get posted publicly)</div>
    <div id="onsite-recruit"></div>
  </div>

  <div class="panel" id="remote">
    <div class="grp-label">Remote-only job boards</div>
    <div id="remote-board"></div>
    <div class="grp-label">Government &amp; aggregators (filter for remote)</div>
    <div id="remote-aggr"></div>
  </div>

  <div class="panel" id="banks">
    <div class="grp-label">Canadian &ldquo;Big Six&rdquo; bank career sites &mdash; apply direct</div>
    <div id="bank-direct"></div>
  </div>

  <div class="panel" id="leads">
    <div class="grp-label">On-site openings to verify</div>
    <div id="leads-onsite"></div>
    <div class="grp-label">Remote openings to verify</div>
    <div id="leads-remote"></div>
  </div>

  <footer>
    <h3>About this launchpad</h3>
    <ul>
      <li>This is a self-contained Flask app. Your job types, locations and search term are saved to <strong>config.json</strong> next to <code>app.py</code>.</li>
      <li>Each card opens a <strong>live, pre-filtered search</strong> built from your current term and active location.</li>
      <li>The <strong>Active leads</strong> tab lists specific openings; each shows the date it was first seen. The green &ldquo;new&rdquo; tag and count pills mark leads from the most recent refresh.</li>
      <li>To wire automatic weekday scanning into this app, or add more job sites for other countries, just ask Claude.</li>
    </ul>
    <h3>Search tips for this role</h3>
    <ul>
      <li><strong>Filter out hybrid:</strong> many boards lump &ldquo;remote&rdquo; and &ldquo;hybrid&rdquo; together -- read the posting body. Quebec employers often label hybrid as &ldquo;t&eacute;l&eacute;travail hybride.&rdquo;</li>
      <li><strong>Confirm your country is in scope:</strong> many &ldquo;remote&rdquo; roles are remote within one country only, or restricted to one province/region. Confirm before treating a role as a remote lead.</li>
      <li><strong>Language note:</strong> regional boards like Jobboom and Jobillico are French-first. Also search &ldquo;administrateur de base de donn&eacute;es&rdquo; to catch French-only postings.</li>
      <li><strong>Recruiters are the hidden market:</strong> senior and contract roles often go through Robert Half, Procom, S.i. Systems, Akkodis and Fed IT before (or instead of) public boards.</li>
      <li><strong>Go direct:</strong> big employers post on their own career sites first &mdash; the <strong>Big Six banks</strong> tab links straight into RBC, TD, Scotiabank, BMO, CIBC and National Bank.</li>
      <li><strong>Re-run anytime:</strong> the <strong>&#8635; Re-run</strong> button reloads the page and rebuilds every search link from your latest saved job types and location.</li>
    </ul>
    <button class="reset" id="reset">Clear all checkmarks</button>
  </footer>
</div>

<script>
/* ---- data injected by Flask ---- */
const DATA       = {{ sites | tojson }};
const LEADS      = {{ cfg.leads | tojson }};
const LAST_SCAN  = {{ cfg.last_scan | tojson }};
const LOC        = {{ active | tojson }};
let   JOB_TYPES  = {{ cfg.job_types | tojson }};
let   term       = {{ cfg.term | tojson }};

/* ---- url building ---- */
function enc(t)  { return encodeURIComponent((t || "").trim()); }
function slug(t) { return (t || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""); }
function buildUrl(tpl) {
  return tpl
    .replace(/{Q}/g, enc(term))
    .replace(/{S}/g, slug(term))
    .replace(/{CITY_ENC}/g, enc(LOC.city))
    .replace(/{CITY_SLUG}/g, slug(LOC.city))
    .replace(/{CITY}/g, LOC.city || "")
    .replace(/{STATE_ENC}/g, enc(LOC.state))
    .replace(/{STATE_SLUG}/g, slug(LOC.state))
    .replace(/{STATE}/g, LOC.state || "")
    .replace(/{COUNTRY_ENC}/g, enc(LOC.country))
    .replace(/{COUNTRY}/g, LOC.country || "");
}

/* ---- server calls ---- */
async function api(path, body) {
  try {
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    });
    return await r.json();
  } catch (e) {
    return { ok: false, error: "Could not reach the server. Is app.py still running?" };
  }
}

/* ---- checkmark state (on-device) ---- */
const KEY = "dba-launchpad-checks-v2";
let checks = {};
try { checks = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { checks = {}; }
function save() { try { localStorage.setItem(KEY, JSON.stringify(checks)); } catch (e) {} }

function isNewLead(item) { return !!LAST_SCAN && item.firstSeen === LAST_SCAN; }

function newCountForSite(id) {
  let n = 0;
  Object.keys(LEADS).forEach(sec => {
    LEADS[sec].forEach(item => { if (item.src === id && isNewLead(item)) n++; });
  });
  return n;
}

/* ---- rendering: site cards ---- */
function pill(id, noCount) {
  if (noCount) return '<div class="pill"><div class="num empty">&mdash;</div><div class="lbl">direct</div></div>';
  const n = newCountForSite(id);
  return '<div class="pill' + (n > 0 ? ' live' : '') + '"><div class="num' + (n > 0 ? '' : ' empty')
    + '">' + n + '</div><div class="lbl">new</div></div>';
}

function siteCard(item, id) {
  const card = document.createElement("div");
  card.className = "card" + (checks[id] ? " done" : "");
  const cb = document.createElement("input");
  cb.type = "checkbox"; cb.className = "chk"; cb.checked = !!checks[id];
  cb.addEventListener("change", () => {
    checks[id] = cb.checked; save();
    card.classList.toggle("done", cb.checked);
  });
  const body = document.createElement("div");
  body.className = "body";
  body.innerHTML =
    '<div class="row1"><span class="name"></span><span class="badge ' + item.badge + '"></span></div>'
    + '<div class="desc"></div>'
    + '<div class="actions"><a class="open" target="_blank" rel="noopener">Open search &#8599;</a></div>';
  body.querySelector(".name").textContent = item.name;
  body.querySelector(".badge").textContent = item.label;
  body.querySelector(".desc").textContent = item.desc;
  const a = body.querySelector("a.open");
  a.href = buildUrl(item.tpl);
  a.dataset.tpl = item.tpl;
  const col = document.createElement("div");
  col.className = "countcol";
  col.innerHTML = pill(id, item.noCount);
  card.appendChild(cb); card.appendChild(body); card.appendChild(col);
  return card;
}

/* ---- rendering: lead cards ---- */
function leadCard(item, id) {
  const isNew = isNewLead(item);
  const card = document.createElement("div");
  card.className = "card" + (checks[id] ? " done" : "") + (isNew ? " isnew" : "");
  const cb = document.createElement("input");
  cb.type = "checkbox"; cb.className = "chk"; cb.checked = !!checks[id];
  cb.addEventListener("change", () => {
    checks[id] = cb.checked; save();
    card.classList.toggle("done", cb.checked);
  });
  const body = document.createElement("div");
  body.className = "body";
  body.innerHTML =
    '<div class="row1"><span class="name"></span><span class="badge b-lead">Lead</span>'
    + (isNew ? '<span class="badge tag-new">New</span>' : '')
    + '</div><div class="desc"></div>'
    + '<div class="meta"></div>'
    + '<div class="actions"><a class="open" target="_blank" rel="noopener">View posting &#8599;</a></div>';
  body.querySelector(".name").textContent = item.name;
  body.querySelector(".desc").textContent = item.desc;
  body.querySelector(".meta").textContent =
    "First seen " + (item.firstSeen || "--") + (isNew ? " · new this refresh" : "");
  body.querySelector("a.open").href = item.url;
  card.appendChild(cb); card.appendChild(body);
  return card;
}

function render() {
  Object.keys(DATA).forEach(sec => {
    const host = document.getElementById(sec);
    if (!host) return;
    host.innerHTML = "";
    DATA[sec].forEach((item, i) => host.appendChild(siteCard(item, sec + "-" + i)));
  });
  Object.keys(LEADS).forEach(sec => {
    const host = document.getElementById(sec);
    if (!host) return;
    host.innerHTML = "";
    if (!LEADS[sec].length) {
      const m = document.createElement("div");
      m.className = "empty-msg";
      m.textContent = "No active leads here right now.";
      host.appendChild(m);
    }
    LEADS[sec].forEach((item, i) => host.appendChild(leadCard(item, sec + "-" + i)));
  });
  refreshCounts();
}

function refreshCounts() {
  const buckets = {
    "c-onsite": ["leads-onsite"],
    "c-remote": ["leads-remote"],
    "c-leads":  ["leads-onsite", "leads-remote"]
  };
  Object.keys(buckets).forEach(cid => {
    let n = 0;
    buckets[cid].forEach(sec => (LEADS[sec] || []).forEach(it => { if (isNewLead(it)) n++; }));
    const el = document.getElementById(cid);
    el.textContent = n > 0 ? (n + " new") : "";
    el.classList.toggle("hasnew", n > 0);
  });
}

function rebuildLinks() {
  document.querySelectorAll("a.open[data-tpl]").forEach(a => {
    a.href = buildUrl(a.dataset.tpl);
  });
}

/* ---- search term + presets ---- */
const input = document.getElementById("term");
input.value = term;

let termTimer;
function setTerm(t) {
  term = t || "SQL Server DBA";
  rebuildLinks();
  syncPresets();
  clearTimeout(termTimer);
  termTimer = setTimeout(() => { api("/api/term", { term: term }); }, 600);
}
input.addEventListener("input", () => setTerm(input.value));
input.addEventListener("blur", () => {
  if (!input.value.trim()) { input.value = "SQL Server DBA"; setTerm("SQL Server DBA"); }
});

const presetWrap = document.getElementById("presets");
function renderPresets() {
  presetWrap.innerHTML = "";
  JOB_TYPES.forEach(p => {
    const chip = document.createElement("span");
    chip.className = "preset";
    const lbl = document.createElement("span");
    lbl.className = "lbl"; lbl.textContent = p;
    lbl.addEventListener("click", () => { input.value = p; setTerm(p); });
    const x = document.createElement("span");
    x.className = "x"; x.textContent = "×"; x.title = "Remove this job type";
    x.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteJobType(p);
    });
    chip.appendChild(lbl); chip.appendChild(x);
    presetWrap.appendChild(chip);
  });
  syncPresets();
  document.getElementById("jtCount").textContent =
    JOB_TYPES.length + (JOB_TYPES.length === 1 ? " saved" : " saved");
}
function syncPresets() {
  [...presetWrap.children].forEach(chip => {
    const t = chip.querySelector(".lbl").textContent;
    chip.classList.toggle("on", t.trim().toLowerCase() === (term || "").trim().toLowerCase());
  });
}

async function addJobType() {
  const v = document.getElementById("addType").value.trim();
  if (!v) { document.getElementById("addType").focus(); return; }
  const r = await api("/api/job-types/add", { name: v });
  if (r.ok) location.reload();
  else alert(r.error || "Could not add that job type.");
}
async function deleteJobType(name) {
  const r = await api("/api/job-types/delete", { name: name });
  if (r.ok) location.reload();
  else alert(r.error || "Could not remove that job type.");
}
document.getElementById("addTypeBtn").addEventListener("click", addJobType);
document.getElementById("addType").addEventListener("keydown", e => {
  if (e.key === "Enter") addJobType();
});

/* ---- location controls ---- */
const locSelect = document.getElementById("locSelect");
document.getElementById("locName").textContent = locSelect.options[locSelect.selectedIndex].text.trim();

locSelect.addEventListener("change", async () => {
  const r = await api("/api/locations/active", { id: locSelect.value });
  if (r.ok) location.reload();
  else alert(r.error || "Could not switch location.");
});

document.getElementById("locRemove").addEventListener("click", async () => {
  const r = await api("/api/locations/delete", { id: locSelect.value });
  if (r.ok) location.reload();
  else alert(r.error || "Could not remove this location.");
});

document.getElementById("addLocBtn").addEventListener("click", async () => {
  const country = document.getElementById("addCountry").value.trim();
  const state   = document.getElementById("addState").value.trim();
  const city    = document.getElementById("addCity").value.trim();
  if (!country && !state && !city) {
    alert("Enter at least a country, state/province or city.");
    return;
  }
  const r = await api("/api/locations/add", { country: country, state: state, city: city });
  if (r.ok) location.reload();
  else alert(r.error || "Could not add that location.");
});

/* ---- tabs ---- */
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(tab.dataset.panel).classList.add("active");
  });
});

document.getElementById("reset").addEventListener("click", () => { checks = {}; save(); render(); });

/* ---- re-run: reload the page, re-pull config, rebuild every search link ---- */
document.getElementById("rerun").addEventListener("click", () => { location.reload(); });

/* ---- go ---- */
renderPresets();
render();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# PORT MANAGEMENT
# ---------------------------------------------------------------------------
def free_port(port):
    """Kill any process currently listening on `port` so we can rebind it.

    This makes restarting the app painless: a stale `python app.py` left
    running in another terminal is stopped automatically instead of causing
    an "Address already in use" error. Uses `lsof`; if that is unavailable
    the function does nothing and any conflict is left to app.run() to report.
    """
    try:
        result = subprocess.run(
            ["lsof", "-ti", "tcp:%d" % port, "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return  # no lsof -- skip quietly
    pids = sorted({int(p) for p in result.stdout.split() if p.strip().isdigit()})
    me = os.getpid()
    killed = False
    for pid in pids:
        if pid == me:
            continue
        print("  Port %d is held by PID %d -- stopping it." % (port, pid))
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        # wait briefly for a graceful exit, then force-kill if needed
        for _ in range(15):
            time.sleep(0.2)
            try:
                os.kill(pid, 0)        # signal 0 = "are you still alive?"
            except ProcessLookupError:
                break
        else:
            try:
                os.kill(pid, signal.SIGKILL)
                print("  PID %d did not exit -- force-killed." % pid)
            except ProcessLookupError:
                pass
        killed = True
    if killed:
        time.sleep(0.6)  # let the OS fully release the socket


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    load_config()  # ensure config.json exists on disk
    port = int(os.environ.get("PORT", "5050"))
    free_port(port)  # always reclaim the port before starting
    print("\n  DBA / Data Roles -- Job Search Launchpad")
    print("  Open this in your browser:  http://127.0.0.1:%d\n" % port)
    app.run(host="127.0.0.1", port=port, debug=False)
