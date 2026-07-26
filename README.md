# WPI Planner Course Scraper & Interactive Graph Toolkit

A complete Python toolkit and modular web application for scraping WPI course offerings, parsing prerequisite relationships, tracking course aliases/cross-listings, building connected graph datasets, and displaying them via a polished, interactive web interface.

## Live Web Application

Once published to GitHub Pages, the web interface will be live at:
`https://<your-username>.github.io/wpi_planner_interactive/`

## Project Structure

```text
wpi_planner_interactive/
├── index.html                    # Main HTML5 UI entrypoint
├── assets/
│   ├── css/
│   │   └── styles.css            # Modern glassmorphism CSS design system & typography
│   ├── js/
│   │   └── app.js                # App logic, Vis.js graph engine & path high-lighter
│   └── wpi_course_graph.html     # Standalone single-file HTML bundle
├── data/
│   ├── wpi_courses.json          # Scraped course catalog (JSON)
│   ├── wpi_courses.csv           # Scraped course catalog (CSV)
│   ├── wpi_course_dag.json       # Prerequisite DAG dataset
│   └── wpi_course_graph.json     # Bidirectional graph dataset ('prerequisite_for')
├── scripts/
│   ├── scraper.py                # Scrapes planner.wpi.edu
│   ├── prerequisite_scraper.py   # Parses prerequisites & aliases into DAG
│   ├── wpi_course_graph.py       # Builds bidirectional graph with reverse edges
│   └── plot_course_graph.py      # Generates graph visualization assets
├── test/                         # Automated unit test suite
│   ├── test_scraper.py
│   ├── test_prerequisite_scraper.py
│   ├── test_course_graph.py
│   └── test_plot_course_graph.py
├── .github/
│   └── workflows/
│       └── deploy.yml            # GitHub Actions automated builder & Pages deployment
└── README.md
```

## UI Features

- **Polished Glassmorphic Design System**: Dark theme (`#090d16`), Google Fonts (`Inter` & `Outfit`), glassmorphism backdrop blur, vibrant HSL department colors.
- **Interactive Prerequisite Path Highlighting**: Clicking any course highlights its **upstream prerequisite chain** (cyan/blue) and **downstream unlocked courses** (emerald green).
- **Search & Auto-Focus**: Instant search bar with auto-centering and zoom animation.
- **Department Filters & Legend**: Quick department filtering and legend selection.
- **Detailed Course Inspector**: Sidebar displaying course badges for direct prerequisites, unlocked courses, aliases, and course description text.

## Local Quick Start

### 1. Run Complete Data & Build Pipeline

```bash
python scripts/scraper.py -v
python scripts/prerequisite_scraper.py -v
python scripts/wpi_course_graph.py -v
python scripts/plot_course_graph.py -v
```

### 2. Launch Local Web Server

```bash
python -m http.server 8000
```
Open `http://localhost:8000` in your web browser.

## Running Tests

Run the full automated unit test suite:

```bash
python -m unittest discover -s test -p "test_*.py"
```
