import os
import json
import unittest

class TestHistoricalCourseDiff(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.historical_dir = os.path.join(self.base_dir, "data", "historical")
        self.years = ["2021_2022", "2022_2023", "2023_2024", "2024_2025", "2025_2026", "2026_2027"]

    def test_historical_datasets_exist(self):
        """Verify that all 6 historical graph files exist under data/historical."""
        for ys in self.years:
            file_path = os.path.join(self.historical_dir, f"wpi_course_graph_{ys}.json")
            if not os.path.exists(file_path) and ys == "2026_2027":
                file_path = os.path.join(self.base_dir, "data", "wpi_course_graph.json")
            self.assertTrue(os.path.exists(file_path), f"Missing dataset: {file_path}")

    def test_course_diff_logic(self):
        """Simulate computing diff for a sample course across historical datasets."""
        catalogs = {}
        for ys in self.years:
            file_path = os.path.join(self.historical_dir, f"wpi_course_graph_{ys}.json")
            if not os.path.exists(file_path) and ys == "2026_2027":
                file_path = os.path.join(self.base_dir, "data", "wpi_course_graph.json")

            with open(file_path, "r", encoding="utf-8") as f:
                catalogs[ys] = json.load(f)

        # Check MA 1024 or DS 3010
        target_course = "MA 1024"
        history = []
        for ys in self.years:
            if target_course in catalogs[ys]:
                node = catalogs[ys][target_course]
                history.append({
                    "year": ys,
                    "prereqs": sorted(node.get("prerequisites", [])),
                    "terms": sorted(node.get("terms", []))
                })

        self.assertGreater(len(history), 0, f"{target_course} should exist in historical catalogs.")

if __name__ == "__main__":
    unittest.main()
