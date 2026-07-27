# WPI Course Catalog Visualizer

An interactive prerequisite network visualizer for Worcester Polytechnic Institute (WPI) courses. Built with HTML5, CSS3, JavaScript, and Vis.js, backed by a Python scraping and graph processing pipeline.

## Features

- **Interactive Prerequisite Network**: Visualizes WPI course prerequisites, relationships, and course unlocked downstream.
- **Two-Tier Interaction Model**:
  - **Single Left-Click**: Highlights a course (Red), its prerequisites (Indigo), and unlocked courses (Blue) directly in the main view while keeping background nodes visible.
  - **Double Left-Click**: Enters **Isolated Focused View** (hides background nodes, auto-zooms onto the focused prerequisite path). Click empty space to return to the main view.
- **Department Filtering**: Select a department from the header or click **Show All** in the sidebar to cluster and focus on department courses.
- **Recursive Prerequisite Unwinder**: Click **Show All (Unwind)** in the course details sidebar to expand full multi-tier prerequisite chains.
- **Live Graph Physics**: Toggle physics simulation with smooth force-directed clustering and anti-collision node spacing.
- **Automated Scraping & Deployment**: Built-in GitHub Actions workflow to re-scrape and publish updates automatically.

## Quick Start

### 1. Run Locally
Start a local HTTP server from the root directory:

```bash
python -m http.server 8000
```
Open `http://localhost:8000` in your web browser.

### 2. Rebuild Graph / HTML Assets
To re-run the processing pipeline and re-generate static graph assets:

```bash
python scripts/scraper.py -v
python scripts/prerequisite_scraper.py -v
python scripts/wpi_course_graph.py -v
python scripts/plot_course_graph.py -v
```

## Running Tests

Run the full automated unit test suite:

```bash
python -m unittest discover -s test -p "test_*.py"
```

## Repository Structure

```text
wpi_planner_interactive/
├── index.html                    # Web application entrypoint
├── assets/
│   ├── css/styles.css            # Design system & typography
│   ├── js/app.js                 # Central application logic & physics config
│   └── wpi_course_graph.html     # Standalone single-file HTML bundle
├── data/                         # Scraped & processed graph datasets (JSON/CSV)
├── scripts/                      # Python scraping and graph generator scripts
├── test/                         # Automated unit test suite
└── .github/workflows/deploy.yml  # GitHub Actions Pages deployment workflow
```

## License & Credits

Site maintained by Joshua DeOliveira. Course data collected from [planner.wpi.edu](https://planner.wpi.edu/).
