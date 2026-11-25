"""Build skills_demand_dashboard.html from O*NET skill ratings and the Indeed posting indices.

Run from the project root:  python3 scripts/build_skills_dashboard.py
Reads  : Data/Onet/*.xlsx|csv, Data/monthly/indeed_data_analysis_job_postings.csv,
         Data/daily/indeed-software.csv, Data/daily/indeed-all.csv
Writes : skills_demand_dashboard.html and docs/skills_demand_dashboard.html
"""
import json, re, shutil
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "Data"
ONET = DATA / "Onet"

# --- Indeed categories -> O*NET occupations (matched on job titles) -------------------------
FAMILIES = {
    "SW": {
        "label": "Software Development",
        "occs": ["15-1252.00", "15-1251.00", "15-1253.00", "15-1254.00",
                 "15-1299.08", "15-1255.01", "15-1299.05"],
    },
    "DA": {
        "label": "Data & Analytics",
        "occs": ["15-2051.01", "15-2051.02", "15-2041.00", "15-2041.01", "15-2031.00",
                 "15-1243.00", "15-1243.01", "15-1242.00", "13-2099.01", "15-2099.01",
                 "13-1161.00", "15-1211.00"],
    },
}

# --- Indeed posting indices (Feb 1 2020 = 100) ----------------------------------------------
da = pd.read_csv(DATA / "monthly/indeed_data_analysis_job_postings.csv")
da = da[(da.countryCode == "US") & (da.postingType == "TOTAL")].set_index("dateString")["value"].rename("DA")
sw = pd.read_csv(DATA / "daily/indeed-software.csv", index_col=0).iloc[:, 0].rename("SW")
al = pd.read_csv(DATA / "daily/indeed-all.csv", index_col=0).iloc[:, 0].rename("ALL")
idx = pd.concat([da, sw, al], axis=1).dropna().sort_index()

# --- O*NET skills: 10 essential + 25 transferable ---------------------------------------------
es = pd.read_csv(ONET / "Essential_Skills_ALL.csv", encoding="utf-8-sig")
tr = pd.read_excel(ONET / "Transferable Skills.xlsx")
sk = pd.concat([es.assign(Group="Essential"), tr.assign(Group="Transferable")])
ref = pd.read_excel(ONET / "Content Model Reference.xlsx").set_index("Element ID")["Description"]

order = (sk[["Element ID", "Element Name", "Group"]].drop_duplicates()
         .sort_values(["Group", "Element ID"]).reset_index(drop=True))
names = order["Element Name"].tolist()
im = sk[sk["Scale ID"] == "IM"].pivot_table(index="Element Name", columns="O*NET-SOC Code", values="Data Value").reindex(names)
lv = sk[sk["Scale ID"] == "LV"].pivot_table(index="Element Name", columns="O*NET-SOC Code", values="Data Value").reindex(names)

def fam_mean(tbl, fam):
    return tbl[FAMILIES[fam]["occs"]].mean(axis=1)

skills = []
for i, r in order.iterrows():
    n = r["Element Name"]
    skills.append({
        "name": n, "group": r["Group"], "desc": str(ref.get(r["Element ID"], "")),
        "im": {"DA": round(fam_mean(im, "DA")[n], 3), "SW": round(fam_mean(im, "SW")[n], 3), "ALL": round(im.loc[n].mean(), 3)},
        "lv": {"DA": round(fam_mean(lv, "DA")[n], 3), "SW": round(fam_mean(lv, "SW")[n], 3), "ALL": round(lv.loc[n].mean(), 3)},
    })

# --- Occupations and their job titles ----------------------------------------------------------
jt = pd.read_excel(ONET / "Job Titles.xlsx")
rt = pd.read_excel(ONET / "Sample of Reported Titles.xlsx")
titles_of = {}
occs = []
for fam, spec in FAMILIES.items():
    for code in spec["occs"]:
        name = sk.loc[sk["O*NET-SOC Code"] == code, "Title"].iloc[0]
        rep = rt[(rt["O*NET-SOC Code"] == code)].sort_values("Shown in My Next Move", ascending=False)["Reported Job Title"].tolist()
        alt = jt[jt["O*NET-SOC Code"] == code]["Job Title"].tolist()
        seen, ex = set(), []
        for t in rep + alt:
            k = t.lower()
            if k not in seen:
                seen.add(k); ex.append(t)
        occs.append({"code": code, "title": name, "family": fam,
                     "n_titles": len(set(t.lower() for t in rep + alt)),
                     "examples": ex[:6], "im": [round(float(im.loc[n, code]), 2) for n in names]})

# --- Technology lists (O*NET "Software Skills") ------------------------------------------------
sf = pd.read_excel(ONET / "Software Skills.xlsx")
tech = {}
for fam, spec in FAMILIES.items():
    s = sf[sf["O*NET-SOC Code"].isin(spec["occs"])]
    g = s.groupby("Workplace Example").agg(n=("O*NET-SOC Code", "nunique"),
                                           hot=("Hot Technology", lambda x: bool((x == "Y").any())))
    g = g.reset_index().sort_values(["n", "hot", "Workplace Example"], ascending=[False, False, True]).head(18)
    tech[fam] = [{"name": r["Workplace Example"], "n": int(r["n"]), "hot": bool(r["hot"])} for _, r in g.iterrows()]

payload = {
    "meta": {"first": idx.index[0], "last": idx.index[-1], "onet": "30.3", "n_occ_all": int(im.shape[1]),
             "labels": {k: v["label"] for k, v in FAMILIES.items()}},
    "dates": idx.index.tolist(),
    "idx": {k: [round(float(v), 2) for v in idx[k]] for k in ["DA", "SW", "ALL"]},
    "skills": skills, "occs": occs, "tech": tech,
}

tpl = (ROOT / "scripts/skills_dashboard_template.html").read_text()
out = tpl.replace("/*__DATA__*/null", json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
(ROOT / "skills_demand_dashboard.html").write_text(out)
(ROOT / "docs").mkdir(exist_ok=True)
shutil.copyfile(ROOT / "skills_demand_dashboard.html", ROOT / "docs/skills_demand_dashboard.html")
print("rows", len(idx), idx.index[0], idx.index[-1], "| skills", len(skills), "| occupations", len(occs))
print(idx.iloc[[0, -1]])
