"""Parser regression tests."""

from __future__ import annotations

import unittest

from tech_notes_form.exporter import format_output
from tech_notes_form.parser import MODE_LABEL_BLOCK, parse_notes

INCIDENT_SAMPLE = """\
Priority: P1 - Critical (Production Outage)
INC Number: INC0084321
Agency: Department of Transportation (DoT)
Name: Alex Chen (Lead Systems Engineer)
State: Active / In-Progress
Software/Firmware Version: EdgeOS v4.2.1-Build78
Deployment Date: June 28, 2026

Initial Issue Description:
Following the scheduled weekend firmware upgrade to v4.2.1-Build78, all core routing nodes at the regional data center began experiencing intermittent kernel panics and spontaneous reboots every 45 to 60 minutes. This has resulted in a 30% drop in telemetry data ingestion and loss of redundancy for critical transit monitoring systems.

Customer Ticket History:

* 06/28/2026 23:00 UTC: Upgrade completed successfully during maintenance window.
* 06/29/2026 01:15 UTC: First spontaneous reboot detected on Node-01. Ticket opened by automated monitoring.
* 06/29/2026 03:30 UTC: Nodes 02 and 03 experienced identical reboots. Escalated to Tier 2 Support.
* 06/30/2026 08:00 UTC: P1 crisis bridge initiated after the issue persisted through multiple manual reloads. Tier 3 Engineering engaged.

Incident Context & Background:
The v4.2.1-Build78 firmware patch was deployed to resolve a known memory leak identified in the previous version (v4.1.9). The deployment went smoothly in the staging environment last week, but the staging environment does not handle the high-throughput encrypted IPsec traffic volume seen in the live production network.

Diagnostic Findings:

* Log Analysis: Core dumps extracted from Node-01 and Node-03 reveal a NullPointer exception in the cryptographic acceleration module (crypto_accel.ko).
* Resource Metrics: CPU and memory utilization remain within normal bounds (under 45%) right up until the exact second of the crash.
* Trigger Condition: The crash correlates perfectly with high-burst periods of multi-protocol label switching (MPLS) traffic wrapped in IPsec tunnels, causing a buffer overflow in the hardware offload queue.

KB Utilization:

* KB0041229: "Known issues with EdgeOS 4.2 Crypto Offloading" - Checked, but the symptoms listed there only involve dropped packets, not total kernel panics.
* KB0039811: "Configuring software-based crypto fallback" - Utilized to formulate the current mitigation strategy.

Actions Taken:

* Disabled hardware crypto-offloading via CLI on Node-01 (no crypto hardware-accel) to test if shifting the load to software-based processing stabilizes the kernel.
* Monitored Node-01 for 90 minutes. Node-01 has remained stable with 0 reboots, though CPU utilization has increased by 22%.
* Applied the same software-fallback workaround to Node-02 and Node-03 to stabilize the regional network temporarily.

Next Steps:

1. Engineering Review: Provide the core dump files to the Firmware Development Team to patch the crypto_accel.ko module.
2. Hotfix Deployment: Schedule a window to apply the hotfix (v4.2.1-Patch1) as soon as it clears QA.
3. Rollback Plan: If software-based processing causes CPU throttling during peak afternoon hours, execute a full rollback to v4.1.9.

Closure Details:
Resolution Summary: N/A
Root Cause: N/A
Closure Date: N/A
"""


class ParseNotesTests(unittest.TestCase):
    def test_incident_sample_keeps_sections_intact(self):
        fields = parse_notes(INCIDENT_SAMPLE)
        labels = [f.label for f in fields]
        self.assertEqual(
            labels,
            [
                "Priority",
                "INC Number",
                "Agency",
                "Name",
                "State",
                "Software/Firmware Version",
                "Deployment Date",
                "Initial Issue Description",
                "Customer Ticket History",
                "Incident Context & Background",
                "Diagnostic Findings",
                "KB Utilization",
                "Actions Taken",
                "Next Steps",
                "Closure Details",
                "Resolution Summary",
                "Root Cause",
                "Closure Date",
            ],
        )

    def test_incident_sample_preserves_timestamps(self):
        fields = parse_notes(INCIDENT_SAMPLE)
        history = next(f for f in fields if f.label == "Customer Ticket History")
        self.assertIn("23:00 UTC", history.value)
        self.assertNotIn("23: 00 UTC", history.value)

    def test_incident_sample_closure_subfields_are_form_fields(self):
        fields = parse_notes(INCIDENT_SAMPLE)
        by_label = {f.label: f for f in fields}
        self.assertEqual(by_label["Closure Details"].export_mode, MODE_LABEL_BLOCK)
        self.assertEqual(by_label["Closure Details"].value, "")
        self.assertEqual(by_label["Resolution Summary"].value, "N/A")
        self.assertEqual(by_label["Root Cause"].value, "N/A")
        self.assertEqual(by_label["Closure Date"].value, "N/A")

    def test_incident_round_trip_preserves_ticket_history_times(self):
        fields = parse_notes(INCIDENT_SAMPLE)
        exported = format_output(fields, blank_between=False)
        self.assertIn("* 06/28/2026 23:00 UTC:", exported)
        self.assertNotIn("23: 00 UTC", exported)

    def test_bullet_list_block(self):
        sample = """\
Steps taken:
- Remoted to another workstation
- Tried to access the URL at https://example.com
"""
        fields = parse_notes(sample)
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0].label, "Steps taken")
        self.assertIn("- Remoted to another workstation", fields[0].value)

    def test_same_line_fields_with_values(self):
        fields = parse_notes("Backup taken: N/A\nStatus: n/a")
        self.assertEqual(len(fields), 2)
        self.assertEqual(fields[0].value, "N/A")
        self.assertEqual(fields[1].value, "n/a")

    def test_label_block_does_not_swallow_following_same_line_field(self):
        """Empty Priority: must not absorb ``INC Number: …`` as plaintext."""
        sample = """\
Priority:

INC Number: INC0084321
Agency: Department of Transportation (DoT)
"""
        fields = parse_notes(sample)
        self.assertEqual(
            [(f.label, f.value) for f in fields],
            [
                ("Priority", ""),
                ("INC Number", "INC0084321"),
                ("Agency", "Department of Transportation (DoT)"),
            ],
        )

    def test_label_block_value_stops_at_next_same_line_field(self):
        sample = """\
INC Number:
INC0084321
Agency: DoT
Name: Alex
"""
        fields = parse_notes(sample)
        self.assertEqual(fields[0].label, "INC Number")
        self.assertEqual(fields[0].value, "INC0084321")
        self.assertEqual(fields[0].export_mode, MODE_LABEL_BLOCK)
        self.assertEqual(fields[1].label, "Agency")
        self.assertEqual(fields[1].value, "DoT")
        self.assertEqual(fields[2].label, "Name")
        self.assertEqual(fields[2].value, "Alex")


if __name__ == "__main__":
    unittest.main()
