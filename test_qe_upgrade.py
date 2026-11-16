"""Automated tests and demo runner for the upgraded RTSP QE modules."""

import json
import unittest
from pathlib import Path

from camera_profile_validator import (
    CameraProfile,
    StreamProbeResult,
    load_profiles,
    validate_profile,
)
from qe_report_generator import (
    build_slack_summary,
    export_csv_report,
    export_html_report,
)
from stream_resilience_tester import make_simulated_probe, run_resilience_check


class TestRtspQeUpgrade(unittest.TestCase):
    def test_profile_validation_pass_warn_fail(self) -> None:
        profile = CameraProfile(
            vendor="Hikvision",
            model="DS-2CD2143G2-I",
            rtsp_url="rtsp://demo:554/ch1",
            expected_codec="h264",
            expected_width=1920,
            expected_height=1080,
            expected_fps=30.0,
        )
        ok = validate_profile(
            profile, StreamProbeResult("h264", 1920, 1080, 29.8, 1.5, True)
        )
        self.assertEqual(ok.status, "PASS")

        warn = validate_profile(
            profile, StreamProbeResult("h264", 1920, 1080, 22.0, 1.5, True)
        )
        self.assertEqual(warn.status, "WARN")

        fail = validate_profile(
            profile, StreamProbeResult("h265", 1280, 720, 30.0, 1.5, True)
        )
        self.assertEqual(fail.status, "FAIL")

    def test_resilience_and_reports(self) -> None:
        profiles = load_profiles(Path(__file__).parent / "camera_profiles.json")
        self.assertEqual(len(profiles), 3)

        probes = [
            StreamProbeResult("h264", 1920, 1080, 30.0, 1.5, True),
            StreamProbeResult("h264", 1920, 1080, 24.0, 1.5, True),
            StreamProbeResult("h264", 1920, 1080, 25.0, 2.0, True),
        ]
        validations = [
            validate_profile(p, pr) for p, pr in zip(profiles, probes)
        ]
        resilience = [
            run_resilience_check(
                channel_id=f"ch{i+1}",
                vendor=p.vendor,
                probe_fn=make_simulated_probe(0.2, 0.85, seed=10 + i),
                total_checks=15,
                retry_delay_sec=0.0,
            )
            for i, p in enumerate(profiles)
        ]

        out_dir = Path(__file__).parent / "sample_reports"
        csv_path = export_csv_report(validations, resilience, out_dir / "qe_report.csv")
        html_path = export_html_report(validations, resilience, out_dir / "qe_report.html")
        slack_json = json.loads(build_slack_summary(validations, resilience))

        self.assertTrue(csv_path.exists())
        self.assertTrue(html_path.exists())
        self.assertIn("RTSP QE Summary", slack_json["text"])


if __name__ == "__main__":
    unittest.main()