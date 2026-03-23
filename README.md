# IT-OCED for a Library Instance

This repository contains the code required to (1) generate simulation data for a library domain and (2) build an IT‑OCED instance in Neo4j using PromG and custom Cypher queries.

## 🚀 Quick Start (TL;DR)
1. Start your Neo4j server 
   - Installed Plugins: APOC Core and APOC extended
   - Create apoc.conf in the database `conf/` directory and add: `apoc.import.file.enabled=true`
2. Configure the connection settings in config.yaml (ensure the URI and password match your Neo4j instance).
3. Generate data by running: `python 2_simulation/create_data.py`
   - Make sure to have installed the required packages: `pip install pandas faker simpy tqdm`
4. Build the IT‑OCED instance by running all cells in: `4_build_it_oced/import_into_neo4j.ipynb`
   -  Make sure to have installed PromG == v2.4.7 `pip installpromg==2.4.7`

The notebook also contains the constraint checks and statistics (e.g., node counts, execution times) at the end.

------------------------
# Detailed steps
## 📘 Generating Simulation Data
Two scripts are used to produce simulation data:

- `2_simulation/create_data.py`: Reads the input files, initializes configuration, and triggers the simulation.

- `2_simulation/library_simulation.py`: Contains the SimPy-based library simulation logic.

### Required Python Libraries
- random
- datetime
- pathlib
- pandas
- faker
- simpy 
- tqdm

Install via (for instance):
```bash
pip install pandas faker simpy tqdm
```

### Input Files (`1_input_data/`)
- `books.csv`: Dataset of books (source: https://www.kaggle.com/datasets/jealousleopard/goodreadsbooks)

### Settings to set in `create_data.py`
- `NUM_YEARS = 1` — number of years to simulate
- `WITH_VIOLATIONS = True` — whether to inject violations
- Reproducibility seeds:
```python
18 Faker.seed(0)
19 random.seed(1)
```

### Output Files (`2_output_data/`)
- `library_1_books.csv` — The generated library catalogue
- `members.csv` — Member profiles (generated with Faker)
- `event_log.csv` — Timestamped activity events
- `injected_violations.csv` — If enabled, contains all injected violations

---
## 🧱 Building the IT‑OCED Instance
The data is loaded into Neo4j using PromG and the notebook import_into_neo4j.ipynb.
A running Neo4j database is required.

### 🛠️ Installing Neo4j
Install Neo4j using one of the following:
- Neo4j Desktop (recommended)
- Neo4j Community Server

Version Requirements

> [!IMPORTANT]
The code works only with Neo4j v5.24.0 or newer (tested with v5.26.19).

#### Install APOC
You’ll need both APOC Core and APOC Extended:
1. **APOC Core**
   - Select your database in Neo4j Desktop
   - Open the Plugins tab
   - Install APOC

2. **APOC Extended**
    - Download the matching version from:
https://github.com/neo4j-contrib/neo4j-apoc-procedures/releases
   - Place `apoc‑<version>‑extended.jar` in the database's `plugins/` folder
   - Restart the database

3. **Enable file import**
    - Create `apoc.conf` in the database `conf/` directory and add: `apoc.import.file.enabled=true`

#### Allocate More Memory
Recommended setting: `server.memory.heap.max_size=2G` in `neo4j.conf` also found in `conf/` directory.

### ⚙️ Configuration File
Edit the file: `4_build_it_oced/config.yaml`
Set:

- URI (default: bolt://localhost:7687)
- Password (default: libraries)

### 📦 Installing PromG

Install PromG as a Python package: `pip install promg==2.4.7`
Source code: https://github.com/PromG-dev/promg-core

