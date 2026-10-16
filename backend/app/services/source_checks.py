"""Deterministic checks for the bundled synthetic ticket, telemetry and calendar exports.

Other uploaded files remain operator supplied and require a human comparison.
"""
import csv
import io
import json
from itertools import islice
from datetime import datetime, timezone


def _same_time(value, expected):
    try:
        observed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return observed.astimezone(timezone.utc) == expected.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return False


def check_source(document, incident):
    try:
        return _check_source(document, incident)
    except (ValueError, TypeError, AttributeError, RecursionError, OverflowError, KeyError):
        return {'recognized': True, 'invalid': True,
                'findings': ['Malformed source data; replace with a valid export.']}


def _check_source(document, incident):
    filename = document['filename']
    category = document['category']
    try:
        data = document['payload'].decode('utf-8-sig')
    except UnicodeDecodeError:
        return {'recognized': False, 'findings': []}
    findings = []
    parsed = None
    if filename.lower().endswith('.json'):
        try:
            def invalid_constant(value):
                raise ValueError('Non-finite JSON number')
            parsed = json.loads(data, parse_constant=invalid_constant)
        except json.JSONDecodeError:
            return {'recognized': False, 'findings': []}
        if not isinstance(parsed, dict) or parsed.get('synthetic_fixture') is not True:
            return {'recognized': False, 'findings': []}
        if not isinstance(parsed.get('incident_id'), str):
            raise ValueError('Invalid incident identity')
        actual_type = 'ticket' if 'ticket_opened_at' in parsed else 'maintenance' if 'windows' in parsed else None
        if actual_type is None:
            return {'recognized': True, 'findings': ['Unrecognized synthetic JSON source format.']}
        if actual_type != category:
            findings.append(f'File contains {actual_type} data but is labelled {category}.')
        if parsed.get('incident_id') != incident.id:
            findings.append('Incident ID differs from the case.')
        if actual_type == 'ticket':
            if not all(isinstance(parsed.get(field), str) for field in ['ticket_opened_at', 'vendor_acknowledged_at']):
                raise ValueError('Invalid ticket timestamps')
            if not _same_time(parsed.get('ticket_opened_at'), incident.ticket_opened_at):
                findings.append('Ticket opened time differs from the entered incident.')
            if not _same_time(parsed.get('vendor_acknowledged_at'), incident.vendor_acknowledged_at):
                findings.append('Vendor acknowledgement time differs from the entered incident.')
        else:
            source_windows = parsed.get('windows')
            if not isinstance(source_windows, list) or len(source_windows) > 25:
                raise ValueError('Invalid maintenance windows')
            for item in source_windows:
                if not isinstance(item, dict) or not all(isinstance(item.get(field), str) for field in ['start', 'end', 'description']):
                    raise ValueError('Invalid maintenance field types')
            if not isinstance(source_windows, list) or len(source_windows) != len(incident.maintenance_windows):
                findings.append('Maintenance window count differs from the entered incident.')
            else:
                for index, (source, entered) in enumerate(zip(source_windows, incident.maintenance_windows), 1):
                    if (not isinstance(source, dict) or not _same_time(source.get('start'), entered.start)
                            or not _same_time(source.get('end'), entered.end)
                            or source.get('description', '').strip() != entered.description.strip()):
                        findings.append(f'Maintenance window {index} differs from the entered incident.')
        return {'recognized': True, 'findings': findings}
    if filename.lower().endswith('.csv'):
        try:
            rows = list(islice(csv.DictReader(io.StringIO(data)), 5001))
            if len(rows) > 5000:
                raise ValueError('Too many telemetry rows')
        except csv.Error:
            return {'recognized': False, 'findings': []}
        if not rows or 'synthetic_fixture' not in rows[0]:
            return {'recognized': False, 'findings': []}
        if category != 'telemetry':
            findings.append(f'File contains telemetry data but is labelled {category}.')
        if any(row.get('synthetic_fixture') != 'true' or row.get('incident_id') != incident.id for row in rows):
            findings.append('Telemetry incident ID or synthetic marker differs from the case.')
        if not any(_same_time(row.get('timestamp_utc'), incident.start) for row in rows):
            findings.append('Telemetry has no row at the entered incident start.')
        if not any(_same_time(row.get('timestamp_utc'), incident.end) for row in rows):
            findings.append('Telemetry has no row at the entered incident end.')
        for row in rows:
            if row.get('pump_state') != incident.telemetry.get('pump_state'):
                findings.append('Pump state differs from the entered incident.')
                break
        pressure = incident.telemetry.get('coolant_pressure_bar')
        if pressure is not None:
            try:
                if any(float(row.get('coolant_pressure_bar', 'nan')) != float(pressure) for row in rows):
                    findings.append('Coolant pressure differs from the entered incident.')
            except ValueError:
                findings.append('Coolant pressure in telemetry is invalid.')
        return {'recognized': True, 'findings': findings}
    return {'recognized': False, 'findings': []}
