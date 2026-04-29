"""Hardcoded enum values for shell completions, sourced from airpweb/models/enums.py."""

ALERT_STATUS = [
    'UNCLAIMED', 'AUTO_ASSIGNED', 'REASSIGNED', 'TRIAGING',
    'TRIAGED', 'PROMOTED', 'DISMISSED', 'IGNORED',
]

ALERT_DISMISSAL_REASON = [
    'FALSE_POSITIVE', 'DUPLICATE', 'DOES_NOT_MEET_THRESHOLD',
    'INFORMATIONAL', 'TEST_ACTIVITY', 'MISCONFIGURATION',
    'INSUFFICIENT_DATA', 'OTHER',
]

ALERT_LABEL = ['UNKNOWN', 'POSITIVE', 'FALSE_ALARM', 'IGNORED']

INCIDENT_STATUS = [
    'Open', 'Triaged', 'Action Taken', 'Active', 'Monitor',
    'Pending Confirmation', 'Postmortem', 'Mitigated', 'Completed',
]

SEVERITY_LEVEL = ['SEV0', 'SEV1', 'SEV2', 'SEV3', 'SEV4', 'SEV5']

INCIDENT_TYPE = [
    'ATO', 'Comms Adverse Event', 'Data Leak', 'DOS/DDOS',
    'Enterprise Violations', 'Fake Accounts', 'Guest Scraping',
    'Hot Button Topics', 'InfoSec Incident', 'Jobs & Payments',
    'Jobs Fraud', 'Legal Adverse Event', 'Member Scraping',
    'Premium Ads Fraud', 'Private Messaging',
    'Public Content-Hate Speech', 'Public Content-Misinformation',
    'Scams-Malware/Phishing', 'Scams-Money',
    'State Sponsored Campaign', 'Other',
]

CASE_TYPE = ['incident', 'tpd_case']

INCIDENT_ENTITY_IMPACT = [
    'Ads', 'Company Pages', 'Enterprise Customers', 'Guest',
    'Members', 'Jobs', 'LTS (Hiring)', 'LSS (Sales)',
    'LMS (Marketing)', 'LLS (Learning)', 'Other',
]

INCIDENT_AREAS_OF_IMPACT = [
    'None', 'DPS', 'Semaphores', 'SLA Attainment',
    'UMI-Anti-Abuse', 'UMI-Fake Accounts', 'UMI-HBT',
    'UMI-Jobs', 'UMI-Misinformation', 'UMI-Public Content', 'Other',
]

TIMELINE_EVENT_TYPE = ['Severity', 'Status', 'Owner', 'Milestone']
