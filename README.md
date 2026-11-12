# WorkForceIQ-Agent

## 1. About the Project

WorkForceIQ-Agent is an AI-powered workforce planning and intelligence platform that helps managers understand workforce skills, project demand, and staffing gaps. The application has been successfully deployed on AWS EC2 (Amazon Web Services).

## 2. Main Features

- **Dashboard:** View workforce demand, skill shortages, internal talent, strategy comparisons, and data summaries.
- **AI Assistant:** Ask questions in everyday language about workforce data. The assistant uses local Python tools to search and calculate results, then uses Groq to explain them.
- **Workforce data analysis:** Review skill gaps, available capacity, qualified employees, and planning scenarios. Results support decisions; they do not assign employees.
- **Project Intelligence:** Upload project requirements as a PDF or DOCX, review extracted requirements, confirm them, match them against local workforce data, and download a DOCX report.

## 3. Requirements

Before you start, install:

- Windows 10 or later with PowerShell
- Python 3.10 or later
- Git
- A Groq account and API key for the AI Assistant and AI-based requirement extraction

## 4. Clone the Repository

On GitHub, click **Code** and copy the HTTPS URL. Paste it in place of the text below, then choose a folder name:

```powershell
$repoUrl = "PASTE_THE_HTTPS_URL_HERE"
$repoFolder = "WorkForceIQ-Agent"
git clone $repoUrl $repoFolder
Set-Location $repoFolder
```

The current checkout has no configured Git remote, so a repository-specific clone URL cannot be verified here.

## 5. Set Up the Environment

Run these commands from the repository folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks virtual-environment activation, use the environment's Python executable directly instead:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 6. Configure Environment Variables

Create a `.env` file in the repository folder. You can open a new file with:

```powershell
notepad .env
```

Create an API key in the [Groq Console](https://console.groq.com/keys). Add your own values to `.env`:

```dotenv
GROQ_API_KEY=<your-groq-api-key>
GROQ_MODEL=<model-id-available-to-your-groq-account>
WORKFORCEIQ_DATA_ROOT=./data/staging/phase12_run_b_anomalies_20261112_public/data
```

Replace both Groq placeholders; do not include angle brackets. Keep `.env` private and never commit it. The project ignores `.env` in Git. `WORKFORCEIQ_DATA_ROOT` must point to the folder that directly contains `raw` and `processed`.

## 7. Dataset Setup

The sanitized public Run B dataset package is included in this repository. The app reads its CSV files from `raw/` and `processed/` beneath `WORKFORCEIQ_DATA_ROOT`.

Its package folder is:

```text
data/staging/phase12_run_b_anomalies_20261112_public/
```

Set `WORKFORCEIQ_DATA_ROOT` to the package's `data/` directory. In Windows PowerShell, run this from the repository folder:

```powershell
$env:WORKFORCEIQ_DATA_ROOT = (Resolve-Path ".\data\staging\phase12_run_b_anomalies_20261112_public\data").Path
```

You can add the same relative path to `.env` as shown above. If you move the package, update the setting to the full path of its `data/` directory. Without this dataset, workforce pages, matching, and validation will not have usable data.

## 8. Run the Application

From the repository folder, start Streamlit:

```powershell
python -m streamlit run app.py
```

Streamlit prints a local address, usually `http://localhost:8501`. Open that address in your browser. Using `python -m streamlit` runs Streamlit through the selected Python environment.

## 9. Try the AI Assistant

Ask any of these questions:

- How many active employees are there?
- Find employees who have both Python and SQL.
- Find employees who have Python or Java.
- Show employees who have more than one qualified skill.
- Find internal talent with Python skills.
- Explain how workforce skill shortages are identified.

## 10. Run Tests and Data Validation

Run the test suite from the repository folder:

```powershell
python -m pytest
```

To validate the Run B workforce data, first set the data root in the current PowerShell window, then run the existing validator:

```powershell
$env:WORKFORCEIQ_DATA_ROOT = (Resolve-Path ".\data\staging\phase12_run_b_anomalies_20261112_public\data").Path
python -m validation.validate_data
```

The public package also contains saved data-validation and anomaly-validation reports under its `reports/` folder.

## 11. Project Documentation

- [High-Level Design](docs/HLD.md)
- [Data Dictionary](docs/data_dictionary.md)
- [Source Manifest](docs/source_manifest.md)
- [Validation Summary](docs/validation_summary.md)

## 12. Important Notes

- The dashboard can show local workforce analysis without a Groq key. The AI Assistant and AI-based requirement extraction need both `GROQ_API_KEY` and `GROQ_MODEL`.
- Project requirement documents are sent to Groq for requirement extraction. Employee matching and capacity calculations run locally in Python. The AI Assistant may send a small, bounded set of tool results to Groq so it can explain verified results.
- The application is read-only for workforce planning. Recommendations and strategy comparisons do not create allocations or change workforce records.
- `.env` is local configuration and is not supplied by the repository. Set the data root and Groq values on each computer where you run the app.

## Deployment

**Successfully deployed on AWS EC2 (Amazon Web Services).**

### Live Demo

[**Access WorkForceIQ-Agent**](http://52.62.176.8)
