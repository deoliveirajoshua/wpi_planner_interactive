# WPI Course Catalog Visualizer

An interactive prerequisite network visualizer for Worcester Polytechnic Institute (WPI) courses. 

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

Site maintained by Joshua DeOliveira. Course data collected from [planner.wpi.edu](https://planner.wpi.edu/).
